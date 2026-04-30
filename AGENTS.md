# AI Coding Agent Instructions — Arrow Store Revenue Optimisation

> This file helps AI agents understand the codebase and be immediately productive.

## Project Overview

**Purpose**: Optimize display floor allocation for Arvind Fashions (Arrow) stores to maximize revenue using Integer Programming (IP).

**Key Workflow**: Every Sunday night, the system pulls stock-on-hand data, computes revenue rates per bucket, runs an IP solver, and surfaces recommendations via Streamlit.

## Build & Run Commands

| Task | Command |
|------|---------|
| Install dependencies | `pip install -r requirements.txt` |
| Run optimizer | `python arrow_store_optimiser.py` |
| Launch Streamlit app | `streamlit run src/streamlit_app/app.py` |
| Run tests | `pytest tests/` |

## Project Structure

```
├── arrow_store_optimiser.py    # Main entry point
├── config/config.yaml          # Configuration
├── src/
│   ├── data_pipeline/          # Revenue rate computation
│   ├── solver/                # IP optimization model
│   ├── streamlit_app/         # UI application
│   └── utils/                 # Utilities
├── data/
│   ├── raw/                   # Input data (SOH, sales, capacity)
│   └── processed/             # Solver outputs
└── docs/ALGORITHM_AND_DATA.md # Algorithm documentation
```

## Key Concepts

- **Bucket**: Planning unit = Category × Priceband (e.g., "FORMAL SHIRTS | Premium")
- **display_share**: Decision variable — % of display floor style slots (integer 1–45)
- **revenue_rate**: Revenue per unit of inventory over rolling 4 weeks

## Important Conventions

- Use dummy data mode for testing (no Fabric connection needed)
- Output files: `data/processed/recommendations_YYYY-MM-DD.csv`, `solver_results_YYYY-MM-DD.json`
- Configuration via `config/config.yaml` — no hardcoded values

## Potential Pitfalls

- IP solver may take time for large stores — check convergence
- Thin-data buckets fallback to category averages
- Streamlit app requires `PYTHONPATH` set or run from project root

## Documentation Links

- [Algorithm & Data](docs/ALGORITHM_AND_DATA.md) — Detailed model explanation
- [Store Optimisation Queries](Arvind_Store_Optimisation_Queries.sql) — SQL queries for Fabric