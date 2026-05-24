# Arvind Fashions — Arrow Brand Store Revenue Optimisation

> **Business Requirements Document:** See [`docs/BRD_v2.0.docx`](docs/BRD_v2.0.docx)

---

## 1. Project Origin & Business Context

This project was initiated following store visits to Arvind Fashions Limited (Arrow brand) stores across India. Key observations:

- **Monday rearrangement cycle:** Store teams physically rearrange the display floor every Monday. Until now, done entirely by intuition — no data-driven guidance existed.
- **65/35 display-to-backroom split:** ~65% of total store inventory is on display at any given time; 35% sits in the backroom as a replenishment buffer.
- **Three-layer stock flow:** As display items sell, staff pull matching sizes from backroom to refill. If backroom runs out, the warehouse replenishes next day — independently of the Monday cycle.
- **Style count as the true constraint:** Display capacity is measured in **number of distinct styles (options)** that can be shown — not units. `Min Option Count` per store (from VM guidelines) is the binding physical constraint.

### What the system does

For each Arrow store, every Sunday night:
1. Pulls the latest SOH snapshot and 4-week sales from **Microsoft Fabric Data Warehouse**
2. Computes rolling 4-week revenue rates per bucket (Category x Priceband) using data-driven, per-category priceband breaks
3. Runs an **Integer Programming (IP) optimisation model** to recommend the optimal display share allocation across all active buckets
4. Surfaces recommendations through a **Streamlit internal tool** for planners and area managers to review and approve before Monday rearrangement

---

## 2. Key Concepts & Terminology

| Term | Definition |
|---|---|
| **Bucket** | A unique Category x Priceband combination (e.g. Formal Shirts / Premium). Key format: `{Category} | {Priceband}` |
| **display_share[bucket]** | % of display floor allocated to a bucket on Monday — the decision variable (integer 1-45) |
| **display_capacity[store]** | Min Option Count — number of distinct styles the store can display, from VM guidelines |
| **revenue_rate[store, bucket]** | Revenue generated per unit of SOH committed to this bucket over 4 weeks: `bucket_revenue_4w / (avg_weekly_soh x 4)` — units: Rs/unit/4-week period |
| **style_count_in_bucket** | Distinct styles with SOH > 0 in this bucket — caps style slot recommendations to only physically fulfillable options |
| **avg_sizes_per_style** | Fleet-wide average distinct sizes per style for this category (e.g. SHIRT ≈ 5, TROUSER ≈ 5, SUIT ≈ 4). Computed at category level — sizes don't vary by priceband. |
| **hanger_slots** | Physical hangers allocated to bucket = `display_share% × display_capacity`. `display_capacity` is hanger count, NOT style count. |
| **style_slots (Rec. Style-Size Count)** | Distinct styles to arrange = `floor(hanger_slots / avg_sizes_per_style)`, capped at `style_count_in_bucket`. Always ≤ available SOH styles. |
| **Priceband** | Economy / Mid / Premium — thresholds computed per category from MRP p33/p67 percentiles, rounded to Rs 500 |
| **Monday rearrangement** | Weekly physical display rearrangement based on solver recommendations |
| **Phase 1** | IP optimisation using rolling 4-week revenue rates (current) |
| **Phase 1.5** | Hybrid IP + early ML once 4-6 months of display data collected |
| **Phase 2** | Full ML model once 2 years of display data available |

---

## 3. Revenue Rate Formula

```
revenue_rate = bucket_revenue_4w / avg_weekly_soh

sell_through_pct = units_sold_4w / (avg_weekly_soh + units_sold_4w) x 100
```

- **Numerator**: Total revenue from this bucket over last 4 weeks (Rs)
- **`avg_weekly_soh`**: SUM across styles of `AVG(Opening_SOH over 28 days) x 7` — the average weekly committed inventory for the bucket over the same 4-week window
- **Source**: `FACT_FNO_BASE_SOH` — Opening_SOH column, 446-day history, native INVENTORY_DATE
- **SIZE aggregation**: `SUM(Opening_SOH)` across all sizes first to get style-level daily SOH, then `AVG` across days in the window, then `x 7` for weekly
- SOH and sales joined at STYLE_CODE level — both sides reference the same styles

