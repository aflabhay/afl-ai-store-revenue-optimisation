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
- Python: `_apply_priceband()` classifies each style using breaks dict
- Python: `_aggregate_to_buckets()` aggregates to store x category x priceband
- All derived metrics (revenue_rate, sell_through_pct, signal_preview, etc.) computed in pandas

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
cap[b]   = min(45%, proportional_fair_share[b] * cap_multiplier, soh_cap[b])  # default 1.5
```

### Revenue rate formula

```
revenue_rate = bucket_revenue_4w / (avg_weekly_soh * 4)
```

Numerator: 4-week revenue. Denominator: avg_weekly_soh * 4 (same 4-week window). Unit: Rs/unit/4-week period.

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
- SOH date parsing: `CONVERT(DATE, LEFT(CAST(s.LOAD_RUN_DATE AS VARCHAR), 8), 112)`

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

## What NOT to do

- Do not add REGION back anywhere (removed intentionally)
- Do not use dummy/sample data — all data comes from Fabric
- Do not use `--data dummy` argument (removed from run_solver.py)
- Do not use `<<PRICEBAND_CASE>>` template injection (replaced with pandas approach)
- Do not use `PERCENTILE_CONT` with plain `GROUP BY` in T-SQL (requires OVER clause)
