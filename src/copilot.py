import os
import json
from typing import Dict, Any
from src.analytics_engine import (
    get_overall_kpis,
    get_stockout_risks,
    get_dead_stock,
    get_sales_anomalies,
    get_daily_attention_feed,
    query_database_facts
)

# Optional Gemini SDK import
genai_sdk = None
try:
    import google.generativeai as genai
    genai_sdk = genai
except ImportError:
    try:
        from google import genai
        genai_sdk = genai
    except ImportError:
        genai_sdk = None

def ask_copilot(query: str, store_id: str = None) -> Dict[str, Any]:
    query_lower = query.lower().strip()
    
    # 1. Fetch Relevant Context from Analytics Engine based on Intent
    context = {}
    intent = "general"
    
    if any(w in query_lower for w in ["running out", "stockout", "out of stock", "low stock", "replenish", "reorder"]):
        intent = "stockout_risks"
        data = get_stockout_risks(store_id)
        context["type"] = "Likely Stock-outs & Reorder Alerts"
        context["items"] = data
        
    elif any(w in query_lower for w in ["overstocked", "dead stock", "not moving", "slow moving", "clearance"]):
        intent = "dead_stock"
        data = get_dead_stock(store_id)
        context["type"] = "Dead Stock & Overstocked Inventory"
        context["items"] = data
        
    elif any(w in query_lower for w in ["spike", "drop", "anomaly", "surge", "unusual", "trend"]):
        intent = "sales_anomalies"
        data = get_sales_anomalies(store_id)
        context["type"] = "Sales Spikes & Drops Anomalies"
        context["items"] = data
        
    elif any(w in query_lower for w in ["today", "attention", "feed", "flag", "action", "priority"]):
        intent = "daily_attention"
        data = get_daily_attention_feed(store_id)
        context["type"] = "Daily Attention Action Feed"
        context["items"] = data
        
    elif any(w in query_lower for w in ["kpi", "overall", "revenue", "performance", "summary", "dashboard"]):
        intent = "kpis"
        data = get_overall_kpis(store_id)
        context["type"] = "Overall Store KPIs & Performance"
        context["kpis"] = data
        
    else:
        # Check for specific product names or out-of-scope terms
        facts = query_database_facts(query_lower)
        if facts["products"]:
            intent = "product_lookup"
            context["type"] = f"Product Search Results for '{query}'"
            context["products"] = facts["products"]
            context["sales_30d"] = facts["sales_facts_30d"]
        else:
            intent = "out_of_scope_or_general"
            context["type"] = "Database Query Result"
            context["message"] = "No direct matching store product or inventory record found in system data."

    # 2. Check Gemini API Key
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    
    # Attempt Gemini Call if API key is present
    if gemini_key and genai_sdk:
        try:
            return call_gemini_api(query, intent, context, gemini_key)
        except Exception as e:
            # If API call fails (quota, network), fallback to rule-based grounded engine
            print(f"[Copilot Warning] Gemini API call failed ({e}), falling back to deterministic grounding.")
            return generate_deterministic_grounded_response(query, intent, context)
    else:
        # Rule-based grounded engine fallback
        return generate_deterministic_grounded_response(query, intent, context)