---

## 4. Optimisation Model (IP Solver)

### Decision Variable
```
display_share[bucket]  in  {1, 2, ..., 45}   (integer percentage)
```

### Objective
```
Maximise:  SUM over buckets [ display_share[bucket] x revenue_rate[bucket] ]
```

### Constraints

| ID | Description | Rule |
|---|---|---|
| C1 | Shares sum to 100% | SUM(display_share) = 100 |
| C2 | Whole-number percentages | display_share in Z (integer) |
| C3 | Proportional cap | display_share <= min(45%, proportional_share x cap_multiplier) |
| C4 | Proportional floor | display_share >= max(1%, proportional_share x floor_weight) |
| C5 | Style count <= display capacity | SUM(ROUND(share/100 x display_capacity)) <= display_capacity |
| C6 | Only existing buckets | Buckets with revenue_rate = 0 excluded before solver runs |
| C7 | SOH style cap | display_share <= style_count_in_bucket / display_capacity x 100 — never recommend more style slots than available SOH can fill |

### Dynamic Floor & Cap Logic

Pure linear objectives produce "bang-bang" allocations — the solver concentrates all free budget in the single highest-rate bucket. To prevent this:

- **Dynamic floor** = `max(1%, proportional_fair_share x floor_weight)` — each bucket guaranteed at least 50% of its proportional fair share (default `floor_weight = 0.50`)
- **Dynamic cap** = `min(45%, proportional_fair_share x cap_multiplier)` — each bucket capped at 1.5x its proportional fair share (default `cap_multiplier = 1.5`)

Where `proportional_fair_share[bucket] = revenue_rate[bucket] / SUM(revenue_rate) x 100`.

This forces the solver to spread the free allocation budget across multiple buckets proportionally to their revenue rates, rather than concentrating in the top 1-2 buckets.

**Allocation signals output:**
- `INCREASE` — bucket hit its proportional cap (solver maxed it out — show more)
- `HOLD` — bucket above floor, below cap (solver allocated some but not all free budget)
- `REDUCE` — bucket at its proportional floor (solver gave it minimum — show less)

### C7 Implementation Detail — Hanger-Aware Model

`display_capacity` (Min Option Count from VM guidelines) = **physical hangers**, not style count. Each style occupies `avg_sizes_per_style` hangers (one hanger per size on display). A SHIRT with S/M/L/XL/XXL needs 5 hangers; a SUIT with 38/40/42/44 needs 4 hangers.

```
hanger_cap%[b] = style_count[b] × avg_sizes[b] / display_capacity × 100
hanger_slots   = int(display_share% / 100 × display_capacity)   ← physical hangers
style_slots    = min(floor(hanger_slots / avg_sizes), style_count)  ← distinct styles
```

`avg_sizes_per_style` is computed at **category level** fleet-wide (not per bucket or store) since sizes are a category property, not priceband-specific.

C7 is a **separate hard PuLP constraint** so it cannot be overridden by the proportional-cap guard:

```python
if c7_feasible:
    for b in bucket_keys:
        prob += x[b] <= soh_hanger_cap_pct[b], f"C7_soh_cap_{b}"
```

When a store's total hanger requirement < `display_capacity`, SOH caps are **normalised proportionally** to sum to 100 so the LP stays feasible. Dynamic floors are reconciled to `min(floor, soh_cap)` before the LP is built. `style_slots` is additionally capped at `style_count_in_bucket` in the output to handle rare categories with no fleet-wide size average.

### Solver Backend

PuLP as the modelling interface. Solver selection at runtime (in order):
1. **HiGHS** (Python API) — preferred; arm64-native, works on Mac Apple Silicon
2. **HiGHS_CMD** — fallback if Python API unavailable
3. **PULP_CBC_CMD** — bundled PuLP CBC; fallback for Ubuntu x86_64 deployment

