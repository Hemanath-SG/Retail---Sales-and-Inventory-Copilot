import unittest
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.analytics_engine import (
    get_overall_kpis,
    get_stockout_risks,
    get_dead_stock,
    get_sales_anomalies,
    get_daily_attention_feed,
    get_category_breakdown,
    get_sales_velocity_trends,
    execute_manager_action,
    get_action_history,
    get_db_connection
)
from src.copilot import ask_copilot
from src.vector_store import search_catalog_knowledge

class TestRetailCopilot(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from generate_data import init_db
        init_db()

    def test_01_overall_kpis(self):
        kpis = get_overall_kpis()
        self.assertIn("total_stores", kpis)
        self.assertEqual(kpis["total_stores"], 3)
        self.assertGreater(kpis["total_revenue_90d"], 10000.0)
        self.assertEqual(kpis["total_skus"], 20)
        print("[OK] Overall KPIs test passed.")

    def test_02_stockout_risks(self):
        risks = get_stockout_risks()
        self.assertIsInstance(risks, list)
        self.assertGreater(len(risks), 0)
        
        # Check Organic Whole Milk stockout risk at Downtown Store
        milk_risk = next((r for r in risks if "MILK-ORG-1L" in r["sku"] and r["store_id"] == "STORE-001"), None)
        self.assertIsNotNone(milk_risk, "Organic Milk stockout risk should be flagged")
        self.assertIn(milk_risk["severity"], ["CRITICAL", "WARNING"])
        self.assertLessEqual(milk_risk["days_remaining"], 4.5)
        self.assertIn("recommended_action", milk_risk)
        self.assertIn("action_payload", milk_risk)
        
        # Check that inter-store transfer surplus was detected from STORE-002
        self.assertEqual(milk_risk["action_payload"]["action_type"], "TRANSFER")
        self.assertEqual(milk_risk["action_payload"]["from_store_id"], "STORE-002")
        print(f"[OK] Stockout risks verified ({len(risks)} flagged items, transfer recommendation detected).")

    def test_03_dead_stock(self):
        dead = get_dead_stock()
        self.assertIsInstance(dead, list)
        self.assertGreater(len(dead), 0)
        
        # Check Cookware set dead stock at Suburban Mall
        cookware = next((d for d in dead if "COOKWARE" in d["sku"] and d["store_id"] == "STORE-002"), None)
        self.assertIsNotNone(cookware, "Cookware set at STORE-002 should be flagged as dead stock")
        self.assertEqual(cookware["sales_21d"], 0)
        self.assertEqual(cookware["tied_up_capital"], 38 * 45.00) # 38 units * $45 cost
        self.assertIn("APPLY_MARKDOWN", cookware["action_payload"]["action_type"])
        print(f"[OK] Dead stock test passed. Found ${cookware['tied_up_capital']} tied up in idle cookware.")

    def test_04_sales_anomalies(self):
        anomalies = get_sales_anomalies()
        self.assertIsInstance(anomalies, list)
        self.assertGreater(len(anomalies), 0)
        
        # 1. Sales Spike: Volt Energy Drink at Express Mart
        spike = next((a for a in anomalies if a["alert_type"] == "SALES_SPIKE" and "BEV-ENERGY" in a["sku"]), None)
        self.assertIsNotNone(spike, "Volt Energy Drink sales spike should be detected")
        self.assertGreaterEqual(spike["multiplier"], 2.0)
        
        # 2. Sales Drop: Artisan Sourdough Bread at Downtown Store
        drop = next((a for a in anomalies if a["alert_type"] == "SALES_DROP" and "BAKERY-ART-BREAD" in a["sku"]), None)
        self.assertIsNotNone(drop, "Artisan Bread sales drop should be detected")
        self.assertLessEqual(drop["multiplier"], 0.35)
        print(f"[OK] Sales anomalies verified (Spike: {spike['multiplier']}x, Drop: {drop['multiplier']}x).")

    def test_05_daily_attention_feed(self):
        feed = get_daily_attention_feed()
        self.assertIsInstance(feed, list)
        self.assertGreater(len(feed), 0)
        # Verify sorted: CRITICAL first
        severities = [item["severity"] for item in feed]
        if "CRITICAL" in severities and "WARNING" in severities:
            first_crit = severities.index("CRITICAL")
            first_warn = severities.index("WARNING")
            self.assertLess(first_crit, first_warn)
        print("[OK] Daily attention feed prioritization passed.")

    def test_06_category_breakdown_and_trends(self):
        categories = get_category_breakdown()
        self.assertGreaterEqual(len(categories), 4)
        for cat in categories:
            self.assertIn("category", cat)
            self.assertIn("total_revenue", cat)
            self.assertIn("gross_profit", cat)

        trends = get_sales_velocity_trends(days=14)
        self.assertGreaterEqual(len(trends), 10)
        for t in trends:
            self.assertIn("sale_date", t)
            self.assertIn("units", t)
        print("[OK] Category breakdown and 14-day velocity trends passed.")

    def test_07_action_execution_lifecycle(self):
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get baseline stock for MILK-ORG-1L
        cursor.execute("SELECT current_stock FROM inventory WHERE store_id = 'STORE-001' AND sku = 'MILK-ORG-1L'")
        stock_dt_before = cursor.fetchone()["current_stock"]
        cursor.execute("SELECT current_stock FROM inventory WHERE store_id = 'STORE-002' AND sku = 'MILK-ORG-1L'")
        stock_sub_before = cursor.fetchone()["current_stock"]
        conn.close()

        # Execute 25 unit transfer from STORE-002 to STORE-001
        payload = {
            "from_store_id": "STORE-002",
            "to_store_id": "STORE-001",
            "sku": "MILK-ORG-1L",
            "quantity": 25
        }
        res = execute_manager_action("TRANSFER", payload)
        self.assertTrue(res["success"])
        self.assertIn("action_id", res)

        # Verify stock levels updated
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT current_stock FROM inventory WHERE store_id = 'STORE-001' AND sku = 'MILK-ORG-1L'")
        stock_dt_after = cursor.fetchone()["current_stock"]
        cursor.execute("SELECT current_stock FROM inventory WHERE store_id = 'STORE-002' AND sku = 'MILK-ORG-1L'")
        stock_sub_after = cursor.fetchone()["current_stock"]
        conn.close()

        self.assertEqual(stock_dt_after, stock_dt_before + 25)
        self.assertEqual(stock_sub_after, stock_sub_before - 25)

        # Verify action history audit log
        history = get_action_history()
        self.assertGreater(len(history), 0)
        latest_act = history[0]
        self.assertEqual(latest_act["action_type"], "TRANSFER")
        self.assertEqual(latest_act["sku"], "MILK-ORG-1L")
        print("[OK] Action execution lifecycle and audit logging passed.")

    def test_08_vector_store_retrieval(self):
        results = search_catalog_knowledge("milk stockout reorder buffer", top_k=3)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        titles = [r["title"] for r in results]
        # Should retrieve milk product or stockout buffer policy
        has_relevant = any("Milk" in t or "Buffer" in t or "Stockout" in t for t in titles)
        self.assertTrue(has_relevant)
        print(f"[OK] Vector store semantic retrieval passed (Retrieved: {titles}).")

    def test_09_copilot_grounded_queries(self):
        # 1. Stockout query
        res1 = ask_copilot("What is running out today?")
        self.assertIn("answer", res1)
        self.assertIn("stockout", res1["intent"])
        self.assertIn("units", res1["answer"].lower())

        # 2. Dead stock query
        res2 = ask_copilot("What is overstocked?")
        self.assertIn("answer", res2)
        self.assertIn("dead_stock", res2["intent"])
        self.assertIn("$", res2["answer"])

        # 3. Product monthly performance query
        res3 = ask_copilot("How did Organic Milk do this month?")
        self.assertIn("answer", res3)
        self.assertIn("product_lookup", res3["intent"])
        self.assertIn("30-day", res3["answer"].lower())

        # 4. Out-of-scope query refusal test
        res4 = ask_copilot("Do you sell MacBook Pro laptops?")
        self.assertIn("answer", res4)
        self.assertEqual(res4["intent"], "out_of_scope")
        self.assertIn("cannot answer", res4["answer"].lower())
        print("[OK] Copilot grounding, intent routing, and refusal tests passed.")

    def test_10_expanded_copilot_intents(self):
        # 1. Full Inventory Catalog Inquiry (The user's exact question!)
        res1 = ask_copilot("what are the things in the inventory?")
        self.assertEqual(res1["intent"], "inventory_catalog")
        self.assertIn("Store Inventory Catalogue", res1["answer"])
        self.assertIn("Fresh Produce & Dairy", res1["answer"])

        # 2. Top Performing Best Sellers
        res2 = ask_copilot("What are our best selling products?")
        self.assertEqual(res2["intent"], "top_performers")
        self.assertIn("Top 5 Best-Selling Products", res2["answer"])

        # 3. Store Network & Managers
        res3 = ask_copilot("Tell me about our stores and managers")
        self.assertEqual(res3["intent"], "stores_overview")
        self.assertIn("Downtown Metro Store", res3["answer"])
        self.assertIn("Sarah Jenkins", res3["answer"])

        # 4. Store Policies
        res4 = ask_copilot("What are our store operational policies?")
        self.assertEqual(res4["intent"], "policies_overview")
        self.assertIn("Standard Operating Policies", res4["answer"])
        print("[OK] Expanded Copilot intents (Inventory Catalogue, Best Sellers, Stores, Policies) passed.")

if __name__ == "__main__":
    unittest.main()
