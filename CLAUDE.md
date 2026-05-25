# CLAUDE.md — Arrow Store Revenue Optimisation

Project context and conventions for AI-assisted development.

---

## Project Overview

Arrow brand (Arvind Fashions Limited) store display optimisation system.
Every Sunday night: fetch Fabric data -> run IP solver -> Streamlit app for planners to review before Monday rearrangement.

**Single Streamlit app:** `src/streamlit_app/app.py` (no pages/ subdirectory).

---

## Run Order

```bash
# 1. Fetch from Fabric (two-pass: MRP distribution -> EDA)
python src/data_pipeline/fabric_connector.py

# 2. Run IP solver
python src/solver/run_solver.py --store all
# or single store:
python src/solver/run_solver.py --store 8194

# 3. Launch app
streamlit run src/streamlit_app/app.py
```

---

## Key Files

| File | Purpose |
|---|---|
| `src/data_pipeline/fabric_connector.py` | Fabric ODBC + two-pass EDA pipeline |
| `src/solver/ip_model.py` | IP model: C1-C7, dynamic floor/cap, HiGHS/CBC |
| `src/solver/run_solver.py` | Batch runner — all stores -> recommendations CSV |
| `src/streamlit_app/app.py` | Streamlit app — store selector, allocation, EDA |
| `data/processed/eda_data_*.csv` | Main input for solver and app |
| `data/processed/priceband_config.json` | Per-category priceband breaks (loaded by app) |
| `data/processed/priceband_mapping.csv` | Human-readable mapping: category, economy_cap, mid_cap |
| `data/processed/store_capacity_real.csv` | Store Min Option Count |
| `data/processed/recommendations_*.csv` | Solver output (flat, one row per store-bucket) |

---

## Data Pipeline Architecture

### Two-pass fetch (`fabric_connector.py`)

**Pass 1 — MRP distribution:**
- SQL: `_MRP_DIST_SQL` — runs `PERCENTILE_CONT ... OVER (PARTITION BY category)` via window functions (NOT plain GROUP BY — SQL Server requires OVER clause)
- CTE structure: `raw` -> `percentiles` (SELECT DISTINCT + window funcs) -> `counts` (GROUP BY for COUNT DISTINCT) -> JOIN
- Output: one row per category with p10/p25/p33/p50/p67/p75/p90 of MRP

**Break computation:**
- `compute_priceband_breaks()`: p33 = Economy cap, p67 = Mid cap
- Both rounded to nearest Rs 500, minimum Rs 500 separation
- Saves: `priceband_config.json`, `priceband_mapping.csv`

**Pass 2 — EDA dataset:**
- SQL: `_EDA_SQL` — outputs one row per **store x style x category** with `avg_unit_mrp`
- NO priceband in SQL — classification done entirely in Python
- CTEs in `_EDA_SQL`: `sales_style`, `soh_style`, `soh_sizes`, `latest_soh_date`, `current_soh_style`
- `current_soh_style`: `SUM(Opening_SOH)` per store×style at `MAX(INVENTORY_DATE)` — today's exact stock snapshot
- Python: `_apply_priceband()` classifies each style using breaks dict
- Python: `_aggregate_to_buckets()` aggregates to store x category x priceband
- All derived metrics (revenue_rate, sell_through_pct, signal_preview, etc.) computed in pandas
- `current_soh_bucket = SUM(current_soh)` per bucket — shown in allocation table as "Current SOH (today)"
- `avg_weekly_soh = SUM(style_avg_weekly_soh)` per bucket — used in revenue_rate denominator, shown as "Avg Weekly SOH"

### Why Python not SQL for pricebands

Old approach used `<<PRICEBAND_CASE>>` template placeholder injected into SQL at runtime — complex, hard to debug, thresholds buried in SQL.

New approach: generate `priceband_mapping.csv` every Monday from data, classify in pandas. SQL stays simple and stable. Breaks are visible in a CSV file anyone can inspect.

---

## IP Solver Algorithm

### Constraints C1-C7