### Solver Meaningfulness

| Active buckets | Solver freedom | Action |
|---|---|---|
| < 20 | Full — ideal | Proceed as designed |
| 20-49 | Good | Proceed, monitor outputs |
| >= 100 | None — floor binds all budget | Coarsen bucket definition |

For Arrow (Formal Shirts / Chinos / Trousers / Casual Shirts x 3 pricebands), expected bucket count per store is **6-15** — well within the ideal range.

---

## 5. Data-Driven Priceband Breaks (Per Category)

Priceband thresholds are computed from actual MRP distribution, not hardcoded. Different categories (Shirts vs Trousers) have different price ranges so one set of global thresholds is wrong.

**Two-pass pipeline:**

1. **MRP distribution query** (`_MRP_DIST_SQL`) — fetches p10/p25/p33/p50/p67/p75/p90 of transaction MRP per category from last 4 weeks. Uses window-function form of `PERCENTILE_CONT ... WITHIN GROUP ... OVER (PARTITION BY category)` (required by SQL Server T-SQL).

2. **Break computation** (`compute_priceband_breaks()`) — p33 = Economy cap, p67 = Mid cap; both rounded to nearest Rs 500; minimum Rs 500 separation enforced. Default fallback: Economy < Rs 2,000, Mid < Rs 3,000.

3. **Dynamic SQL injection** (`_build_priceband_case()`) — builds a nested `CASE WHEN` expression per category and injects it into `_EDA_SQL_TEMPLATE` via a `<<PRICEBAND_CASE>>` placeholder.

4. **Config saved** to `data/processed/priceband_config.json` so the Streamlit app can display current breaks in the Price Bands EDA tab.

---

## 6. Data Pipeline

### Run order

```bash
# Step 1: Fetch from Fabric (two-pass: MRP distribution -> EDA)
python src/data_pipeline/fabric_connector.py

# Step 2: Run IP solver for all stores
python src/solver/run_solver.py --store all

# Step 3: Launch app
streamlit run src/streamlit_app/app.py
```

### Outputs written to `data/processed/`

| File | Written by | Purpose |
|---|---|---|
| `mrp_distribution_YYYY-MM-DD.csv` | fabric_connector | MRP percentiles per category |
| `priceband_config.json` | fabric_connector | Per-category break points for app display |
| `eda_data_YYYY-MM-DD.csv` | fabric_connector | Main EDA dataset with revenue rates |
| `store_capacity_real.csv` | run_solver | Store Min Option Count (written after first solver run) |
| `recommendations_YYYY-MM-DD.csv` | run_solver | Flat solver output per store-bucket |
| `solver_results_YYYY-MM-DD.json` | run_solver | Full solver output with metadata |

### Fabric Tables Used

| Table | Purpose |
|---|---|
| `[prd].[FACT_FNO_SALES_TC_ONLINE_BASE]` | Transaction-level sales — units, revenue, MRP, discount |
| `[prd].[FACT_FNO_BASE_SOH]` | Opening SOH per style x size x store x day (446-day history). Columns: STORE_CODE, STYLECODE, SIZE, INVENTORY_DATE (native DATE), Opening_SOH. Must SUM across sizes before averaging across days. |
| `[prd].[DIM_SAP_STORE_MASTER]` | Store master — name, region, active Arrow stores |

---

## 7. Streamlit App

Single-file app (`src/streamlit_app/app.py`) with sidebar navigation.

### Pages

| Page | Description |
|---|---|
| Store Selector | Search by `{store_id} - {store_name}`. Selection persists across page navigation via session state. Active store shown as banner. |
| Allocation Recommendations | IP solver output for selected store — display share %, style slots, INCREASE/HOLD/REDUCE signals, expected revenue index |
| EDA Explorer | 6-tab exploratory dashboard |

### EDA Explorer Tabs

