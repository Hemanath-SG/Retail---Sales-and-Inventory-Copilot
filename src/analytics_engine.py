import sqlite3
import os
from typing import Dict, List, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "retail_copilot.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_overall_kpis(store_id: Optional[str] = None) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    where_clause = "WHERE store_id = ?" if store_id else ""
    params = (store_id,) if store_id else ()
    
    # 1. Total Stores Count
    cursor.execute("SELECT COUNT(*) as count FROM stores " + (f"WHERE store_id = '{store_id}'" if store_id else ""))
    total_stores = cursor.fetchone()["count"]
    
    # 2. Total Sales 30 Days & Revenue
    query_sales = f"""
    SELECT SUM(units_sold) as total_units, SUM(revenue) as total_revenue 
    FROM daily_sales 
    {where_clause}
    """
    cursor.execute(query_sales, params)
    sales_res = cursor.fetchone()
    total_units = sales_res["total_units"] or 0
    total_revenue = round(sales_res["total_revenue"] or 0.0, 2)
    
    # 3. Inventory Value & Total SKUs
    query_inv = f"""
    SELECT SUM(i.current_stock * p.unit_cost) as total_cost_value,
           SUM(i.current_stock * p.unit_price) as total_retail_value,
           COUNT(DISTINCT i.sku) as total_skus
    FROM inventory i
    JOIN products p ON i.sku = p.sku
    {where_clause}
    """
    cursor.execute(query_inv, params)
    inv_res = cursor.fetchone()
    inventory_cost = round(inv_res["total_cost_value"] or 0.0, 2)
    inventory_retail = round(inv_res["total_retail_value"] or 0.0, 2)
    total_skus = inv_res["total_skus"] or 0
    
    # 4. Critical Stockout count
    stockouts = get_stockout_risks(store_id)
    dead_stocks = get_dead_stock(store_id)
    anomalies = get_sales_anomalies(store_id)
    
    conn.close()
    
    return {
        "total_stores": total_stores,
        "total_units_sold_90d": total_units,
        "total_revenue_90d": total_revenue,
        "inventory_cost_value": inventory_cost,
        "inventory_retail_value": inventory_retail,
        "total_skus": total_skus,
        "stockout_alerts": len(stockouts),
        "dead_stock_alerts": len(dead_stocks),
        "anomaly_alerts": len(anomalies)
    }