| ID | Rule |
|---|---|
| C1 | SUM(display_share) = 100 |
| C2 | display_share is integer |
| C3 | display_share <= min(45%, proportional_share x cap_multiplier) |
| C4 | display_share >= max(1%, proportional_share x floor_weight) |
| C5 | SUM(ROUND(share/100 x display_capacity)) <= display_capacity |
| C6 | Only buckets with revenue_rate > 0 are passed to solver |
| C7 | display_share <= style_count_in_bucket / display_capacity x 100 (SOH cap) |

### Dynamic floor & cap (prevents bang-bang)

```
proportional_fair_share[b] = revenue_rate[b] / SUM(revenue_rate) * 100
floor[b] = max(1%, proportional_fair_share[b] * floor_weight)   # default 0.50
cap[b]   = min(45%, proportional_fair_share[b] * cap_multiplier)  # default 1.5
```

### C7 — SOH style cap (critical: separate hard constraint)

- `display_capacity` = **style count** (Min Option Count), NOT hanger count — e.g. 400 means 400 distinct styles
- Max hanger capacity = `display_capacity × 5` ≈ 2000 hangers (informational, not a solver constraint)
- `avg_sizes_per_style` computed at **category level** fleet-wide (not per bucket) — sizes are a category property, not priceband-specific
- `soh_style_cap_pct[b] = max(1, int(style_count[b] / display_capacity * 100))` — pure style cap, no avg_sizes
- C7 is a **separate hard PuLP constraint** `prob += x[b] <= soh_style_cap_pct[b]` — NOT mixed into variable bounds
- When `sum(soh_caps) < 100`: **normalise proportionally** so they sum to 100 → C7 always applied
- Dynamic floors reconciled to `min(floor, soh_cap)` before LP build
- Guard 2: if `sum(min(proportional_cap, soh_cap)) < 100`, relax proportional caps to 45%
- `style_slots` (shown as **Rec. Style Count**) = `int(display_share% / 100 * display_capacity)`, capped at `style_count_in_bucket`
- `hanger_slots` (shown as **Rec. Display Units**) = `style_slots × avg_sizes_per_style` — physical hangers required
- `style_slots` always ≤ `style_count_in_bucket` — C7 + explicit cap in output

### Revenue rate formula

```
revenue_rate = bucket_revenue_4w / avg_weekly_soh
```

- `avg_weekly_soh` = SUM across styles of `AVG(Opening_SOH over 28 days) * 7` — the average weekly inventory committed to this bucket
- Computed from `FACT_FNO_BASE_SOH` (Opening_SOH, 446-day history, INVENTORY_DATE native DATE)
- Do NOT use `* 4` on the denominator — the `avg_weekly_soh` already captures the 4-week average

### Sell-through formula

```
sell_through_pct = units_sold_4w / (avg_weekly_soh + units_sold_4w) * 100
```

### Solver selection (ip_model.py)

```python
available = pulp.listSolvers(onlyAvailable=True)
if "HiGHS" in available:        # arm64 Mac (preferred)
    solver = pulp.HiGHS(...)
elif "HiGHS_CMD" in available:
    solver = pulp.HiGHS_CMD(...)
else:
    solver = pulp.PULP_CBC_CMD(...)  # Ubuntu x86_64 fallback
```

### Output signals

- `INCREASE` — bucket hit its proportional cap
- `HOLD` — between floor and cap
- `REDUCE` — bucket at its proportional floor

---

## Streamlit App Conventions

- **No REGION anywhere** — removed from SQL, solver, app display
- **Store selector format**: `"{store_id} - {store_name}"` sorted by store_id
- **Session state key**: `session_state["selected_store_label"]` persists store selection across page navigation
- **No dummy data** — app raises clear errors if `eda_data_*.csv` or `store_capacity_real.csv` not found
- **EDA tabs**: Fleet Overview, Revenue Rate, Sell-Through, SOH Analysis, Data Quality, Price Bands

---

## SQL Server (Fabric) Gotchas

- `PERCENTILE_CONT` requires `WITHIN GROUP (ORDER BY col) OVER (PARTITION BY ...)` — cannot be used as a plain GROUP BY aggregate
- `COUNT(DISTINCT col)` cannot be used as a window function — must use GROUP BY separately and JOIN
- Always use `f.QUALITY = 'Q1'` and `f.QUANTITY > 0` filters on sales fact table
- `FACT_FNO_BASE_SOH` has a SIZE column — always `SUM(Opening_SOH)` across sizes first to get style-level daily SOH, then `AVG` across days for the window average
- Do NOT use `FACT_FNO_SOH_DAILY` — it has only 1 day of data and closing SOH. Always use `FACT_FNO_BASE_SOH` with `Opening_SOH` and `INVENTORY_DATE`

