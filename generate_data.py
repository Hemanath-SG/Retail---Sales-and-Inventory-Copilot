import sqlite3
import os
import random
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DATA_DIR, "retail_copilot.db")

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Stores Table
    cursor.execute("""
    CREATE TABLE stores (
        store_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        location TEXT NOT NULL,
        manager TEXT NOT NULL
    );
    """)
    
    # 2. Products Table
    cursor.execute("""
    CREATE TABLE products (
        sku TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_cost REAL NOT NULL,
        unit_price REAL NOT NULL,
        reorder_point INTEGER NOT NULL,
        target_stock INTEGER NOT NULL,
        lead_time_days INTEGER NOT NULL
    );
    """)
    
    # 3. Inventory Table
    cursor.execute("""
    CREATE TABLE inventory (
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
    CREATE TABLE daily_sales (
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
    
    # Insert Stores
    stores = [
        ("STORE-001", "Downtown Metro Store", "12 Main St, City Center", "Sarah Jenkins"),
        ("STORE-002", "Suburban Mall Branch", "45 Park Ave, Grand Mall", "David Chen"),
        ("STORE-003", "Westside Express Mart", "88 West Blvd, University Quarter", "Elena Rostova")
    ]
    cursor.executemany("INSERT INTO stores VALUES (?, ?, ?, ?);", stores)
    
    # Insert Products
    products = [
        # SKU, Name, Category, Unit Cost, Unit Price, Reorder Point, Target Stock, Lead Time (Days)
        ("MILK-ORG-1L", "Organic Whole Milk 1L", "Fresh Produce & Dairy", 2.10, 3.89, 25, 100, 3),
        ("CHEDDAR-250G", "Aged Sharp Cheddar 250g", "Fresh Produce & Dairy", 3.20, 5.99, 15, 60, 4),
        ("GREEK-YOG-500G", "Plain Greek Yogurt 500g", "Fresh Produce & Dairy", 2.40, 4.49, 20, 80, 2),
        ("EGGS-FREE-12P", "Free-Range Large Eggs 12pk", "Fresh Produce & Dairy", 2.80, 4.99, 30, 120, 3),
        ("OAT-MILK-1L", "Barista Oat Milk 1L", "Fresh Produce & Dairy", 2.50, 4.79, 20, 75, 4),
        
        ("BAKERY-ART-BREAD", "Artisan Sourdough Loaf", "Bakery & Breakfast", 2.00, 5.49, 15, 50, 2),
        ("CROISSANT-4PK", "Butter Croissants 4pk", "Bakery & Breakfast", 2.80, 5.99, 12, 40, 2),
        ("OATS-ROLLED-1KG", "Rolled Whole Oats 1kg", "Bakery & Breakfast", 1.90, 3.99, 15, 60, 5),
        
        ("BEV-SODA-6P", "Sparkling Citrus Soda 6-Pack", "Beverages & Snacks", 3.00, 6.49, 30, 120, 3),
        ("BEV-ENERGY-500ML", "Volt Energy Drink 500ml", "Beverages & Snacks", 1.10, 2.99, 40, 150, 2),
        ("CHIPS-SEA-SALT", "Kettle Sea Salt Chips 150g", "Beverages & Snacks", 1.40, 3.29, 25, 100, 4),
        ("ALMONDS-ROAST-200G", "Roasted Salted Almonds 200g", "Beverages & Snacks", 3.50, 7.49, 15, 50, 5),
        ("DARK-CHOC-100G", "70% Dark Chocolate Bar 100g", "Beverages & Snacks", 1.80, 3.99, 20, 80, 5),
        
        ("SHAMPOO-ARGAN", "Argan Oil Shampoo 400ml", "Personal Care & Pharmacy", 4.20, 8.99, 10, 40, 7),
        ("HAND-SOAP-500ML", "Lavender Hand Soap 500ml", "Personal Care & Pharmacy", 1.50, 3.49, 20, 80, 5),
        ("TOOTHPASTE-MINT", "Mint Fluoride Toothpaste 100ml", "Personal Care & Pharmacy", 1.80, 3.99, 15, 60, 6),
        
        ("COOKWARE-5P-SET", "5-Piece Non-Stick Cookware Set", "Home & Kitchen", 45.00, 89.99, 5, 20, 10),
        ("DISH-SOAP-1L", "Lemon Dishwashing Liquid 1L", "Home & Kitchen", 1.60, 3.79, 25, 90, 4),
        ("PAPER-TOWEL-6PK", "Ultra Absorbent Paper Towels 6pk", "Home & Kitchen", 4.50, 9.49, 20, 80, 5),
        ("STORAGE-BOX-3PK", "Clear Plastic Storage Tubs 3pk", "Home & Kitchen", 6.80, 14.99, 10, 35, 7)
    ]
    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?);", products)
    
    # 3. Insert Inventory Levels (With deliberate edge cases for hackathon testing)
    today = datetime.now()
    
    inventory_data = [
        # Store 1: Downtown Metro
        ("STORE-001", "MILK-ORG-1L", 14, 0, (today - timedelta(days=5)).strftime("%Y-%m-%d")), # CRITICAL STOCKOUT RISK! Stock 14, sales ~12/day, lead time 3 days
        ("STORE-001", "CHEDDAR-250G", 45, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")),
        ("STORE-001", "GREEK-YOG-500G", 55, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")),
        ("STORE-001", "EGGS-FREE-12P", 80, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")),
        ("STORE-001", "OAT-MILK-1L", 40, 0, (today - timedelta(days=3)).strftime("%Y-%m-%d")),
        ("STORE-001", "BAKERY-ART-BREAD", 35, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")), # RECENT SALES DROP CASE
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
        ("STORE-002", "MILK-ORG-1L", 85, 0, (today - timedelta(days=2)).strftime("%Y-%m-%d")), # Surplus milk here for transfer!
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
        ("STORE-002", "COOKWARE-5P-SET", 38, 0, (today - timedelta(days=25)).strftime("%Y-%m-%d")), # DEAD STOCK CASE! 38 units, 0 sales in 21 days
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
        ("STORE-003", "BEV-ENERGY-500ML", 18, 0, (today - timedelta(days=1)).strftime("%Y-%m-%d")), # RECENT SPIKE CASE! High velocity, stock burning fast
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
    
    # Filter unique store_id, sku pairs
    seen = set()
    unique_inventory = []
    for item in inventory_data:
        pair = (item[0], item[1])
        if pair not in seen:
            seen.add(pair)
            unique_inventory.append(item)
            
    cursor.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?);", unique_inventory)
    
    # 4. Generate 90 Days Daily Sales Data with realistic distribution & deliberate test cases
    random.seed(42) # Reproducible dataset
    sales_rows = []
    
    start_date = today - timedelta(days=90)
    for day_idx in range(91):
        current_date = (start_date + timedelta(days=day_idx)).strftime("%Y-%m-%d")
        is_recent_3_days = (day_idx >= 88)
        is_last_21_days = (day_idx >= 65)
        
        for store in ["STORE-001", "STORE-002", "STORE-003"]:
            for sku, name, cat, cost, price, r_pt, t_st, lead_t in products:
                
                # Base velocity per category & store
                if "Fresh" in cat or "Bakery" in cat:
                    base_sales = random.randint(8, 15) if store == "STORE-001" else random.randint(4, 10)
                elif "Beverages" in cat:
                    base_sales = random.randint(12, 22) if store == "STORE-001" else random.randint(6, 14)
                elif "Personal" in cat:
                    base_sales = random.randint(2, 6)
                else: # Home & Kitchen
                    base_sales = random.randint(1, 4)
                
                # --- Inject Hackathon Test Cases ---
                
                # 1. Milk Organic 1L at Downtown Store: High steady velocity ~12-14 units/day
                if store == "STORE-001" and sku == "MILK-ORG-1L":
                    units = random.randint(11, 15)
                
                # 2. Dead stock: Cookware set at Suburban Mall (STORE-002) has 0 sales in last 21 days!
                elif store == "STORE-002" and sku == "COOKWARE-5P-SET" and is_last_21_days:
                    units = 0
                
                # 3. Sales Spike: Volt Energy Drink at Express Mart (STORE-003) spiked to 35 units/day in last 3 days!
                elif store == "STORE-003" and sku == "BEV-ENERGY-500ML" and is_recent_3_days:
                    units = random.randint(32, 38)
                
                # 4. Sales Drop: Artisan Sourdough Bread at Downtown (STORE-001) dropped to 1-2 units/day in last 5 days
                elif store == "STORE-001" and sku == "BAKERY-ART-BREAD" and day_idx >= 86:
                    units = random.randint(1, 3)
                
                else:
                    # Weekend bump
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

if __name__ == "__main__":
    init_db()
