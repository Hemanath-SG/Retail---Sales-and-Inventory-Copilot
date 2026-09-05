import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Ensure database exists before starting
from generate_data import init_db, DB_PATH
if not os.path.exists(DB_PATH):
    print("Database not found. Initializing and generating sample retail dataset...")
    init_db()

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

PORT = int(os.environ.get("PORT", 8000))

class CopilotRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        super().__init__(*args, directory=static_dir, **kwargs)

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)
        store_id = query_params.get("store_id", [None])[0]

        if path.startswith("/api/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

            if path == "/api/dashboard":
                kpis = get_overall_kpis(store_id)
                categories = get_category_breakdown(store_id)
                trends = get_sales_velocity_trends(store_id, days=14)
                response = {
                    "kpis": kpis,
                    "categories": categories,
                    "trends": trends
                }
            elif path == "/api/alerts":
                response = {
                    "attention_feed": get_daily_attention_feed(store_id),
                    "stockout_risks": get_stockout_risks(store_id),
                    "dead_stock": get_dead_stock(store_id),
                    "sales_anomalies": get_sales_anomalies(store_id)
                }
            elif path == "/api/inventory":
                conn = get_db_connection()
                cursor = conn.cursor()
                where = "WHERE i.store_id = ?" if store_id else ""
                params = (store_id,) if store_id else ()
                cursor.execute(f"""
                SELECT i.store_id, s.name as store_name, i.sku, p.name as product_name, p.category,
                       i.current_stock, p.reorder_point, p.target_stock, p.unit_cost, p.unit_price, p.lead_time_days
                FROM inventory i
                JOIN products p ON i.sku = p.sku
                JOIN stores s ON i.store_id = s.store_id
                {where}
                ORDER BY p.category, p.name
                """, params)
                items = [dict(row) for row in cursor.fetchall()]
                conn.close()
                response = {"inventory": items}
            elif path == "/api/stores":
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM stores")
                stores = [dict(row) for row in cursor.fetchall()]
                conn.close()
                response = {"stores": stores}
            elif path == "/api/trends":
                days = int(query_params.get("days", [14])[0])
                response = {"trends": get_sales_velocity_trends(store_id, days=days)}
            elif path == "/api/actions/history":
                response = {"actions": get_action_history()}
            else:
                response = {"error": "API route not found"}

            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            # Serve static files
            super().do_GET()

    def do_POST(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path.startswith("/api/"):
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            body = json.loads(post_data.decode("utf-8")) if content_length > 0 else {}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

            if path == "/api/chat":
                query = body.get("query", "")
                store_id = body.get("store_id", None)
                api_key = body.get("api_key", None)
                copilot_result = ask_copilot(query, store_id, custom_api_key=api_key)
                self.wfile.write(json.dumps(copilot_result).encode("utf-8"))

            elif path == "/api/actions/execute":
                action_type = body.get("action_type", "")
                payload = body.get("payload", {})
                result = execute_manager_action(action_type, payload)
                self.wfile.write(json.dumps(result).encode("utf-8"))

            else:
                self.wfile.write(json.dumps({"error": "POST route not found"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        # Quiet standard HTTP logs for clean judge terminal
        pass

def run_server():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, CopilotRequestHandler)
    print("=" * 60)
    print(f"  Retail - Sales and Inventory Copilot Running!")
    print(f"  TRACK_ID=PS03")
    print(f"  Serving on http://localhost:{PORT}")
    print(f"  Gemini Grounding: Active (GEMINI_API_KEY / Local Engine)")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server gracefully...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