def call_gemini_api(query: str, intent: str, context: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    """Call Google Gemini API with strict grounding instructions"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    system_prompt = f"""You are an expert Retail Sales and Inventory Copilot for store managers.
Your job is to answer store managers' plain language questions using ONLY the actual data provided below.

CRITICAL RULES:
1. ALWAYS back every claim with exact numbers from the data payload (e.g. current stock count, daily velocity, price, lead time, revenue dollars). Never state a conclusion without figures.
2. Recommend concrete actions with clear data and assumptions behind them.
3. If the user asks about something NOT in the data payload or outside retail sales/inventory, state explicitly: "The system data cannot answer this question as no matching records exist." Never guess or invent numbers.
4. Keep output structured with Markdown bullet points and bold numbers.

DATA PAYLOAD:
{json.dumps(context, indent=2)}

USER QUESTION: {query}
"""

    response = model.generate_content(system_prompt)
    answer_text = response.text.strip() if response.text else "Unable to generate response from Gemini API."
    
    return {
        "query": query,
        "intent": intent,
        "answer": answer_text,
        "grounded_data": context,
        "source": "Gemini 1.5 Flash (Grounded)"
    }

def generate_deterministic_grounded_response(query: str, intent: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback deterministic grounded response generator"""
    
    if intent == "stockout_risks":
        items = context.get("items", [])
        if not items:
            text = "✅ **Good News!** No products are currently at immediate risk of running out across the selected stores."
        else:
            lines = [f"⚠️ **Found {len(items)} product(s) at risk of stock-out:**\n"]
            for item in items:
                lines.append(
                    f"- **{item['product_name']}** ({item['sku']}) at **{item['store_name']}**:\n"
                    f"  - **Current Stock:** {item['current_stock']} units\n"
                    f"  - **Daily Velocity (14d):** {item['daily_velocity']} units/day\n"
                    f"  - **Days Remaining:** **{item['days_remaining']} days** (Lead time: {item['lead_time_days']} days)\n"
                    f"  - 💡 **Recommended Action:** {item['recommended_action']}\n"
                )
            text = "\n".join(lines)
            
    elif intent == "dead_stock":
        items = context.get("items", [])
        if not items:
            text = "✅ **Inventory Healthy:** No dead stock (0 sales in past 21 days) detected."
        else:
            lines = [f"📦 **Found {len(items)} dead stock item(s) tied up in inventory:**\n"]
            for item in items:
                lines.append(
                    f"- **{item['product_name']}** ({item['sku']}) at **{item['store_name']}**:\n"
                    f"  - **Idle Stock:** {item['current_stock']} units\n"
                    f"  - **Tied-up Capital:** **${item['tied_up_capital']}** (Unit Cost: ${item['data_assumptions']['unit_cost']})\n"
                    f"  - **Recent Sales (21d):** 0 units sold\n"
                    f"  - 💡 **Recommended Action:** {item['recommended_action']}\n"
                )
            text = "\n".join(lines)
            
    elif intent == "sales_anomalies":
        items = context.get("items", [])
        if not items:
            text = "📊 **No major sales anomalies detected** (all sales velocities are within 30-day normal moving averages)."
        else:
            lines = [f"📈 **Sales Velocity Anomalies Detected ({len(items)} items):**\n"]
            for item in items:
                icon = "🔥" if item["alert_type"] == "SALES_SPIKE" else "📉"
                lines.append(
                    f"- {icon} **{item['product_name']}** ({item['sku']}) at **{item['store_name']}**:\n"
                    f"  - **3-Day Velocity:** **{item['v_3d']} units/day** vs 30d Avg: **{item['v_30d']} units/day**\n"
                    f"  - **Current Stock:** {item['current_stock']} units\n"
                    f"  - 💡 **Recommended Action:** {item['recommended_action']}\n"
                )
            text = "\n".join(lines)
            
    elif intent == "daily_attention":
        items = context.get("items", [])
        lines = [f"🔔 **Daily Attention Priority Items ({len(items)} flags today):**\n"]
        for idx, item in enumerate(items[:5], 1):
            lines.append(
                f"{idx}. **[{item['severity']}] {item['product_name']}** at {item['store_name']}:\n"
                f"   - {item['message']}\n"
                f"   - 💡 **Action:** {item['recommended_action']}\n"
            )
        text = "\n".join(lines)
        
    elif intent == "kpis":
        k = context.get("kpis", {})
        text = (
            f"🏬 **Store Network Performance Summary:**\n"
            f"- **Active Stores:** {k['total_stores']}\n"
            f"- **90-Day Total Revenue:** **${k['total_revenue_90d']:,}** ({k['total_units_sold_90d']:,} units sold)\n"
            f"- **Total Inventory Value:** **${k['inventory_retail_value']:,}** retail / **${k['inventory_cost_value']:,}** cost\n"
            f"- **Current Alerts:** {k['stockout_alerts']} Stock-out risks | {k['dead_stock_alerts']} Dead stock | {k['anomaly_alerts']} Anomalies"
        )
        
    elif intent == "product_lookup":
        prods = context.get("products", [])
        lines = [f"🔍 **Product Details for '{query}':**\n"]
        for p in prods:
            lines.append(
                f"- **{p['name']}** (SKU: `{p['sku']}`) at **{p['store_name']}**:\n"
                f"  - **Stock Level:** {p['current_stock']} units (Reorder Point: {p['reorder_point']}, Lead Time: {p['lead_time_days']} days)\n"
                f"  - **Unit Price:** ${p['unit_price']} | Unit Cost: ${p['unit_cost']}\n"
            )
        text = "\n".join(lines)
        
    else:
        text = (
            "⚠️ **Data Grounding Limitation:**\n"
            "The system data cannot answer this question directly as no matching products, stores, or metrics were found in the database.\n"
            "Please ask about stock-out risks, dead stock, sales spikes, or specific store catalogue products."
        )
        
    return {
        "query": query,
        "intent": intent,
        "answer": text,
        "grounded_data": context,
        "source": "Deterministic Grounded Engine"
    }
