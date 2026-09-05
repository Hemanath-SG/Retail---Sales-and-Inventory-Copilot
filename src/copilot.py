import os
import json
from typing import Dict, Any, Optional
from src.analytics_engine import (
    get_overall_kpis,
    get_stockout_risks,
    get_dead_stock,
    get_sales_anomalies,
    get_daily_attention_feed,
    query_database_facts
)
from src.vector_store import search_catalog_knowledge

def ask_copilot(query: str, store_id: Optional[str] = None) -> Dict[str, Any]:
    query_lower = query.lower().strip()
    
    # 1. Intent Classification & Deterministic Grounding Context Fetching
    context: Dict[str, Any] = {}
    intent = "general"
    
    # Check for semantic knowledge & policy matches
    relevant_knowledge = search_catalog_knowledge(query, top_k=2)
    context["retrieved_policies"] = [
        {"title": k["title"], "text": k["text"]} 
        for k in relevant_knowledge if k.get("type") == "policy"
    ]

    # Intent 1: Stockouts & Reorder
    if any(w in query_lower for w in ["running out", "stockout", "out of stock", "low stock", "replenish", "reorder", "short"]):
        intent = "stockout_risks"
        data = get_stockout_risks(store_id)
        context["type"] = "Likely Stock-outs & Reorder Alerts"
        context["stockout_items"] = data
        
    # Intent 2: Dead stock / Overstocked
    elif any(w in query_lower for w in ["overstocked", "dead stock", "not moving", "slow moving", "clearance", "idle"]):
        intent = "dead_stock"
        data = get_dead_stock(store_id)
        context["type"] = "Dead Stock & Overstocked Inventory"
        context["dead_stock_items"] = data
        
    # Intent 3: Anomalies (Spikes & Drops)
    elif any(w in query_lower for w in ["spike", "drop", "anomaly", "surge", "slump", "unusual", "trend"]):
        intent = "sales_anomalies"
        data = get_sales_anomalies(store_id)
        context["type"] = "Sales Velocity Spikes & Drops"
        context["anomalies"] = data
        
    # Intent 4: Daily attention feed
    elif any(w in query_lower for w in ["today", "attention", "feed", "flag", "priority", "what needs"]):
        intent = "daily_attention"
        data = get_daily_attention_feed(store_id)
        context["type"] = "Daily Attention Priority Feed"
        context["attention_items"] = data
        
    # Intent 5: KPIs and overall performance
    elif any(w in query_lower for w in ["kpi", "overall", "revenue", "performance", "summary", "dashboard"]):
        intent = "kpis"
        data = get_overall_kpis(store_id)
        context["type"] = "Store Network KPIs & Financial Summary"
        context["kpis"] = data
        
    # Intent 6: Product performance or specific SKU lookup (e.g. "how did Organic Milk do this month?")
    else:
        facts = query_database_facts(query_lower)
        if facts["products"]:
            intent = "product_lookup"
            context["type"] = f"Product Sales & Stock Data for '{query}'"
            context["products"] = facts["products"]
            context["sales_30d"] = facts["sales_facts_30d"]
        else:
            intent = "out_of_scope"
            context["type"] = "Refusal: Data Not Found"
            context["message"] = (
                "The system data cannot answer this question as no matching records exist in store catalogue, "
                "inventory levels, or 90-day sales history."
            )

    # 2. Check if GEMINI_API_KEY is available
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    
    if gemini_key:
        # Attempt LLM call using google.genai or legacy google.generativeai
        llm_response = call_gemini_llm(query, intent, context, gemini_key)
        if llm_response:
            return llm_response
            
    # Deterministic Grounded Fallback
    return generate_deterministic_grounded_response(query, intent, context)

def call_gemini_llm(query: str, intent: str, context: Dict[str, Any], api_key: str) -> Optional[Dict[str, Any]]:
    system_instruction = (
        "You are an expert Retail Sales and Inventory Copilot for store managers.\n"
        "Your role is to analyze sales velocity, inventory levels, lead times, and store policies.\n\n"
        "MANDATORY GROUNDING RULES:\n"
        "1. ALWAYS substantiate every claim with exact numbers from the DATA PAYLOAD (current stock units, daily velocity, lead times, revenue dollars, tied-up capital). NEVER make a claim without the figures.\n"
        "2. When answering alerts or issues, clearly recommend concrete actions showing the data and assumptions behind them.\n"
        "3. If the user asks about products, items, or topics NOT present in the DATA PAYLOAD (e.g. laptops, weather, general knowledge), YOU MUST REFUSE: state clearly that the system data cannot answer this question because no matching records exist in the retail catalogue. DO NOT GUESS OR INVENT DATA.\n"
        "4. Format the response with clean Markdown bolding for numbers and bullet points."
    )
    
    prompt = f"{system_instruction}\n\nDATA PAYLOAD:\n{json.dumps(context, indent=2)}\n\nUSER QUESTION:\n{query}"

    # Try modern google.genai SDK first
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
    except Exception as e1:
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
        except Exception as e2:
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
    except Exception as e3:
        print(f"[Copilot Warning] All Gemini SDK calls failed ({e3}), using deterministic grounding.")

    return None

def generate_deterministic_grounded_response(query: str, intent: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic, mathematically exact grounding fallback"""
    
    if intent == "stockout_risks":
        items = context.get("stockout_items", [])
        if not items:
            text = "✅ **Healthy Inventory:** No products are at risk of stock-out across the stores. All items exceed lead-time buffers."
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
        
    else: # out_of_scope
        text = (
            "⚠️ **The data cannot answer this question.**\n"
            "No matching products, stores, or metrics exist in the retail system database for your query.\n\n"
            "Our system tracks 20 catalogue SKUs across Fresh Produce & Dairy, Bakery, Beverages, Personal Care, and Home & Kitchen.\n"
            "Please ask about stock-out risks, dead stock, sales spikes/drops, or specific store catalogue products."
        )
        
    return {
        "query": query,
        "intent": intent,
        "answer": text,
        "grounded_data": context,
        "source": "Deterministic Grounding Engine"
    }