| Tab | Contents |
|---|---|
| Fleet Overview | Store count, bucket coverage, top/bottom stores by revenue rate |
| Revenue Rate | Distribution histograms and heatmaps by category x priceband |
| Sell-Through & Discounts | Discount depth vs sell-through scatter, category trends |
| SOH Analysis | SOH KPIs, histogram, SOH vs revenue rate scatter, store-level SOH table |
| Data Quality | Revenue rate coverage, NULL counts, bucket completeness |
| Price Bands | Current priceband performance (revenue, rate, sell-through) + recommended vs current break comparison per category |

---

## 8. Tech Stack

| Component | Technology |
|---|---|
| Optimisation solver | PuLP (IP modelling) + HiGHS (arm64 Mac) / CBC (x86_64 Ubuntu) |
| Data layer | Microsoft Fabric Data Warehouse (T-SQL) |
| DB connector | pyodbc + AAD token auth (InteractiveBrowserCredential local; notebookutils on Fabric) |
| App framework | Streamlit |
| App hosting | Azure App Service (Ubuntu VM, x86_64) |
| Image storage | Azure Blob Storage (Phase 1.5+) |
| Image capture | Power Apps (Phase 1.5+) |
| Image analysis | SAM + CLIP (Phase 2) |

---

## 9. Repository Structure

```
afl-ai-store-revenue-optimisation/
|
+-- README.md                          # This file
+-- CLAUDE.md                          # AI assistant instructions and project context
+-- requirements.txt                   # Python dependencies
+-- .env.example                       # Environment variables template
|
+-- data/
|   +-- processed/                     # Auto-generated outputs (not committed)
|       +-- eda_data_YYYY-MM-DD.csv
|       +-- priceband_config.json
|       +-- mrp_distribution_*.csv
|       +-- store_capacity_real.csv
|       +-- recommendations_*.csv
|       +-- solver_results_*.json
|
+-- src/
|   +-- data_pipeline/
|   |   +-- fabric_connector.py        # Fabric ODBC + two-pass EDA fetch + priceband SQL
|   |   +-- revenue_rate_builder.py    # Legacy helper (kept for reference)
|   |
|   +-- solver/
|   |   +-- ip_model.py                # IP model: C1-C7, dynamic floor/cap, HiGHS/CBC
|   |   +-- run_solver.py              # Batch runner: all stores -> recommendations CSV
|   |
|   +-- streamlit_app/
|   |   +-- app.py                     # Streamlit app: store selector, allocation, EDA
|   |
|   +-- utils/
|       +-- size_break_monitor.py      # Daily CORE style SOH check (future use)
|
+-- notebooks/                         # EDA and analysis notebooks
+-- docs/
    +-- BRD_v2.0.docx
```

---

## 10. Project Phases

### Phase 1 — IP Optimisation (current)
- Rolling 4-week revenue rates from Fabric, joined at STYLE_CODE level
- Data-driven per-category priceband breaks from MRP p33/p67 percentiles
- IP solver (PuLP + HiGHS) with C1-C7 constraints
- C7 SOH style cap — recommendations never exceed available SOH
- Dynamic proportional floors and caps to prevent bang-bang concentration
- Streamlit internal tool for planner review and approval

### Phase 1.5 — Hybrid ML (4-6 months of display data)
- Weekly display Excel uploads via Power Apps -> Azure Blob
- ML model supplements revenue rates with observed display share data
- Shadow mode: ML runs alongside IP, validated before promotion

### Phase 2 — Full ML (2 years of display data)
- ML model replaces revenue rate estimation entirely
- SAM + CLIP extracts style counts from Monday wall photos
- Per-bucket display share becomes a directly observed feature

---

## 11. Deployment — Azure App Service (Ubuntu VM)

The Streamlit app is hosted on an Azure App Service VM running Ubuntu x86_64. The data pipeline runs locally (Mac) and processed outputs are pushed to the VM.

### VM Environment Setup (first time)

