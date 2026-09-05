TRACK_ID=PS03

# Retail - Sales and Inventory Copilot (PS03)

An intelligent, multi-store sales and inventory operations copilot designed for store managers. The system monitors sales velocity, stock levels, lead times, and financial metrics across a retail network to proactively detect stock-outs before they happen, identify dead stock, surface sales velocity spikes & drops, and provide actionable recommendations backed by deterministic calculations and Google Gemini AI reasoning.

---

## 🎯 Key Features & Capabilities

1. **Deterministic Analytics & Alert Engine**:
   - **Likely Stock-outs**: Calculates daily sales velocity over a 14-day window ($v = \text{sales} / 14$), computes Days of Stock Remaining ($DIR = \text{stock} / v$), and flags items where $DIR \le \text{lead\_time\_days}$.
   - **Dead Stock Identification**: Surfaces products with idle stock and zero sales over the last 21+ days, calculating tied-up capital and suggesting clearance markdowns or product bundling.
   - **Sales Anomalies (Spikes & Drops)**: Compares 3-day short-term velocity to 30-day baseline moving averages ($>2.0\times$ for spikes, $<0.35\times$ for drops).

2. **Grounded GenAI Reasoning (Google Gemini)**:
   - Uses Google Gemini API (`gemini-1.5-flash`) for plain-language natural language understanding.
   - **Strict Grounding Enforcement**: Every claim is backed by exact numeric figures (stock levels, velocity rates, lead times, cost, revenue).
   - **Refusal / Out-of-Scope Discipline**: Refuses to answer queries outside the system's store dataset rather than inventing figures.
   - **Deterministic Fallback**: If `GEMINI_API_KEY` is omitted or API calls fail, the system falls back to a deterministic rule-based template engine so the app runs smoothly in offline testing environments.

3. **Interactive Control Tower Dashboard**:
   - Executive dark-mode UI with live KPI metrics.
   - **Copilot Assistant Drawer** with interactive chat and quick-test prompt pills.
   - **Needs Attention Today Feed** featuring actionable recommendation cards and an expandable **"Data & Assumptions Audit Trail"**.
   - **Store Network Inventory Matrix** with real-time text filter and status badges.

---

## 🛠️ Environment Variables

The application requires only one external API key (Google Gemini):

| Environment Variable | Required | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Optional / Recommended | API key for Google Gemini LLM. Read automatically at startup. If omitted, app seamlessly uses grounded fallback mode. |

---

## 🚀 How to Run (Single Command Launcher)

From the repository root:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the application (Backend + Frontend together on port 8000)
python app.py
```

Open your browser and navigate to:
👉 **`http://localhost:8000`**

*(Note: On first startup, `app.py` automatically initializes and seeds `data/retail_copilot.db` if it does not already exist.)*

---

## 📁 Repository Structure

```
.
├── TRACK_ID=PS03 (Line 1 of README.md)
├── app.py                   # Main HTTP & REST API server (Port 8000)
├── generate_data.py         # SQLite database & dataset generator
├── requirements.txt         # Python dependencies
├── README.md                # Submission documentation
├── src/
│   ├── analytics_engine.py  # Deterministic math engine (stockouts, dead stock, anomalies)
│   ├── copilot.py           # Gemini GenAI grounding & prompt synthesis module
│   └── db.py                # Database connection helpers
├── static/
│   ├── index.html           # Web UI layout
│   ├── style.css            # Executive dark-mode styling system
│   └── app.js               # Dynamic dashboard & chat logic
└── data/
    └── retail_copilot.db    # SQLite dataset containing stores, products, inventory & 90-day sales
```

---

## 📊 Sample Data Generated

The system includes precomputed, committed dataset files in `data/retail_copilot.db`:
- **3 Stores**: Downtown Metro Store (`STORE-001`), Suburban Mall Branch (`STORE-002`), Westside Express Mart (`STORE-003`).
- **20 Product SKUs**: Across Fresh Produce & Dairy, Bakery, Beverages, Personal Care, and Home & Kitchen.
- **90 Days of Sales History**: Over 5,400 daily sales transaction records.
- **Seeded Hackathon Edge-Cases**:
  - `MILK-ORG-1L` at Downtown (Stock = 14, Velocity = 11.5/day, Lead Time = 3d → Critical stockout in ~1.2 days).
  - `COOKWARE-5P-SET` at Suburban Mall (Stock = 38, 0 sales in 21 days → $3,419.62 dead stock).
  - `BEV-ENERGY-500ML` at Express Mart (3d velocity jumped 5.4x → Sales spike alert).
  - `BAKERY-ART-BREAD` at Downtown (Sales dropped -88% after price hike → Sales drop alert).

---

## 📽️ Demo Video Link

- **Demo Video**: [Link to 2-3 minute video walkthrough] *(To be attached upon submission)*
