import sqlite3
import os
import uuid
from datetime import datetime, timedelta
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
    
    # 1. Stores Count
    cursor.execute("SELECT COUNT(*) as count FROM stores " + (f"WHERE store_id = '{store_id}'" if store_id else ""))
    total_stores = cursor.fetchone()["count"]
    
    # 2. Total Sales 90 Days & Revenue
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
    
    # 4. Critical Stockout, Dead Stock, and Anomaly Counts
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
    today = datetime.now()
    
    for item in inv_items:
        # Calculate 14-day sales velocity: v = sum(units_sold)/14
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
            
        # Flag condition: DIR <= Lead Time + 1.5 Days Safety Buffer OR (current_stock <= reorder_point and velocity > 0)
        safety_threshold = item["lead_time_days"] + 1.5
        is_critical = days_remaining <= item["lead_time_days"]
        is_warning = days_remaining <= safety_threshold or (item["current_stock"] <= item["reorder_point"] and velocity_14d > 2.0)
        
        if is_critical or is_warning:
            projected_stockout = (today + timedelta(days=max(0.1, days_remaining))).strftime("%Y-%m-%d")
            rec_reorder = max(item["target_stock"] - item["current_stock"], 25)
            est_cost = round(rec_reorder * item["unit_cost"], 2)
            
            # Check for Sister Store Surplus for inter-store transfer
            cursor.execute("""
            SELECT i2.store_id, s2.name as store_name, i2.current_stock
            FROM inventory i2
            JOIN stores s2 ON i2.store_id = s2.store_id
            WHERE i2.sku = ? AND i2.store_id != ? AND i2.current_stock >= 40
            ORDER BY i2.current_stock DESC
            """, (item["sku"], item["store_id"]))
            surplus = cursor.fetchone()
            
            if surplus:
                rec_action = (
                    f"⚡ Transfer 25 units from {surplus['store_name']} (Surplus available: {surplus['current_stock']} units). "
                    f"Inter-store transfer takes ~24h vs {item['lead_time_days']}-day vendor lead time."
                )
                action_payload = {
                    "action_type": "TRANSFER",
                    "sku": item["sku"],
                    "product_name": item["product_name"],
                    "to_store_id": item["store_id"],
                    "to_store_name": item["store_name"],
                    "from_store_id": surplus["store_id"],
                    "from_store_name": surplus["store_name"],
                    "quantity": 25
                }
            else:
                rec_action = (
                    f"📝 Issue Purchase Order for {rec_reorder} units (${est_cost} total) immediately "
                    f"to prevent stockout before the {item['lead_time_days']}-day vendor lead time."
                )
                action_payload = {
                    "action_type": "REORDER_PO",
                    "sku": item["sku"],
                    "product_name": item["product_name"],
                    "store_id": item["store_id"],
                    "store_name": item["store_name"],
                    "quantity": rec_reorder,
                    "estimated_cost": est_cost
                }
                
            risks.append({
                "alert_type": "STOCKOUT_RISK",
                "severity": "CRITICAL" if is_critical else "WARNING",
                "store_id": item["store_id"],
                "store_name": item["store_name"],
                "sku": item["sku"],
                "product_name": item["product_name"],
                "category": item["category"],
                "current_stock": item["current_stock"],
                "daily_velocity": velocity_14d,
                "days_remaining": days_remaining,
                "projected_stockout_date": projected_stockout,
                "lead_time_days": item["lead_time_days"],
                "message": (
                    f"Likely stockout in {days_remaining} days! Current stock is {item['current_stock']} units with "
                    f"daily burn of {velocity_14d} units/day. Lead time is {item['lead_time_days']} days."
                ),
                "recommended_action": rec_action,
                "action_payload": action_payload,
                "data_assumptions": {
                    "current_stock": item["current_stock"],
                    "daily_velocity_14d": velocity_14d,
                    "days_remaining": days_remaining,
                    "lead_time_days": item["lead_time_days"],
                    "safety_buffer_days": 1.5,
                    "projected_stockout_date": projected_stockout,
                    "reorder_qty": rec_reorder,
                    "unit_cost": item["unit_cost"],
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
            
            rec_action = (
                f"🏷️ Apply 25% clearance markdown (reduce from ${item['unit_price']} to ${markdown_price}) "
                f"or cross-bundle with high-velocity category to liquidate ${tied_up} tied-up capital."
            )
            action_payload = {
                "action_type": "APPLY_MARKDOWN",
                "sku": item["sku"],
                "product_name": item["product_name"],
                "store_id": item["store_id"],
                "store_name": item["store_name"],
                "discount_pct": 25,
                "old_price": item["unit_price"],
                "new_price": markdown_price
            }
            
            dead_stock_list.append({
                "alert_type": "DEAD_STOCK",
                "severity": "CRITICAL" if tied_up >= 1000 else "WARNING",
                "store_id": item["store_id"],
                "store_name": item["store_name"],
                "sku": item["sku"],
                "product_name": item["product_name"],
                "category": item["category"],
                "current_stock": item["current_stock"],
                "sales_21d": sales_21d,
                "tied_up_capital": tied_up,
                "message": (
                    f"Zero sales recorded for {item['product_name']} over the last 21 days! "
                    f"{item['current_stock']} units sitting idle (${tied_up} tied-up capital)."
                ),
                "recommended_action": rec_action,
                "action_payload": action_payload,
                "data_assumptions": {
                    "idle_days": 21,
                    "units_sold_21d": 0,
                    "current_stock": item["current_stock"],
                    "unit_cost": item["unit_cost"],
                    "unit_price": item["unit_price"],
                    "tied_up_capital": tied_up,
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
                reorder_qty = int(item["target_stock"] * 1.5)
                rec_action = (
                    f"📈 Demand surge detected (+{pct_inc}% vs 30d baseline). "
                    f"Apply 1.5x surge reorder multiplier to replenish {reorder_qty} units before stock is depleted."
                )
                action_payload = {
                    "action_type": "REORDER_PO",
                    "sku": item["sku"],
                    "product_name": item["product_name"],
                    "store_id": item["store_id"],
                    "store_name": item["store_name"],
                    "quantity": reorder_qty
                }
                anomalies.append({
                    "alert_type": "SALES_SPIKE",
                    "severity": "CRITICAL" if ratio >= 3.0 else "WARNING",
                    "store_id": item["store_id"],
                    "store_name": item["store_name"],
                    "sku": item["sku"],
                    "product_name": item["product_name"],
                    "category": item["category"],
                    "current_stock": item["current_stock"],
                    "v_3d": v_3d,
                    "v_30d": v_30d,
                    "multiplier": ratio,
                    "message": (
                        f"Sales Spike! Daily sales surged by +{pct_inc}% over the last 3 days "
                        f"({v_3d} units/day vs 30d baseline of {v_30d} units/day)."
                    ),
                    "recommended_action": rec_action,
                    "action_payload": action_payload,
                    "data_assumptions": {
                        "velocity_3d": v_3d,
                        "velocity_30d_baseline": v_30d,
                        "spike_multiplier": ratio,
                        "percentage_increase": pct_inc,
                        "current_stock": item["current_stock"]
                    }
                })
            
            # Drop Detection (< 0.40x when baseline was significant)
            elif ratio <= 0.40 and v_30d >= 2.5:
                pct_dec = int((1.0 - ratio) * 100)
                rec_action = (
                    f"📉 Demand slump detected (-{pct_dec}% vs 30d baseline). "
                    f"Inspect shelf visibility, check competitor pricing, or run a 15% discount promo."
                )
                anomalies.append({
                    "alert_type": "SALES_DROP",
                    "severity": "WARNING",
                    "store_id": item["store_id"],
                    "store_name": item["store_name"],
                    "sku": item["sku"],
                    "product_name": item["product_name"],
                    "category": item["category"],
                    "current_stock": item["current_stock"],
                    "v_3d": v_3d,
                    "v_30d": v_30d,
                    "multiplier": ratio,
                    "message": (
                        f"Sales Slump! Daily sales dropped by -{pct_dec}% over the last 3 days "
                        f"({v_3d} units/day vs 30d baseline of {v_30d} units/day)."
                    ),
                    "recommended_action": rec_action,
                    "action_payload": {
                        "action_type": "INSPECT_PROMOTION",
                        "sku": item["sku"],
                        "product_name": item["product_name"],
                        "store_id": item["store_id"],
                        "store_name": item["store_name"]
                    },
                    "data_assumptions": {
                        "velocity_3d": v_3d,
                        "velocity_30d_baseline": v_30d,
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
    all_alerts = stockouts + dead_stocks + anomalies
    return sorted(all_alerts, key=lambda x: 0 if x["severity"] == "CRITICAL" else 1)

def get_category_breakdown(store_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    where = "WHERE s.store_id = ?" if store_id else ""
    params = (store_id,) if store_id else ()
    
    query = f"""
    SELECT p.category, 
           SUM(s.units_sold) as total_units,
           ROUND(SUM(s.revenue), 2) as total_revenue,
           ROUND(SUM(s.units_sold * p.unit_cost), 2) as total_cost,
           ROUND(SUM(s.revenue) - SUM(s.units_sold * p.unit_cost), 2) as gross_profit
    FROM daily_sales s
    JOIN products p ON s.sku = p.sku
    {where}
    GROUP BY p.category
    ORDER BY total_revenue DESC
    """
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_sales_velocity_trends(store_id: Optional[str] = None, days: int = 14) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    where = f"WHERE sale_date >= date('now', '-{days} days')"
    if store_id:
        where += f" AND store_id = '{store_id}'"
        
    query = f"""
    SELECT sale_date, SUM(units_sold) as units, ROUND(SUM(revenue), 2) as revenue
    FROM daily_sales
    {where}
    GROUP BY sale_date
    ORDER BY sale_date ASC
    """
    cursor.execute(query)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def execute_manager_action(action_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a store manager action:
    - TRANSFER: inter-store transfer
    - REORDER_PO: purchase order restock
    - APPLY_MARKDOWN: clearance price reduction
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    action_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        if action_type == "TRANSFER":
            from_store = payload["from_store_id"]
            to_store = payload["to_store_id"]
            sku = payload["sku"]
            qty = int(payload.get("quantity", 25))
            
            # Decrement from source
            cursor.execute("UPDATE inventory SET current_stock = MAX(0, current_stock - ?) WHERE store_id = ? AND sku = ?", (qty, from_store, sku))
            # Increment destination
            cursor.execute("UPDATE inventory SET current_stock = current_stock + ?, last_restocked = date('now') WHERE store_id = ? AND sku = ?", (qty, to_store, sku))
            
            details = f"Transferred {qty} units of {sku} from {from_store} to {to_store}."
            cursor.execute("INSERT INTO manager_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (action_id, now_str, action_type, sku, to_store, from_store, qty, details, "COMPLETED"))
            conn.commit()
            conn.close()
            return {"success": True, "action_id": action_id, "message": details}
            
        elif action_type == "REORDER_PO":
            store_id = payload["store_id"]
            sku = payload["sku"]
            qty = int(payload.get("quantity", 50))
            
            cursor.execute("UPDATE inventory SET current_stock = current_stock + ?, last_restocked = date('now') WHERE store_id = ? AND sku = ?", (qty, store_id, sku))
            details = f"Placed purchase order and received replenishment of {qty} units for {sku} at {store_id}."
            cursor.execute("INSERT INTO manager_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (action_id, now_str, action_type, sku, store_id, None, qty, details, "COMPLETED"))
            conn.commit()
            conn.close()
            return {"success": True, "action_id": action_id, "message": details}
            
        elif action_type == "APPLY_MARKDOWN":
            store_id = payload.get("store_id", "ALL")
            sku = payload["sku"]
            new_price = float(payload["new_price"])
            
            cursor.execute("UPDATE products SET unit_price = ? WHERE sku = ?", (new_price, sku))
            details = f"Applied clearance markdown for {sku} to new unit price ${new_price:.2f}."
            cursor.execute("INSERT INTO manager_actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (action_id, now_str, action_type, sku, store_id, None, 0, details, "COMPLETED"))
            conn.commit()
            conn.close()
            return {"success": True, "action_id": action_id, "message": details}
            
        else:
            conn.close()
            return {"success": False, "error": f"Unsupported action type: {action_type}"}
            
    except Exception as e:
        conn.close()
        return {"success": False, "error": str(e)}

def get_action_history() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM manager_actions ORDER BY created_at DESC LIMIT 20")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def query_database_facts(search_term: str) -> Dict[str, Any]:
    """Query exact facts for grounding plain language QA by matching catalogue products mentioned in search_term"""
    conn = get_db_connection()
    cursor = conn.cursor()
    term_lower = search_term.strip().lower()
    
    # Check all products to see if any product name or core keywords appear in the user's question
    cursor.execute("SELECT sku, name FROM products")
    all_prods = cursor.fetchall()
    matched_skus = []
    
    for row in all_prods:
        p_name_lower = row["name"].lower()
        p_sku_lower = row["sku"].lower()
        
        # Exact product name or SKU in query
        if p_name_lower in term_lower or p_sku_lower in term_lower:
            matched_skus.append(row["sku"])
            continue
            
        # Match significant keywords (e.g., 'milk', 'cheddar', 'yogurt', 'bread', 'croissant', 'cookware', 'shampoo')
        keywords = [
            w for w in p_name_lower.replace("-", " ").split() 
            if len(w) >= 4 and w not in ["whole", "fresh", "large", "pack", "piece", "liquid", "tubes"]
        ]
        # If at least one distinct keyword is present in user question
        if any(k in term_lower for k in keywords):
            matched_skus.append(row["sku"])
            
    if not matched_skus:
        conn.close()
        return {"products": [], "sales_facts_30d": []}
        
    placeholders = ",".join("?" for _ in matched_skus)
    cursor.execute(f"""
    SELECT p.sku, p.name, p.category, p.unit_cost, p.unit_price, p.reorder_point, p.lead_time_days,
           i.store_id, s.name as store_name, i.current_stock
    FROM products p
    JOIN inventory i ON p.sku = i.sku
    JOIN stores s ON i.store_id = s.store_id
    WHERE p.sku IN ({placeholders})
    ORDER BY p.name, s.name
    """, matched_skus)
    products = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute(f"""
    SELECT store_id, sku, SUM(units_sold) as total_units_30d, ROUND(SUM(revenue), 2) as total_revenue_30d
    FROM daily_sales
    WHERE sku IN ({placeholders}) AND sale_date >= date('now', '-30 days')
    GROUP BY store_id, sku
    """, matched_skus)
    sales_facts = [dict(row) for row in cursor.fetchall()]
        
    conn.close()
    return {
        "products": products,
        "sales_facts_30d": sales_facts
    }

def get_full_inventory_catalog(store_id: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns all catalogue products with stock levels, prices, and categories"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    where_clauses = []
    params = []
    if store_id:
        where_clauses.append("i.store_id = ?")
        params.append(store_id)
    if category:
        where_clauses.append("LOWER(p.category) LIKE ?")
        params.append(f"%{category.lower()}%")
        
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    
    cursor.execute(f"""
    SELECT p.sku, p.name, p.category, p.unit_cost, p.unit_price, p.reorder_point, p.target_stock, p.lead_time_days,
           i.store_id, s.name as store_name, i.current_stock
    FROM products p
    JOIN inventory i ON p.sku = i.sku
    JOIN stores s ON i.store_id = s.store_id
    {where_sql}
    ORDER BY p.category, p.name, s.name
    """, params)
    
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items

def get_top_performing_products(store_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
    """Returns top selling products by 90-day revenue and units"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    where_sql = "WHERE d.store_id = ?" if store_id else ""
    params = (store_id,) if store_id else ()
    
    cursor.execute(f"""
    SELECT p.sku, p.name, p.category, p.unit_price, p.unit_cost,
           SUM(d.units_sold) as total_units_sold,
           ROUND(SUM(d.revenue), 2) as total_revenue,
           ROUND(SUM(d.revenue) - SUM(d.units_sold * p.unit_cost), 2) as gross_margin
    FROM daily_sales d
    JOIN products p ON d.sku = p.sku
    {where_sql}
    GROUP BY p.sku
    ORDER BY total_revenue DESC
    LIMIT ?
    """, (*params, limit))
    
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items

def get_store_network_info() -> List[Dict[str, Any]]:
    """Returns overview of all stores with manager details and inventory summary"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT s.store_id, s.name, s.location, s.manager, s.phone, s.delivery_days,
           COUNT(DISTINCT i.sku) as sku_count,
           SUM(i.current_stock) as total_units,
           ROUND(SUM(i.current_stock * p.unit_cost), 2) as inventory_cost_val,
           ROUND(SUM(i.current_stock * p.unit_price), 2) as inventory_retail_val
    FROM stores s
    LEFT JOIN inventory i ON s.store_id = i.store_id
    LEFT JOIN products p ON i.sku = p.sku
    GROUP BY s.store_id
    ORDER BY s.store_id
    """)
    stores = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return stores

def get_all_policies() -> List[Dict[str, Any]]:
    """Returns all operational store policies"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT policy_id, category, title, description FROM store_policies ORDER BY policy_id")
    policies = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return policies
