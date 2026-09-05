import sqlite3
import os
import json
import math
import random
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DATA_DIR, "retail_copilot.db")
EMBEDDINGS_PATH = os.path.join(DATA_DIR, "catalog_embeddings.json")

import hashlib

def generate_local_embedding(text: str, dim: int = 64) -> list[float]:
    """
    Deterministic normalized embedding generator for local semantic grounding.
    Uses character n-grams and md5 hashing to produce consistent, normalized 64-dim vectors
    compatible with offline cosine similarity search across all Python runs.
    """
    vec = [0.0] * dim
    words = text.lower().replace("-", " ").split()
    for word in words:
        for i in range(len(word)):
            token = word[i:i+3]
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            vec[idx] += 1.0 + (len(token) * 0.2)
    
    # Normalize vector to unit length
    magnitude = math.sqrt(sum(x * x for x in vec))
    if magnitude > 0:
        vec = [round(x / magnitude, 5) for x in vec]
    return vec

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Stores Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stores (
        store_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        location TEXT NOT NULL,
        manager TEXT NOT NULL,
        phone TEXT,
        delivery_days TEXT
    );
    """)
    
    # 2. Products Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        sku TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_cost REAL NOT NULL,
        unit_price REAL NOT NULL,
        reorder_point INTEGER NOT NULL,
        target_stock INTEGER NOT NULL,
        lead_time_days INTEGER NOT NULL,
        is_perishable INTEGER DEFAULT 0
    );
    """)
    
    # 3. Inventory Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        store_id TEXT,
        sku TEXT,
        current_stock INTEGER NOT NULL,
        reserved_stock INTEGER DEFAULT 0,
        last_restocked TEXT,
        PRIMARY KEY (store_id, sku),
        FOREIGN KEY (store_id) REFERENCES stores(store_id),
        FOREIGN KEY (sku) REFERENCES products(sku)
    );
    """)
    
    # 4. Daily Sales Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_sales (
        sale_date TEXT,
        store_id TEXT,
        sku TEXT,
        units_sold INTEGER NOT NULL,
        revenue REAL NOT NULL,
        PRIMARY KEY (sale_date, store_id, sku),
        FOREIGN KEY (store_id) REFERENCES stores(store_id),
        FOREIGN KEY (sku) REFERENCES products(sku)
    );
    """)
    
    # 5. Store Operational Policies Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS store_policies (
        policy_id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        parameters_json TEXT NOT NULL
    );
    """)

    # 6. Manager Executed Actions Audit Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS manager_actions (
        action_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        action_type TEXT NOT NULL,
        sku TEXT NOT NULL,
        store_id TEXT NOT NULL,
        donor_store_id TEXT,
        quantity INTEGER NOT NULL,
        details TEXT NOT NULL,
        status TEXT NOT NULL
    );
    """)
    
    # Insert Stores
    stores = [
        ("STORE-001", "Downtown Metro Store", "12 Main St, City Center", "Sarah Jenkins", "+1-555-0101", "Mon, Wed, Fri"),
        ("STORE-002", "Suburban Mall Branch", "45 Park Ave, Grand Mall", "David Chen", "+1-555-0102", "Tue, Thu, Sat"),
        ("STORE-003", "Westside Express Mart", "88 West Blvd, University Quarter", "Elena Rostova", "+1-555-0103", "Daily")
    ]
    cursor.executemany("INSERT INTO stores VALUES (?, ?, ?, ?, ?, ?);", stores)
    
    # Insert Products
    # SKU, Name, Category, Unit Cost, Unit Price, Reorder Point, Target Stock, Lead Time (Days), is_perishable
    products = [
        ("MILK-ORG-1L", "Organic Whole Milk 1L", "Fresh Produce & Dairy", 2.10, 3.89, 25, 100, 3, 1),
        ("CHEDDAR-250G", "Aged Sharp Cheddar 250g", "Fresh Produce & Dairy", 3.20, 5.99, 15, 60, 4, 1),
        ("GREEK-YOG-500G", "Plain Greek Yogurt 500g", "Fresh Produce & Dairy", 2.40, 4.49, 20, 80, 2, 1),
        ("EGGS-FREE-12P", "Free-Range Large Eggs 12pk", "Fresh Produce & Dairy", 2.80, 4.99, 30, 120, 3, 1),
        ("OAT-MILK-1L", "Barista Oat Milk 1L", "Fresh Produce & Dairy", 2.50, 4.79, 20, 75, 4, 0),
        
        ("BAKERY-ART-BREAD", "Artisan Sourdough Loaf", "Bakery & Breakfast", 2.00, 5.49, 15, 50, 2, 1),
        ("CROISSANT-4PK", "Butter Croissants 4pk", "Bakery & Breakfast", 2.80, 5.99, 12, 40, 2, 1),
        ("OATS-ROLLED-1KG", "Rolled Whole Oats 1kg", "Bakery & Breakfast", 1.90, 3.99, 15, 60, 5, 0),
        
        ("BEV-SODA-6P", "Sparkling Citrus Soda 6-Pack", "Beverages & Snacks", 3.00, 6.49, 30, 120, 3, 0),
        ("BEV-ENERGY-500ML", "Volt Energy Drink 500ml", "Beverages & Snacks", 1.10, 2.99, 40, 150, 2, 0),
        ("CHIPS-SEA-SALT", "Kettle Sea Salt Chips 150g", "Beverages & Snacks", 1.40, 3.29, 25, 100, 4, 0),
        ("ALMONDS-ROAST-200G", "Roasted Salted Almonds 200g", "Beverages & Snacks", 3.50, 7.49, 15, 50, 5, 0),
        ("DARK-CHOC-100G", "70% Dark Chocolate Bar 100g", "Beverages & Snacks", 1.80, 3.99, 20, 80, 5, 0),
        
        ("SHAMPOO-ARGAN", "Argan Oil Shampoo 400ml", "Personal Care & Pharmacy", 4.20, 8.99, 10, 40, 7, 0),
        ("HAND-SOAP-500ML", "Lavender Hand Soap 500ml", "Personal Care & Pharmacy", 1.50, 3.49, 20, 80, 5, 0),
        ("TOOTHPASTE-MINT", "Mint Fluoride Toothpaste 100ml", "Personal Care & Pharmacy", 1.80, 3.99, 15, 60, 6, 0),
        
        ("COOKWARE-5P-SET", "5-Piece Non-Stick Cookware Set", "Home & Kitchen", 45.00, 89.99, 5, 20, 10, 0),
        ("DISH-SOAP-1L", "Lemon Dishwashing Liquid 1L", "Home & Kitchen", 1.60, 3.79, 25, 90, 4, 0),
        ("PAPER-TOWEL-6PK", "Ultra Absorbent Paper Towels 6pk", "Home & Kitchen", 4.50, 9.49, 20, 80, 5, 0),
        ("STORAGE-BOX-3PK", "Clear Plastic Storage Tubs 3pk", "Home & Kitchen", 6.80, 14.99, 10, 35, 7, 0)
    ]
    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);", products)
    
    # Insert Store Operational Policies
    policies = [
        (
            "POL-001", "Stockout Prevention", "Lead-Time Safety Buffer Rule",
            "A product is flagged for urgent replenishment when Days of Inventory Remaining (DIR) is less than or equal to lead time plus 1.5 days safety buffer. DIR is computed as current stock divided by 14-day average daily sales velocity.",
            json.dumps({"safety_buffer_days": 1.5, "velocity_window_days": 14})
        ),
        (
            "POL-002", "Inter-Store Rebalancing", "Priority Sister-Store Transfer Rule",
            "Before issuing external vendor purchase orders, check if another store in the network holds surplus inventory (defined as current stock >= 40 units and DIR >= 15 days). If surplus exists, recommend an emergency transfer of 20 to 30 units to minimize stockout lead-time.",
            json.dumps({"min_surplus_units": 40, "min_surplus_dir": 15, "default_transfer_qty": 25})
        ),
        (
            "POL-003", "Dead Stock Clearance", "21-Day Zero-Movement Markdown Rule",
            "Inventory items with zero sales in the preceding 21 days are classified as Dead Stock. To liquidate tied-up capital and free shelf space, recommend a 25% clearance markdown or promotional product bundling.",
            json.dumps({"idle_days_threshold": 21, "markdown_pct": 25})
        ),
        (
            "POL-004", "Demand Spikes", "Surge Velocity Multiplier Rule",
            "When 3-day sales velocity exceeds 2.0x the 30-day baseline average, flag a Sales Spike. Recommend a 1.5x multiplier on next purchase order to prevent unexpected run-out.",
            json.dumps({"spike_ratio_threshold": 2.0, "reorder_multiplier": 1.5})
        ),
        (
            "POL-005", "Demand Drops", "Slump Investigation Rule",
            "When 3-day sales velocity falls below 0.35x the 30-day baseline average for an active product, flag a Sales Drop. Recommend immediate price check, shelf inspection, and short-term promo.",
            json.dumps({"drop_ratio_threshold": 0.35})
        )
    ]
    cursor.executemany("INSERT INTO store_policies VALUES (?, ?, ?, ?, ?);", policies)
    
    # Insert Initial Inventory Data with deliberate edge cases
    today = datetime.now()
    inventory_data = [
        # Store 1: Downtown Metro
        ("STORE-001", "MILK-ORG-1L", 14, 0, (today - timedelta(days=5)).strftime("%Y-%m-%d")), # CRITICAL STOCKOUT: stock 14, velocity ~11.8/day, lead time 3d
        ("STORE-001", "CHEDDAR-250G", 45, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")),
        ("STORE-001", "GREEK-YOG-500G", 55, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")),
        ("STORE-001", "EGGS-FREE-12P", 80, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")),
        ("STORE-001", "OAT-MILK-1L", 40, 0, (today - timedelta(days=3)).strftime("%Y-%m-%d")),
        ("STORE-001", "BAKERY-ART-BREAD", 35, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")), # SALES DROP ANOMALY
        ("STORE-001", "CROISSANT-4PK", 22, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")),
        ("STORE-001", "OATS-ROLLED-1KG", 50, 0, (today - timedelta(days=10)).strftime("%Y-%m-%d")),
        ("STORE-001", "BEV-SODA-6P", 95, 0, (today - timedelta(days=4)).strftime("%Y-%m-%d")),
        ("STORE-001", "BEV-ENERGY-500ML", 110, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")),
        ("STORE-001", "CHIPS-SEA-SALT", 65, 0, (today - timedelta(days=3)).strftime("%Y-%m-%d")),
        ("STORE-001", "ALMONDS-ROAST-200G", 30, 0, (today - timedelta(days=8)).strftime("%Y-%m-%d")),
        ("STORE-001", "DARK-CHOC-100G", 45, 0, (today - timedelta(days=5)).strftime("%Y-%m-%d")),
        ("STORE-001", "SHAMPOO-ARGAN", 25, 0, (today - timedelta(days=12)).strftime("%Y-%m-%d")),
        ("STORE-001", "HAND-SOAP-500ML", 60, 0, (today - timedelta(days=6)).strftime("%Y-%m-%d")),
        ("STORE-001", "TOOTHPASTE-MINT", 40, 0, (today - timedelta(days=7)).strftime("%Y-%m-%d")),
        ("STORE-001", "COOKWARE-5P-SET", 8, 0, (today - timedelta(days=20)).strftime("%Y-%m-%d")),
        ("STORE-001", "DISH-SOAP-1L", 70, 0, (today - timedelta(days=4)).strftime("%Y-%m-%d")),
        ("STORE-001", "PAPER-TOWEL-6PK", 50, 0, (today - timedelta(days=3)).strftime("%Y-%m-%d")),
        ("STORE-001", "STORAGE-BOX-3PK", 20, 0, (today - timedelta(days=15)).strftime("%Y-%m-%d")),
        
        # Store 2: Suburban Mall Branch
        ("STORE-002", "MILK-ORG-1L", 85, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")), # SURPLUS FOR TRANSFER (85 units available)
        ("STORE-002", "CHEDDAR-250G", 30, 0, (today - timedelta(days=4)).strftime("%Y-%m-%d")),
        ("STORE-002", "GREEK-YOG-500G", 40, 0, (today - timedelta(days=3)).strftime("%Y-%m-%d")),
        ("STORE-002", "EGGS-FREE-12P", 60, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")),
        ("STORE-002", "OAT-MILK-1L", 35, 0, (today - timedelta(days=4)).strftime("%Y-%m-%d")),
        ("STORE-002", "BAKERY-ART-BREAD", 18, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")),
        ("STORE-002", "CROISSANT-4PK", 15, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")),
        ("STORE-002", "OATS-ROLLED-1KG", 30, 0, (today - timedelta(days=12)).strftime("%Y-%m-%d")),
        ("STORE-002", "BEV-SODA-6P", 70, 0, (today - timedelta(days=5)).strftime("%Y-%m-%d")),
        ("STORE-002", "BEV-ENERGY-500ML", 80, 0, (today - timedelta(days=3)).strftime("%Y-%m-%d")),
        ("STORE-002", "CHIPS-SEA-SALT", 50, 0, (today - timedelta(days=4)).strftime("%Y-%m-%d")),
        ("STORE-002", "ALMONDS-ROAST-200G", 22, 0, (today - timedelta(days=9)).strftime("%Y-%m-%d")),
        ("STORE-002", "DARK-CHOC-100G", 35, 0, (today - timedelta(days=6)).strftime("%Y-%m-%d")),
        ("STORE-002", "SHAMPOO-ARGAN", 18, 0, (today - timedelta(days=14)).strftime("%Y-%m-%d")),
        ("STORE-002", "HAND-SOAP-500ML", 45, 0, (today - timedelta(days=7)).strftime("%Y-%m-%d")),
        ("STORE-002", "TOOTHPASTE-MINT", 30, 0, (today - timedelta(days=8)).strftime("%Y-%m-%d")),
        ("STORE-002", "COOKWARE-5P-SET", 38, 0, (today - timedelta(days=25)).strftime("%Y-%m-%d")), # CRITICAL DEAD STOCK: 38 units, 0 sales in 21 days
        ("STORE-002", "DISH-SOAP-1L", 55, 0, (today - timedelta(days=5)).strftime("%Y-%m-%d")),
        ("STORE-002", "PAPER-TOWEL-6PK", 40, 0, (today - timedelta(days=4)).strftime("%Y-%m-%d")),
        ("STORE-002", "STORAGE-BOX-3PK", 15, 0, (today - timedelta(days=18)).strftime("%Y-%m-%d")),

        # Store 3: Westside Express Mart
        ("STORE-003", "MILK-ORG-1L", 40, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")),
        ("STORE-003", "CHEDDAR-250G", 20, 0, (today - timedelta(days=3)).strftime("%Y-%m-%d")),
        ("STORE-003", "GREEK-YOG-500G", 30, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")),
        ("STORE-003", "EGGS-FREE-12P", 50, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")),
        ("STORE-003", "OAT-MILK-1L", 25, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")),
        ("STORE-003", "BAKERY-ART-BREAD", 12, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")),
        ("STORE-003", "CROISSANT-4PK", 10, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")),
        ("STORE-003", "OATS-ROLLED-1KG", 20, 0, (today - timedelta(days=8)).strftime("%Y-%m-%d")),
        ("STORE-003", "BEV-SODA-6P", 40, 0, (today - timedelta(days=3)).strftime("%Y-%m-%d")),
        ("STORE-003", "BEV-ENERGY-500ML", 18, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")), # CRITICAL SPIKE CASE: High velocity, low stock
        ("STORE-003", "CHIPS-SEA-SALT", 35, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")),
        ("STORE-003", "ALMONDS-ROAST-200G", 15, 0, (today - timedelta(days=6)).strftime("%Y-%m-%d")),
        ("STORE-003", "DARK-CHOC-100G", 25, 0, (today - timedelta(days=4)).strftime("%Y-%m-%d")),
        ("STORE-003", "SHAMPOO-ARGAN", 12, 0, (today - timedelta(days=10)).strftime("%Y-%m-%d")),
        ("STORE-003", "HAND-SOAP-500ML", 30, 0, (today - timedelta(days=5)).strftime("%Y-%m-%d")),
        ("STORE-003", "TOOTHPASTE-MINT", 20, 0, (today - timedelta(days=6)).strftime("%Y-%m-%d")),
        ("STORE-003", "COOKWARE-5P-SET", 4, 0, (today - timedelta(days=30)).strftime("%Y-%m-%d")),
        ("STORE-003", "DISH-SOAP-1L", 35, 0, (today - timedelta(days=3)).strftime("%Y-%m-%d")),
        ("STORE-003", "PAPER-TOWEL-6PK", 25, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")),
        ("STORE-003", "STORAGE-BOX-3PK", 10, 0, (today - timedelta(days=12)).strftime("%Y-%m-%d"))
    ]
    cursor.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?);", inventory_data)
    
    # 90 Days Daily Sales Data
    random.seed(42)
    sales_rows = []
    start_date = today - timedelta(days=90)
    
    for day_idx in range(91):
        current_date = (start_date + timedelta(days=day_idx)).strftime("%Y-%m-%d")
        is_recent_3_days = (day_idx >= 88)
        is_last_21_days = (day_idx >= 65)
        
        for store in ["STORE-001", "STORE-002", "STORE-003"]:
            for sku, name, cat, cost, price, r_pt, t_st, lead_t, is_per in products:
                
                # Baseline velocity
                if "Fresh" in cat or "Bakery" in cat:
                    base_sales = random.randint(8, 15) if store == "STORE-001" else random.randint(4, 10)
                elif "Beverages" in cat:
                    base_sales = random.randint(12, 22) if store == "STORE-001" else random.randint(6, 14)
                elif "Personal" in cat:
                    base_sales = random.randint(2, 6)
                else:
                    base_sales = random.randint(1, 4)
                
                # --- Inject Hackathon Test Cases ---
                
                # 1. Milk Organic 1L at Downtown: High steady velocity ~12-14 units/day
                if store == "STORE-001" and sku == "MILK-ORG-1L":
                    units = random.randint(11, 15)
                
                # 2. Dead stock: Cookware set at Suburban Mall has 0 sales in last 21 days
                elif store == "STORE-002" and sku == "COOKWARE-5P-SET" and is_last_21_days:
                    units = 0
                
                # 3. Sales Spike: Volt Energy Drink at Express Mart spiked to 35 units/day in last 3 days
                elif store == "STORE-003" and sku == "BEV-ENERGY-500ML" and is_recent_3_days:
                    units = random.randint(32, 38)
                
                # 4. Sales Drop: Artisan Sourdough Bread at Downtown dropped to 0-2 units/day in last 7 days
                elif store == "STORE-001" and sku == "BAKERY-ART-BREAD" and day_idx >= 84:
                    units = random.randint(0, 2)
                
                else:
                    # Weekend demand uplift
                    date_obj = datetime.strptime(current_date, "%Y-%m-%d")
                    if date_obj.weekday() in (5, 6):
                        base_sales = int(base_sales * 1.35)
                    units = max(0, int(random.gauss(base_sales, 2)))
                
                revenue = round(units * price, 2)
                sales_rows.append((current_date, store, sku, units, revenue))
                
    cursor.executemany("INSERT INTO daily_sales VALUES (?, ?, ?, ?, ?);", sales_rows)
    conn.commit()
    conn.close()
    print(f"Database successfully generated at: {DB_PATH}")

    # Generate Precomputed Embeddings for Products & Policies
    catalog_corpus = []
    for sku, name, cat, cost, price, r_pt, t_st, lead_t, is_per in products:
        text = f"Product: {name}. SKU: {sku}. Category: {cat}. Price: ${price}. Lead Time: {lead_t} days."
        catalog_corpus.append({
            "id": sku,
            "type": "product",
            "title": name,
            "text": text,
            "vector": generate_local_embedding(text)
        })
    for pol_id, cat, title, desc, params in policies:
        text = f"Policy {pol_id}: {title}. Category: {cat}. {desc}"
        catalog_corpus.append({
            "id": pol_id,
            "type": "policy",
            "title": title,
            "text": text,
            "vector": generate_local_embedding(text)
        })
        
    with open(EMBEDDINGS_PATH, "w") as f:
        json.dump(catalog_corpus, f, indent=2)
    print(f"Catalog embeddings generated at: {EMBEDDINGS_PATH}")

if __name__ == "__main__":
    init_db()