```bash
# SSH into the VM
ssh <user>@<vm-hostname>

# Install Python 3.11 and pip
sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv python3-pip

# Create app directory
mkdir -p /home/site/wwwroot
cd /home/site/wwwroot

# Clone the repo
git clone https://github.com/aflabhay/afl-ai-store-revenue-optimisation.git .

# Create virtualenv and install deps
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env from template
cp .env.example .env
# Edit .env and fill in FABRIC_CONNECTION_STRING etc.
nano .env
```

### Azure App Service startup command

Set this as the startup command in Azure Portal → App Service → Configuration → Startup Command:

```bash
/home/site/wwwroot/venv/bin/streamlit run /home/site/wwwroot/src/streamlit_app/app.py --server.port 8000 --server.address 0.0.0.0 --server.headless true
```

### Weekly deployment workflow (every Sunday)

Run this on your local Mac after the pipeline completes:

```bash
# Step 1 — regenerate all processed outputs locally
cd /path/to/afl-ai-store-revenue-optimisation
python src/data_pipeline/fabric_connector.py
PYTHONPATH=. python src/solver/run_solver.py --store all

# Step 2 — push processed data files to VM via SCP
scp data/processed/eda_data_$(date +%Y-%m-%d).csv         <user>@<vm-hostname>:/home/site/wwwroot/data/processed/
scp data/processed/recommendations_$(date +%Y-%m-%d).csv  <user>@<vm-hostname>:/home/site/wwwroot/data/processed/
scp data/processed/solver_results_$(date +%Y-%m-%d).json  <user>@<vm-hostname>:/home/site/wwwroot/data/processed/
scp data/processed/priceband_config.json                   <user>@<vm-hostname>:/home/site/wwwroot/data/processed/
scp data/processed/priceband_mapping.csv                   <user>@<vm-hostname>:/home/site/wwwroot/data/processed/
scp data/processed/store_capacity_real.csv                 <user>@<vm-hostname>:/home/site/wwwroot/data/processed/
scp data/processed/size_breaks_latest.csv                  <user>@<vm-hostname>:/home/site/wwwroot/data/processed/

# Step 3 — pull latest code changes to VM (if any)
ssh <user>@<vm-hostname> "cd /home/site/wwwroot && git pull && source venv/bin/activate && pip install -r requirements.txt"

# Step 4 — restart the app
ssh <user>@<vm-hostname> "supervisorctl restart streamlit"
# OR via Azure CLI:
az webapp restart --name <app-name> --resource-group <rg-name>
```

### Deploy code-only changes (no data refresh)

```bash
# Push to GitHub then pull on VM
git push origin main
ssh <user>@<vm-hostname> "cd /home/site/wwwroot && git pull && supervisorctl restart streamlit"
```

### File locations on VM

| File | VM Path |
|---|---|
| App code | `/home/site/wwwroot/src/` |
| Processed data | `/home/site/wwwroot/data/processed/` |
| `.env` secrets | `/home/site/wwwroot/.env` |
| Python venv | `/home/site/wwwroot/venv/` |
| App logs | `/home/LogFiles/` (Azure Portal → Log stream) |

### ODBC driver on VM (required for Fabric connection)

```bash
# Install Microsoft ODBC Driver 18 on Ubuntu
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

---

## 12. Key Business Rules



- **Monday only:** All recommendations activate on Monday. Mid-week changes queue for the following Monday.
- **Override requires reason:** Any deviation from solver recommendations must be logged — feeds Phase 1.5 improvement.
- **Arrow first:** Phase 1 covers Arrow brand only. Expansion to USPA, Flying Machine, Excalibur follows after validation.
- **Quarterly taxonomy review:** Priceband thresholds reviewed with Merchandising every quarter. Refresh by re-running `fabric_connector.py`.
- **SOH-constrained:** Solver never recommends more style slots for a bucket than the number of distinct styles with actual SOH in that bucket (C7).

---

*Built for Arvind Fashions Limited | Arrow Brand | Phase 1 — Integer Programming Optimisation*
