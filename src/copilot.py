import os
import json
from typing import Dict, Any, Optional, List
from src.analytics_engine import (
    get_overall_kpis,
    get_stockout_risks,
    get_dead_stock,
    get_sales_anomalies,
    get_daily_attention_feed,
    get_category_breakdown,
    get_sales_velocity_trends,
    get_full_inventory_catalog,
    get_top_performing_products,
    get_store_network_info,
    get_all_policies,
    get_action_history,
    query_database_facts
)
from src.vector_store import search_catalog_knowledge

def ask_copilot(query: str, store_id: Optional[str] = None, custom_api_key: Optional[str] = None) -> Dict[str, Any]:
    query_lower = query.lower().strip()
    context: Dict[str, Any] = {}
    intent = "general"
    
    # 1. Intent Detection & Dynamic Data Extraction

    # Intent 1: Stockout & Reorder Queries
    if any(w in query_lower for w in ["running out", "stockout", "out of stock", "low stock", "replenish", "reorder", "shortage"]):
        intent = "stockout_risks"
        data = get_stockout_risks(store_id)
        context["type"] = "Likely Stock-outs & Reorder Alerts"
        context["stockout_items"] = data

    # Intent 2: Dead stock / Overstocked Queries
    elif any(w in query_lower for w in ["overstocked", "dead stock", "not moving", "slow moving", "clearance", "idle stock"]):
        intent = "dead_stock"
        data = get_dead_stock(store_id)
        context["type"] = "Dead Stock & Overstocked Inventory"
        context["dead_stock_items"] = data

    # Intent 3: Sales Anomalies (Spikes & Drops)
    elif any(w in query_lower for w in ["spike", "drop", "anomaly", "surge", "slump", "unusual velocity"]):
        intent = "sales_anomalies"
        data = get_sales_anomalies(store_id)
        context["type"] = "Sales Velocity Spikes & Drops"
        context["anomalies"] = data

    # Intent 4: Daily attention priority feed
    elif any(w in query_lower for w in ["today", "attention", "feed", "flag", "priority", "what needs", "action items"]):
        intent = "daily_attention"
        data = get_daily_attention_feed(store_id)
        context["type"] = "Daily Attention Priority Feed"
        context["attention_items"] = data

    # Intent 5: Full Inventory Listing & Catalogue Inquiries ("what are the things in the inventory", "what do we have")
    elif any(w in query_lower for w in [
        "things in the inventory", "in the inventory", "in inventory", "show inventory", 
        "what do we have", "what do you have", "what products", "list products", "list items", 
        "what do we sell", "our products", "all products", "catalogue", "catalog", 
        "everything in stock", "items in stock", "show items"
    ]):
        intent = "inventory_catalog"
        items = get_full_inventory_catalog(store_id)
        context["type"] = "Full Store Inventory Catalogue"
        context["catalog_items"] = items
        context["total_skus"] = len(set(i["sku"] for i in items))
        context["total_units"] = sum(i["current_stock"] for i in items)

    # Intent 6: Operational Policies & Standard Operating Procedures
    elif any(w in query_lower for w in ["policy", "policies", "rule", "rules", "buffer", "threshold", "sop", "guideline", "standard"]):
        intent = "policies_overview"
        knowledge = search_catalog_knowledge(query, top_k=2)
        policy_matches = [k for k in knowledge if k.get("type") == "policy"]
        context["type"] = "Store Operations Standard Policies"
        context["policies"] = policy_matches if policy_matches else get_all_policies()

    # Intent 7: Store Network & Manager Inquiries
    elif any(w in query_lower for w in ["our stores", "list stores", "all stores", "locations", "branches", "manager", "managers", "where are", "contact", "phone"]):
        intent = "stores_overview"
        stores = get_store_network_info()
        context["type"] = "Store Network & Management Overview"
        context["stores"] = stores

    # Intent 8: Top Performing Products / Best Sellers
    elif any(w in query_lower for w in ["best seller", "best selling", "top selling", "top seller", "highest revenue", "most popular", "most sold", "leaderboard", "rank"]):
        intent = "top_performers"
        top_prods = get_top_performing_products(store_id, limit=5)
        context["type"] = "Top 5 Best Selling Products (90 Days)"
        context["top_products"] = top_prods

    # Intent 9: Category Performance & Breakdown
    elif any(w in query_lower for w in ["category", "categories", "department", "departments", "margin", "profit"]):
        intent = "category_performance"
        cats = get_category_breakdown(store_id)
        context["type"] = "Category Financial Breakdown & Margins"
        context["categories"] = cats

    # Intent 10: Executed Actions Audit History
    elif any(w in query_lower for w in ["action history", "audit log", "recent actions", "transfers made", "orders placed"]):
        intent = "action_history"
        history = get_action_history()
        context["type"] = "Manager Action Execution Audit Trail"
        context["recent_actions"] = history

    # Intent 11: Specific Category Drilldown (Dairy, Bakery, Beverages, Personal Care, Kitchen)
    elif any(cat in query_lower for cat in ["dairy", "bakery", "bread", "beverage", "drink", "personal care", "pharmacy", "kitchen", "cookware"]):
        matched_cat = ""
        if "dairy" in query_lower: matched_cat = "Dairy"
        elif "bakery" in query_lower or "bread" in query_lower: matched_cat = "Bakery"
        elif "beverage" in query_lower or "drink" in query_lower: matched_cat = "Beverages"
        elif "personal" in query_lower or "pharmacy" in query_lower: matched_cat = "Personal Care"
        elif "kitchen" in query_lower or "cookware" in query_lower: matched_cat = "Home & Kitchen"

        items = get_full_inventory_catalog(store_id, category=matched_cat)
        if items:
            intent = "category_drilldown"
            context["type"] = f"Inventory Records for {matched_cat}"
            context["category_items"] = items
        else:
            intent = "inventory_catalog"
            context["catalog_items"] = get_full_inventory_catalog(store_id)

    # Intent 12: Specific Product Lookup or General KPI Summary
    elif any(w in query_lower for w in ["kpi", "overall", "revenue", "performance", "summary", "dashboard", "total sales"]):
        intent = "kpis"
        data = get_overall_kpis(store_id)
        context["type"] = "Store Network KPIs & Financial Summary"
        context["kpis"] = data

    else:
        # Check if query matches any product in catalogue
        facts = query_database_facts(query_lower)
        if facts["products"]:
            intent = "product_lookup"
            context["type"] = f"Product Sales & Stock Data for '{query}'"
            context["products"] = facts["products"]
            context["sales_30d"] = facts["sales_facts_30d"]
        else:
            intent = "out_of_scope"
            context["type"] = "Refusal: Unrelated Query"
            context["message"] = (
                "The system data cannot answer this question as no matching products, stores, "
                "or operational records exist in the retail database."
            )

    # 2. Check for Gemini API Key (from parameter or environment)
    gemini_key = custom_api_key or os.environ.get("GEMINI_API_KEY", "").strip()
    
    if gemini_key:
        llm_response = call_gemini_llm(query, intent, context, gemini_key)
        if llm_response:
            return llm_response
            
    # 3. Fallback to Enhanced Deterministic Grounded Engine
    return generate_deterministic_grounded_response(query, intent, context)