---

## Dependencies

```
pulp>=2.7.0
highspy>=1.5.0    # HiGHS arm64-native (Mac); fallback CBC works on Ubuntu x86_64
pandas>=2.0.0
streamlit>=1.32.0
plotly>=5.18.0
pyodbc>=5.0.0
azure-identity>=1.15.0
python-dotenv>=1.0.0
```

---

## Deployment — Azure App Service (Ubuntu x86_64)

### Weekly data push (run locally on Mac after pipeline)

```bash
# 1. Run pipeline locally
python src/data_pipeline/fabric_connector.py
PYTHONPATH=. python src/solver/run_solver.py --store all

# 2. SCP processed files to VM
TODAY=$(date +%Y-%m-%d)
VM=<user>@<vm-hostname>
DEST=/home/site/wwwroot/data/processed

scp data/processed/eda_data_${TODAY}.csv       $VM:$DEST/
scp data/processed/recommendations_${TODAY}.csv $VM:$DEST/
scp data/processed/solver_results_${TODAY}.json $VM:$DEST/
scp data/processed/priceband_config.json        $VM:$DEST/
scp data/processed/priceband_mapping.csv        $VM:$DEST/
scp data/processed/store_capacity_real.csv      $VM:$DEST/
scp data/processed/size_breaks_latest.csv       $VM:$DEST/

# 3. Pull latest code + restart
ssh $VM "cd /home/site/wwwroot && git pull && supervisorctl restart streamlit"
# OR: az webapp restart --name <app-name> --resource-group <rg-name>
```

### VM startup command (Azure Portal → App Service → Configuration)

```bash
/home/site/wwwroot/venv/bin/streamlit run /home/site/wwwroot/src/streamlit_app/app.py --server.port 8000 --server.address 0.0.0.0 --server.headless true
```

### First-time VM setup

```bash
ssh <user>@<vm-hostname>
mkdir -p /home/site/wwwroot && cd /home/site/wwwroot
git clone https://github.com/aflabhay/afl-ai-store-revenue-optimisation.git .
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env   # fill in FABRIC_CONNECTION_STRING

# Install ODBC Driver 18 (required for Fabric)
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update && sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

---

## What NOT to do

- Do not add REGION back anywhere (removed intentionally)
- Do not use dummy/sample data — all data comes from Fabric
- Do not use `--data dummy` argument (removed from run_solver.py)
- Do not use `<<PRICEBAND_CASE>>` template injection (replaced with pandas approach)
- Do not use `PERCENTILE_CONT` with plain `GROUP BY` in T-SQL (requires OVER clause)
- Do not use `FACT_FNO_SOH_DAILY` — use `FACT_FNO_BASE_SOH` with `Opening_SOH` and `INVENTORY_DATE`
- Do not reference `LOAD_RUN_DATE` or `SAP_STORE_ID` — old column names from the deprecated SOH table
- Do not add `* 4` to the revenue_rate denominator — the formula is `bucket_revenue_4w / avg_weekly_soh`
- Do not count zero-SOH styles in `style_count_in_bucket` — only count styles with `style_avg_daily_soh > 0`
- Do not mix soh_hanger_cap_pct into dynamic_caps — C7 must be a separate hard PuLP constraint
- Do not skip C7 normalisation — when sum(soh_caps) < 100, normalise proportionally before applying
- Do not compute `avg_sizes_per_style` at bucket level — always use category-level fleet-wide average
- Do not equate `hanger_slots` (Rec. Display Units) with `style_slots` (Rec. Style Count) — style_slots = share% × display_capacity; hanger_slots = style_slots × avg_sizes
- Do not treat `display_capacity` as hanger count — it is STYLE count (Min Option Count). Hangers = style_slots × avg_sizes.
- Do not include `avg_sizes` in the C7 formula — C7 caps style slots vs style capacity: `soh_style_cap_pct = style_count / display_capacity * 100`
- `style_slots` must always be capped at `style_count_in_bucket` in solver output (rare categories fall back to avg_sizes=1)