def get_stockout_risks(store_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    where_clause = "WHERE i.store_id = ?" if store_id else ""
    params = (store_id,) if store_id else ()
    
    query = f"""
    SELECT i.store_id, s.name as store_name, i.sku, p.name as product_name, p.category,
           i.current_stock, p.lead_time_days, p.reorder_point, p.target_stock, p.unit_cost, p.unit_price
    FROM inventory i
    JOIN products p ON i.sku = p.sku
    JOIN stores s ON i.store_id = s.store_id
    {where_clause}
    """
    cursor.execute(query, params)
    inv_items = cursor.fetchall()
    
    risks = []
    for item in inv_items:
        # Calculate 14-day sales velocity
        cursor.execute("""
        SELECT SUM(units_sold) as total_14d
        FROM daily_sales
        WHERE store_id = ? AND sku = ?
          AND sale_date >= date('now', '-14 days')
        """, (item["store_id"], item["sku"]))
        sales_14d = cursor.fetchone()["total_14d"] or 0
        velocity_14d = round(sales_14d / 14.0, 2)
        
        if velocity_14d > 0:
            days_remaining = round(item["current_stock"] / velocity_14d, 1)
        else:
            days_remaining = 999.0
            
        # Flag if stock runs out within lead time + 1 day buffer
        if days_remaining <= item["lead_time_days"] + 1.0 or item["current_stock"] <= item["reorder_point"]:
            rec_reorder = max(item["target_stock"] - item["current_stock"], 20)
            est_cost = round(rec_reorder * item["unit_cost"], 2)
            
            # Check if another store has surplus inventory for transfer
            cursor.execute("""
            SELECT i2.store_id, s2.name as store_name, i2.current_stock
            FROM inventory i2
            JOIN stores s2 ON i2.store_id = s2.store_id
            WHERE i2.sku = ? AND i2.store_id != ? AND i2.current_stock >= 50
            """, (item["sku"], item["store_id"]))
            surplus = cursor.fetchone()
            
            if surplus:
                rec_action = f"Emergency transfer 25 units from {surplus['store_name']} (Surplus: {surplus['current_stock']} units available), or place purchase order for {rec_reorder} units (${est_cost})."
            else:
                rec_action = f"Place purchase order for {rec_reorder} units (${est_cost} total) immediately to prevent stock-out before lead time."
                
            risks.append({
                "alert_type": "STOCKOUT_RISK",
                "severity": "HIGH" if days_remaining <= item["lead_time_days"] else "MEDIUM",
                "store_id": item["store_id"],
                "store_name": item["store_name"],
                "sku": item["sku"],
                "product_name": item["product_name"],
                "category": item["category"],
                "current_stock": item["current_stock"],
                "daily_velocity": velocity_14d,
                "days_remaining": days_remaining,
                "lead_time_days": item["lead_time_days"],
                "message": f"{item['product_name']} has only {item['current_stock']} units left with daily sales of {velocity_14d} units/day. Estimated stock-out in {days_remaining} days (Lead time: {item['lead_time_days']} days).",
                "recommended_action": rec_action,
                "data_assumptions": {
                    "current_stock": item["current_stock"],
                    "daily_velocity_14d": velocity_14d,
                    "days_remaining": days_remaining,
                    "lead_time_days": item["lead_time_days"],
                    "unit_cost": item["unit_cost"],
                    "reorder_qty": rec_reorder,
                    "total_est_cost": est_cost
                }
            })
            
    conn.close()
    return sorted(risks, key=lambda x: x["days_remaining"])

def get_dead_stock(store_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    where_clause = "WHERE i.store_id = ?" if store_id else ""
    params = (store_id,) if store_id else ()
    
    query = f"""
    SELECT i.store_id, s.name as store_name, i.sku, p.name as product_name, p.category,
           i.current_stock, i.last_restocked, p.unit_cost, p.unit_price
    FROM inventory i
    JOIN products p ON i.sku = p.sku
    JOIN stores s ON i.store_id = s.store_id
    {where_clause}
    """
    cursor.execute(query, params)
    inv_items = cursor.fetchall()
    
    dead_stock_list = []
    for item in inv_items:
        if item["current_stock"] <= 0:
            continue
            
        cursor.execute("""
        SELECT SUM(units_sold) as total_21d
        FROM daily_sales
        WHERE store_id = ? AND sku = ?
          AND sale_date >= date('now', '-21 days')
        """, (item["store_id"], item["sku"]))
        sales_21d = cursor.fetchone()["total_21d"] or 0
        
        if sales_21d == 0:
            tied_up = round(item["current_stock"] * item["unit_cost"], 2)
            potential_revenue = round(item["current_stock"] * item["unit_price"], 2)
            
            markdown_price = round(item["unit_price"] * 0.75, 2)
            rec_action = f"Apply 25% clearance markdown (New price: ${markdown_price}) or bundle with complementary fast-mover to liquidate ${tied_up} tied-up capital."
            
            dead_stock_list.append({
                "alert_type": "DEAD_STOCK",
                "severity": "MEDIUM" if tied_up < 1000 else "HIGH",
                "store_id": item["store_id"],
                "store_name": item["store_name"],
                "sku": item["sku"],
                "product_name": item["product_name"],
                "category": item["category"],
                "current_stock": item["current_stock"],
                "sales_21d": sales_21d,
                "tied_up_capital": tied_up,
                "message": f"Zero sales recorded for {item['product_name']} over the last 21 days. {item['current_stock']} units sitting idle (${tied_up} tied up capital).",
                "recommended_action": rec_action,
                "data_assumptions": {
                    "current_stock": item["current_stock"],
                    "unit_cost": item["unit_cost"],
                    "current_unit_price": item["unit_price"],
                    "tied_up_capital": tied_up,
                    "potential_revenue": potential_revenue,
                    "recommended_markdown_price": markdown_price
                }
            })
            
    conn.close()
    return sorted(dead_stock_list, key=lambda x: x["tied_up_capital"], reverse=True)

def get_sales_anomalies(store_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    where_clause = "WHERE i.store_id = ?" if store_id else ""
    params = (store_id,) if store_id else ()
    
    query = f"""
    SELECT i.store_id, s.name as store_name, i.sku, p.name as product_name, p.category,
           i.current_stock, p.unit_cost, p.unit_price, p.target_stock
    FROM inventory i
    JOIN products p ON i.sku = p.sku
    JOIN stores s ON i.store_id = s.store_id
    {where_clause}
    """
    cursor.execute(query, params)
    inv_items = cursor.fetchall()
    
    anomalies = []
    for item in inv_items:
        # 3-day recent velocity
        cursor.execute("""
        SELECT SUM(units_sold) as units_3d
        FROM daily_sales
        WHERE store_id = ? AND sku = ?
          AND sale_date >= date('now', '-3 days')
        """, (item["store_id"], item["sku"]))
        sales_3d = cursor.fetchone()["units_3d"] or 0
        v_3d = round(sales_3d / 3.0, 2)
        
        # 30-day baseline velocity
        cursor.execute("""
        SELECT SUM(units_sold) as units_30d
        FROM daily_sales
        WHERE store_id = ? AND sku = ?
          AND sale_date >= date('now', '-30 days')
        """, (item["store_id"], item["sku"]))
        sales_30d = cursor.fetchone()["units_30d"] or 0
        v_30d = round(sales_30d / 30.0, 2)
        
        if v_30d > 0.5:
            ratio = round(v_3d / v_30d, 2)
            
            # Spike Detection (> 2.0x)
            if ratio >= 2.0 and sales_3d >= 10:
                pct_inc = int((ratio - 1.0) * 100)
                rec_action = f"Increase short-term reorder multiplier by 1.5x to account for demand surge (+{pct_inc}% sales jump)."
                anomalies.append({
                    "alert_type": "SALES_SPIKE",
                    "severity": "HIGH" if ratio >= 3.0 else "MEDIUM",
                    "store_id": item["store_id"],
                    "store_name": item["store_name"],
                    "sku": item["sku"],
                    "product_name": item["product_name"],
                    "category": item["category"],
                    "current_stock": item["current_stock"],
                    "v_3d": v_3d,
                    "v_30d": v_30d,
                    "multiplier": ratio,
                    "message": f"Sales Spike! {item['product_name']} daily sales jumped by +{pct_inc}% over the last 3 days ({v_3d} units/day vs 30d avg of {v_30d} units/day).",
                    "recommended_action": rec_action,
                    "data_assumptions": {
                        "velocity_3d": v_3d,
                        "velocity_30d_avg": v_30d,
                        "spike_multiplier": ratio,
                        "current_stock": item["current_stock"]
                    }
                })
            
            # Drop Detection (< 0.35x when baseline was significant)
            elif ratio <= 0.35 and v_30d >= 4.0:
                pct_dec = int((1.0 - ratio) * 100)
                rec_action = f"Investigate price changes, competitors, or shelf placement. Consider temporal promo or 2-for-1 deal to revive demand (-{pct_dec}% sales drop)."
                anomalies.append({
                    "alert_type": "SALES_DROP",
                    "severity": "MEDIUM",
                    "store_id": item["store_id"],
                    "store_name": item["store_name"],
                    "sku": item["sku"],
                    "product_name": item["product_name"],
                    "category": item["category"],
                    "current_stock": item["current_stock"],
                    "v_3d": v_3d,
                    "v_30d": v_30d,
                    "multiplier": ratio,
                    "message": f"Sales Drop! {item['product_name']} sales dropped by -{pct_dec}% over the last 3 days ({v_3d} units/day vs 30d avg of {v_30d} units/day).",
                    "recommended_action": rec_action,
                    "data_assumptions": {
                        "velocity_3d": v_3d,
                        "velocity_30d_avg": v_30d,
                        "drop_percentage": pct_dec,
                        "current_stock": item["current_stock"]
                    }
                })
                
    conn.close()
    return anomalies

def get_daily_attention_feed(store_id: Optional[str] = None) -> List[Dict[str, Any]]:
    stockouts = get_stockout_risks(store_id)
    dead_stocks = get_dead_stock(store_id)
    anomalies = get_sales_anomalies(store_id)
    
    # Merge and prioritize
    all_alerts = stockouts + dead_stocks + anomalies
    
    # Sort order: HIGH severity first
    return sorted(all_alerts, key=lambda x: 0 if x["severity"] == "HIGH" else 1)

def query_database_facts(search_term: str) -> Dict[str, Any]:
    """Helper to query database facts for GenAI grounding"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    term = f"%{search_term.strip()}%"
    
    # Check if query matches product
    cursor.execute("""
    SELECT p.sku, p.name, p.category, p.unit_cost, p.unit_price, p.reorder_point, p.lead_time_days,
           i.store_id, s.name as store_name, i.current_stock
    FROM products p
    JOIN inventory i ON p.sku = i.sku
    JOIN stores s ON i.store_id = s.store_id
    WHERE p.name LIKE ? OR p.sku LIKE ? OR p.category LIKE ?
    """, (term, term, term))
    products = [dict(row) for row in cursor.fetchall()]
    
    # Check 30d sales for matching products
    sales_facts = []
    if products:
        skus = list(set(p["sku"] for p in products))
        placeholders = ",".join("?" for _ in skus)
        cursor.execute(f"""
        SELECT store_id, sku, SUM(units_sold) as total_units_30d, SUM(revenue) as total_revenue_30d
        FROM daily_sales
        WHERE sku IN ({placeholders}) AND sale_date >= date('now', '-30 days')
        GROUP BY store_id, sku
        """, skus)
        sales_facts = [dict(row) for row in cursor.fetchall()]
        
    conn.close()
    return {
        "products": products,
        "sales_facts_30d": sales_facts
    }
