# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Arrow Brand Store Revenue Optimisation — an AI-powered decision support tool for Arvind Fashions Limited. Every Sunday, it pulls inventory and sales data, computes rolling 4-week revenue rates per bucket (Category × Priceband), runs an Integer Programming solver to allocate display floor space across all stores, and surfaces recommendations via a Streamlit app for planner review before Monday rearrangement.

**Important:** `arrow_store_optimiser.py` at the repo root is a **rule-based demo/benchmark** for leadership presentations — it is NOT the production solver. The production solver is `src/solver/ip_model.py`.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run solver on dummy data (no Fabric connection needed)
python src/solver/run_solver.py --data dummy --store all
python src/solver/run_solver.py --data dummy --store 8194   # single store

# Launch Streamlit planning UI
streamlit run src/streamlit_app/app.py

# Compute revenue rates standalone
python src/data_pipeline/revenue_rate_builder.py

# Run size-break monitor (daily CORE style SOH check)
python src/utils/size_break_monitor.py

# Run tests
pytest tests/
```

## Architecture

### Data Flow

```
data/raw/ (sales_sample.csv, soh_sample.csv, store_capacity.csv)
    ↓
src/data_pipeline/revenue_rate_builder.py
    → compute_revenue_rates(): rolling 4-week window, thin-bucket fallback to category average
    ↓
src/solver/run_solver.py  (batch runner)
    → src/solver/ip_model.py  (PuLP IP model per store)
    ↓
data/processed/recommendations_YYYY-MM-DD.csv
data/processed/solver_results_YYYY-MM-DD.json
    ↓
src/streamlit_app/app.py  (4-page planning UI)
    → Pages: Store Selector → Allocation View → What-if Simulation → Export & Activate
```

### Core Components

**`src/data_pipeline/revenue_rate_builder.py`**
- `assign_priceband()`: maps UNITMRP to Economy/Mid/Premium tiers using thresholds in `config/config.yaml`
- `compute_revenue_rates()`: builds bucket revenue rates; if a bucket has < 2 weeks of data, seeds from the category-priceband average across comparable stores (thin-bucket fallback)
- `load_dummy_data()`: reads CSVs from `data/raw/` — no Fabric connection

**`src/solver/ip_model.py`**
- `SolverConfig` dataclass: holds `floor_weight`, `cap_multiplier`, `timeout_secs`
- `solve_store()`: single-store IP model using PuLP + CBC solver
  - Decision variable: `display_share[bucket]` = integer % of display floor (1–45 range)
  - Objective: maximize `SUM(display_share × revenue_rate)`
  - Constraints C1–C6: shares sum to 100, integer values, per-bucket floor/cap, style slot limit
  - Dynamic floors/caps prevent bang-bang allocation (all budget to top 1–2 buckets)
- `format_output_table()`: produces signal column (GREEN=INCREASE, YELLOW=HOLD, RED=REDUCE)

**`src/solver/run_solver.py`**
- `run_all_stores()`: batch-solves every store, writes CSV + JSON to `data/processed/`
- `load_store_capacity()`: reads MIN_OPTION_COUNT from `data/raw/store_capacity.csv`
- CLI: `--data {dummy|fabric}`, `--store {all|STORE_CODE}`

**`src/streamlit_app/app.py`**
- 4-page navigation via sidebar radio, session state persists selected store across pages
- Page 3 (What-if): re-runs solver with a pinned bucket constraint to simulate planner overrides
- `src/streamlit_app/pages/` stubs exist but logic lives in `app.py`

**`src/utils/size_break_monitor.py`**
- `check_size_breaks()`: flags CORE styles (pivotable sizes M, L) with SOH ≤ 2 for next-day warehouse replenishment — runs daily independent of the weekly cycle

### Key Concepts

**Bucket**: composite key `"CATEGORY | priceband"` (e.g., `"FORMAL SHIRTS | Premium"`)

**Priceband thresholds** (configured in `config/config.yaml`, reviewed quarterly):
- Economy: ₹0–₹1,999
- Mid: ₹2,000–₹2,999
- Premium: ₹3,000+

**Data quality filters** applied upstream: `INVOICETYPE="SALES"`, `QUALITY="Q1"`, `ON_HOLD=0`, positive quantities

**CORE vs FASHION** (`FASHION` field in SOH): CORE = pivotable sizes — only CORE styles trigger the size-break daily monitor

**Thin-bucket fallback**: buckets with < 2 weeks of data get seeded from category-priceband averages to avoid zeroing out new arrivals in the solver

**Solver warning**: if a store has > 100 active buckets the solver loses meaningful allocation freedom — this is flagged in output metadata

## Configuration

`config/config.yaml` controls:
- `floor_weight` (default 0.5) and `cap_multiplier` (default 1.5): tune how aggressively the solver can concentrate or diversify allocation
- `timeout_secs` (default 60): per-store solver time limit
- Priceband MRP thresholds
- Brand name and pilot store list

## Data Schemas

**Input — Sales** (`data/raw/sales_sample.csv`): `SAP_STORECODE, CATEGORY, UNITMRP, NETAMT, INVOICE_DATE, QUANTITY, INVOICETYPE, QUALITY, FASHION`

**Input — SOH** (`data/raw/soh_sample.csv`): `SAP_STORE_ID, CLASS, MRP, SOH, LOAD_RUN_DATE, ON_HOLD, QUALITY, FASHION`

**Input — Store Capacity** (`data/raw/store_capacity.csv`): `STORE_CODE, STORE_NAME, REGION, MIN_OPTION_COUNT, MAX_OPTION_COUNT`

**Output — Recommendations** (`data/processed/recommendations_YYYY-MM-DD.csv`): `store_id, bucket_key, display_share_pct, floor_share, cap_share, revenue_rate, style_slots, expected_rev_index, signal`

## Fabric Integration

For production runs (`--data fabric`), a `FABRIC_CONNECTION_STRING` environment variable must be set in `.env`. The SQL queries for Fabric extraction are in `Arvind_Store_Optimisation_Queries.sql`. Local development uses dummy CSV data and requires no Fabric connection.

## Project Phases

| Phase | Status | Approach |
|-------|--------|----------|
| Phase 1 | LIVE | IP solver (PuLP) on rolling 4-week revenue rates |
| Phase 1.5 | Next | IP + early ML once 4–6 months of display Excel data accumulate |
| Phase 2 | Future | Full ML (LightGBM) + SAM/CLIP image analysis |