def call_gemini_llm(query: str, intent: str, context: Dict[str, Any], api_key: str) -> Optional[Dict[str, Any]]:
    system_instruction = (
        "You are an expert Retail Sales and Inventory Operations Copilot for store managers.\n"
        "Your role is to answer questions about inventory, products, sales velocity, stores, and operational policies.\n\n"
        "MANDATORY GROUNDING RULES:\n"
        "1. ALWAYS cite verified numbers from the DATA PAYLOAD (e.g. stock units, velocity rates, lead times, prices, revenue dollars, tied-up capital). Never make a claim without figures.\n"
        "2. When discussing stockouts or dead stock, recommend actionable operational steps (inter-store transfers, purchase orders, markdowns).\n"
        "3. If the user asks about products or topics completely unrelated to our retail operations (e.g. laptops, weather, politics), politely refuse and clarify what retail data is available.\n"
        "4. Format your answer with clean Markdown bolding for numbers and bullet points."
    )
    
    prompt = f"{system_instruction}\n\nDATA PAYLOAD:\n{json.dumps(context, indent=2)}\n\nUSER QUESTION:\n{query}"

    # Try modern google.genai SDK
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        if response and response.text:
            return {
                "query": query,
                "intent": intent,
                "answer": response.text.strip(),
                "grounded_data": context,
                "source": "Google Gemini 2.5 Flash (Grounded)"
            }
    except Exception:
        # Fallback to gemini-1.5-flash
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            if response and response.text:
                return {
                    "query": query,
                    "intent": intent,
                    "answer": response.text.strip(),
                    "grounded_data": context,
                    "source": "Google Gemini 1.5 Flash (Grounded)"
                }
        except Exception:
            pass

    # Try legacy google.generativeai SDK
    try:
        import google.generativeai as genai_legacy
        genai_legacy.configure(api_key=api_key)
        model = genai_legacy.GenerativeModel("gemini-1.5-flash")
        res = model.generate_content(prompt)
        if res and res.text:
            return {
                "query": query,
                "intent": intent,
                "answer": res.text.strip(),
                "grounded_data": context,
                "source": "Google Gemini 1.5 Flash (Legacy SDK)"
            }
    except Exception as e:
        print(f"[Copilot Warning] Gemini API call failed ({e}), using deterministic grounding.")

    return None

