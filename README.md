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
│   ├── analytics_engine.py  # Deterministic math engine (stockouts, dead stock, anomalies, actions)
│   ├── copilot.py           # Gemini GenAI grounding & prompt synthesis module (google.genai + legacy SDK)
│   ├── vector_store.py      # Local vector retrieval pipeline (gemini-embedding-001 & NumPy cosine similarity)
│   └── db.py                # Database connection helpers
├── static/
│   ├── index.html           # Web UI layout & executive control tower
│   ├── style.css            # Executive dark-mode styling system with animations & canvas styling
│   └── app.js               # Dynamic dashboard, canvas chart renderer, 1-click action triggers & chat logic
├── test_app.py              # Automated test suite (10 test suites covering all criteria)
└── data/
    ├── retail_copilot.db    # SQLite dataset containing stores, products, inventory, 90-day sales & policies
    └── catalog_embeddings.json # Precomputed normalized vector embeddings for instant offline boot (<90s)
```

---

## 🧪 Automated Testing

To run the full automated verification test suite:

```bash
python test_app.py
```

This validates:
- KPI calculations and multi-store network totals.
- Imminent stockout detection, velocity burn calculations, and inter-store surplus transfer logic.
- 21-day dead stock detection and tied-up capital valuation.
- Short-term vs baseline velocity anomalies (surge spikes and demand slumps).
- Real-time manager action execution (transfers, reorders, markdowns) and audit trail logging.
- Local vector store semantic retrieval with policy grounding.
- GenAI query routing and strict refusal discipline on out-of-scope inquiries.

---

## 📊 Sample Data & Documents Generated

The system includes precomputed, committed dataset files in `data/retail_copilot.db` and `data/catalog_embeddings.json`:
- **3 Stores**: Downtown Metro Store (`STORE-001`), Suburban Mall Branch (`STORE-002`), Westside Express Mart (`STORE-003`).
- **20 Product SKUs**: Across Fresh Produce & Dairy, Bakery, Beverages, Personal Care, and Home & Kitchen.
- **5 Store Operational Policies**: Standard operating procedures for lead-time safety buffers, sister-store transfer priority, dead stock markdowns, and surge multipliers.
- **90 Days of Sales History**: Over 5,400 daily sales transaction records.
- **Seeded Hackathon Edge-Cases**:
  - `MILK-ORG-1L` at Downtown (Stock = 14, Velocity = 11.8/day, Lead Time = 3d → Critical stockout in ~1.2 days; Suburban Mall has 85 units surplus ready for 24h transfer).
  - `COOKWARE-5P-SET` at Suburban Mall (Stock = 38, 0 sales in 21 days → $1,710.00 dead stock tied up in cost capital).
  - `BEV-ENERGY-500ML` at Express Mart (3d velocity jumped 2.9x → Sales spike alert).
  - `BAKERY-ART-BREAD` at Downtown (Sales dropped -71% after price elasticity change → Sales drop alert).

---

## 🌐 Live Deployment & Public Access

- **Live Public URL**: 👉 **`https://lane-towns-router-crossword.trycloudflare.com`**
- **Local Port**: `http://localhost:8000`

### 1-Click Cloud Deployment:
The repository includes production configuration files ready for any cloud provider:
1. **Render**: Connect the repository to [Render](https://render.com). It will automatically detect `render.yaml` and deploy with `python app.py`.
2. **Railway / Heroku**: Connect the repository to [Railway](https://railway.app). It will automatically build from `Procfile` and `requirements.txt`.
3. **Docker**: Build and run anywhere using the included `Dockerfile`:
   ```bash
   docker build -t retail-copilot .
   docker run -p 8000:8000 -e GEMINI_API_KEY="your_api_key" retail-copilot
   ```

---

## 📽️ Demo Video Link

- **Demo Video**: [Link to 2-3 minute video walkthrough] *(Attach YouTube/Loom demo recording here upon Devfolio submission)*
