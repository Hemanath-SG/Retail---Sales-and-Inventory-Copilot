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
    get_daily_attention_feed
)
from src.copilot import ask_copilot

class TestRetailCopilot(unittest.TestCase):

    def test_overall_kpis(self):
        kpis = get_overall_kpis()
        self.assertIn("total_stores", kpis)
        self.assertEqual(kpis["total_stores"], 3)
        self.assertGreater(kpis["total_revenue_90d"], 0)
        print("[OK] Overall KPIs test passed.")

    def test_stockout_risks(self):
        risks = get_stockout_risks()
        self.assertIsInstance(risks, list)
        self.assertGreater(len(risks), 0)
        # Check Organic Milk stockout risk
        milk_risk = next((r for r in risks if "MILK-ORG-1L" in r["sku"]), None)
        self.assertIsNotNone(milk_risk)
        self.assertEqual(milk_risk["severity"], "HIGH")
        self.assertIn("recommended_action", milk_risk)
        print(f"[OK] Stockout risk test passed. Found {len(risks)} risks.")
 
    def test_dead_stock(self):
        dead = get_dead_stock()
        self.assertIsInstance(dead, list)
        self.assertGreater(len(dead), 0)
        # Check Cookware set dead stock
        cookware = next((d for d in dead if "COOKWARE" in d["sku"]), None)
        self.assertIsNotNone(cookware)
        self.assertEqual(cookware["sales_21d"], 0)
        print(f"[OK] Dead stock test passed. Found {len(dead)} dead stock items.")
 
    def test_sales_anomalies(self):
        anomalies = get_sales_anomalies()
        self.assertIsInstance(anomalies, list)
        self.assertGreater(len(anomalies), 0)
        print(f"[OK] Sales anomalies test passed. Found {len(anomalies)} anomalies.")
 
    def test_copilot_queries(self):
        # 1. Stockout query
        res1 = ask_copilot("What is running out today?")
        self.assertIn("answer", res1)
        self.assertIn("STOCKOUT_RISK", json.dumps(res1["grounded_data"]))

        # 2. Dead stock query
        res2 = ask_copilot("What is overstocked?")
        self.assertIn("answer", res2)

        # 3. Out-of-scope query
        res3 = ask_copilot("What is the price of iPhone 15?")
        self.assertIn("cannot answer", res3["answer"].lower())

        print("[OK] Copilot query routing & grounding tests passed.")

if __name__ == "__main__":
    unittest.main()