def generate_deterministic_grounded_response(query: str, intent: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Comprehensive, mathematically exact deterministic grounding engine"""

    # 1. Full Inventory Catalog Listing
    if intent in ["inventory_catalog", "category_drilldown"]:
        items = context.get("catalog_items") or context.get("category_items") or []
        if not items:
            text = "No inventory items found matching your criteria."
        else:
            # Group by category
            cats: Dict[str, List[Dict[str, Any]]] = {}
            for item in items:
                cat = item["category"]
                if cat not in cats: cats[cat] = []
                cats[cat].append(item)

            lines = [f"📦 **Store Inventory Catalogue ({len(items)} product records across stores):**\n"]
            for cat_name, cat_items in cats.items():
                lines.append(f"### 🏷️ {cat_name}")
                # Aggregate stock per product
                prod_agg: Dict[str, Dict[str, Any]] = {}
                for p in cat_items:
                    sku = p["sku"]
                    if sku not in prod_agg:
                        prod_agg[sku] = {
                            "name": p["name"],
                            "price": p["unit_price"],
                            "cost": p["unit_cost"],
                            "lead_time": p["lead_time_days"],
                            "total_stock": 0,
                            "store_breakdown": []
                        }
                    prod_agg[sku]["total_stock"] += p["current_stock"]
                    prod_agg[sku]["store_breakdown"].append(f"{p['store_name']}: {p['current_stock']}")

                for sku, p in prod_agg.items():
                    stores_str = ", ".join(p["store_breakdown"])
                    lines.append(
                        f"- **{p['name']}** (`{sku}`):\n"
                        f"  - **Total Network Stock:** **{p['total_stock']} units** ({stores_str})\n"
                        f"  - **Price:** **${p['price']:.2f}** | Cost: **${p['cost']:.2f}** | Lead Time: **{p['lead_time']} days**"
                    )
                lines.append("")
            text = "\n".join(lines)

    # 2. Top Performing Best Sellers
    elif intent == "top_performers":
        top = context.get("top_products", [])
        lines = [f"🏆 **Top 5 Best-Selling Products Across Store Network (90 Days):**\n"]
        for idx, p in enumerate(top, 1):
            lines.append(
                f"{idx}. **{p['name']}** (`{p['sku']}`):\n"
                f"   - **90-Day Revenue:** **${p['total_revenue']:,}** (**{p['total_units_sold']:,} units sold**)\n"
                f"   - **Gross Profit Margin:** **${p['gross_margin']:,}** (Unit Price: ${p['unit_price']:.2f} | Cost: ${p['unit_cost']:.2f})\n"
                f"   - **Category:** {p['category']}"
            )
        text = "\n".join(lines)

    # 3. Category Performance
    elif intent == "category_performance":
        cats = context.get("categories", [])
        lines = [f"📊 **Category Performance & Profit Breakdown:**\n"]
        for c in cats:
            margin_pct = round((c["gross_profit"] / c["total_revenue"] * 100), 1) if c["total_revenue"] > 0 else 0
            lines.append(
                f"- **{c['category']}**:\n"
                f"  - **Total Revenue:** **${c['total_revenue']:,}** ({c['total_units']:,} units sold)\n"
                f"  - **Gross Profit:** **${c['gross_profit']:,}** (**{margin_pct}% margin**)"
            )
        text = "\n".join(lines)

    # 4. Store Network & Manager Information
    elif intent == "stores_overview":
        stores = context.get("stores", [])
        lines = [f"🏬 **Store Network Directory & Operations:**\n"]
        for s in stores:
            lines.append(
                f"- **{s['name']}** (`{s['store_id']}`):\n"
                f"  - **Location:** {s['location']}\n"
                f"  - **Store Manager:** **{s['manager']}** (Contact: `{s['phone']}`)\n"
                f"  - **Delivery Schedule:** {s['delivery_days']}\n"
                f"  - **Inventory on Hand:** **{s['total_units']:,} units** across **{s['sku_count']} SKUs** (Valuation: **${s['inventory_retail_val']:,}** retail / **${s['inventory_cost_val']:,}** cost)"
            )
        text = "\n".join(lines)

    # 5. Policies & Operating Rules
    elif intent == "policies_overview":
        policies = context.get("policies", [])
        lines = [f"📜 **Store Operations Standard Operating Policies (SOP):**\n"]
        for p in policies:
            pol_id = p.get("policy_id") or p.get("id") or "POL"
            cat = p.get("category") or "Operations"
            desc = p.get("description") or p.get("text") or ""
            lines.append(
                f"- **[{pol_id}] {p.get('title', 'Policy')}** (*{cat}*):\n"
                f"  - {desc}"
            )
        text = "\n".join(lines)

    # 6. Action Execution Audit History
    elif intent == "action_history":
        actions = context.get("recent_actions", [])
        if not actions:
            text = "📜 No manager actions have been executed yet in the current session."
        else:
            lines = [f"📜 **Recent Manager Executed Actions ({len(actions)} total):**\n"]
            for a in actions[:6]:
                lines.append(
                    f"- ⏱️ `{a['created_at']}` | **{a['action_type']}** (`{a['action_id']}`):\n"
                    f"  - {a['details']} [Status: **{a['status']}**]"
                )
            text = "\n".join(lines)

    # 7. Stockout Risks
    elif intent == "stockout_risks":
        items = context.get("stockout_items", [])
        if not items:
            text = "✅ **Healthy Inventory:** No products are at risk of stock-out across the stores."
        else:
            lines = [f"⚠️ **Found {len(items)} product(s) facing imminent stock-out:**\n"]
            for item in items:
                lines.append(
                    f"- **{item['product_name']}** (`{item['sku']}`) at **{item['store_name']}**:\n"
                    f"  - **Current Stock:** **{item['current_stock']} units**\n"
                    f"  - **14-Day Velocity:** **{item['daily_velocity']} units/day**\n"
                    f"  - **Days of Stock Remaining (DIR):** **{item['days_remaining']} days** (Vendor Lead Time: {item['lead_time_days']} days)\n"
                    f"  - **Projected Stockout Date:** **{item['projected_stockout_date']}**\n"
                    f"  - 💡 **Recommended Action:** {item['recommended_action']}\n"
                )
            text = "\n".join(lines)

    # 8. Dead Stock
    elif intent == "dead_stock":
        items = context.get("dead_stock_items", [])
        if not items:
            text = "✅ **Inventory Healthy:** No dead stock (0 sales in past 21 days) detected."
        else:
            lines = [f"📦 **Found {len(items)} dead stock item(s) idle in inventory:**\n"]
            for item in items:
                lines.append(
                    f"- **{item['product_name']}** (`{item['sku']}`) at **{item['store_name']}**:\n"
                    f"  - **Idle Stock:** **{item['current_stock']} units** (21-Day Sales: **0 units**)\n"
                    f"  - **Tied-up Capital:** **${item['tied_up_capital']}** (Unit Cost: ${item['data_assumptions']['unit_cost']})\n"
                    f"  - 💡 **Recommended Action:** {item['recommended_action']}\n"
                )
            text = "\n".join(lines)

    # 9. Sales Velocity Anomalies
    elif intent == "sales_anomalies":
        items = context.get("anomalies", [])
        if not items:
            text = "📊 **No major sales anomalies detected:** All product sales velocities are within 30-day baseline ranges."
        else:
            lines = [f"📈 **Sales Velocity Anomalies Detected ({len(items)} items):**\n"]
            for item in items:
                icon = "🔥" if item["alert_type"] == "SALES_SPIKE" else "📉"
                lines.append(
                    f"- {icon} **{item['product_name']}** (`{item['sku']}`) at **{item['store_name']}**:\n"
                    f"  - **3-Day Velocity:** **{item['v_3d']} units/day** vs 30d Baseline: **{item['v_30d']} units/day**\n"
                    f"  - **Current Stock:** **{item['current_stock']} units**\n"
                    f"  - 💡 **Recommended Action:** {item['recommended_action']}\n"
                )
            text = "\n".join(lines)

    # 10. Daily Attention Priority Feed
    elif intent == "daily_attention":
        items = context.get("attention_items", [])
        lines = [f"🔔 **Needs Attention Today ({len(items)} total flags across network):**\n"]
        for idx, item in enumerate(items[:5], 1):
            sev_badge = f"🔴 [{item['severity']}]" if item["severity"] == "CRITICAL" else f"🟡 [{item['severity']}]"
            lines.append(
                f"{idx}. {sev_badge} **{item['product_name']}** at **{item['store_name']}**:\n"
                f"   - **Issue:** {item['message']}\n"
                f"   - 💡 **Action:** {item['recommended_action']}\n"
            )
        text = "\n".join(lines)

    # 11. Network KPIs
    elif intent == "kpis":
        k = context.get("kpis", {})
        text = (
            f"🏬 **Store Network Financial & Operational Summary:**\n"
            f"- **Active Stores:** **{k['total_stores']} locations**\n"
            f"- **90-Day Total Revenue:** **${k['total_revenue_90d']:,}** (**{k['total_units_sold_90d']:,} units** sold)\n"
            f"- **Inventory Valuation:** **${k['inventory_cost_value']:,}** (Cost) / **${k['inventory_retail_value']:,}** (Retail)\n"
            f"- **Active SKUs:** **{k['total_skus']} products**\n"
            f"- **Current Active Alerts:** **{k['stockout_alerts']}** Stock-outs | **{k['dead_stock_alerts']}** Dead Stock | **{k['anomaly_alerts']}** Anomalies"
        )

    # 12. Specific Product Lookup
    elif intent == "product_lookup":
        prods = context.get("products", [])
        sales = context.get("sales_30d", [])
        lines = [f"🔍 **Product Performance & Inventory Facts for '{query}':**\n"]
        
        for p in prods:
            s_fact = next((s for s in sales if s["store_id"] == p["store_id"] and s["sku"] == p["sku"]), None)
            units_30d = s_fact["total_units_30d"] if s_fact else 0
            rev_30d = s_fact["total_revenue_30d"] if s_fact else 0.0
            
            lines.append(
                f"- **{p['name']}** (`{p['sku']}`) at **{p['store_name']}**:\n"
                f"  - **Current Stock:** **{p['current_stock']} units** (Reorder Point: {p['reorder_point']}, Lead Time: {p['lead_time_days']} days)\n"
                f"  - **Price:** **${p['unit_price']:.2f}** | Cost: **${p['unit_cost']:.2f}**\n"
                f"  - **30-Day Sales Performance:** **{units_30d} units sold**, generating **${rev_30d:,.2f}** revenue\n"
            )
        text = "\n".join(lines)

    # 13. Knowledge Retrieval Match
    elif intent == "knowledge_retrieval":
        matches = context.get("matches", [])
        lines = [f"💡 **Relevant Store Knowledge for '{query}':**\n"]
        for m in matches:
            lines.append(f"- **{m['title']}**:\n  {m['text']}\n")
        text = "\n".join(lines)

    # 14. Genuine Out of Scope Refusal
    else:
        text = (
            "⚠️ **The data cannot answer this question.**\n"
            f"No matching records for '{query}' exist in our store inventory, sales logs, or policies.\n\n"
            "Our system tracks:\n"
            "- 🏬 **3 Stores**: Downtown Metro, Suburban Mall, Westside Express\n"
            "- 📦 **20 Catalogue SKUs**: Fresh Produce & Dairy, Bakery, Beverages, Personal Care, and Home & Kitchen\n"
            "- 📊 **Analytics**: Stock-out risks, dead stock, sales velocity spikes & drops, and monthly performance.\n\n"
            "Feel free to ask about any product, store inventory, or category performance!"
        )

    return {
        "query": query,
        "intent": intent,
        "answer": text,
        "grounded_data": context,
        "source": "Deterministic Grounding Engine"
    }
