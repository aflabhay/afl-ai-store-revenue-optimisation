# Arvind Fashions — Store Revenue Optimisation System

> **Business Requirements Document:** See [`docs/BRD_v2.0.docx`](docs/BRD_v2.0.docx)

---

## 1. Project Origin & Business Context

This project was initiated following a series of store visits to Arvind Fashions Limited stores across India. The key observations from those visits that drove the need for this system:

- **Monday rearrangement cycle:** Store teams physically rearrange the display floor every Monday. Until now, this was done entirely by intuition and store manager experience — no data-driven guidance existed.
- **65/35 display-to-backroom split:** Approximately 65% of total store inventory is on display at any given time; 35% sits in the backroom as a replenishment buffer.
- **Three-layer stock flow:** As display items sell during the week, staff pull matching sizes from the backroom to refill the display. If backroom runs out of a specific size, the warehouse replenishes that size **next day** — independently of the Monday cycle. This means virtually all committed inventory has a path to customers across a week.
- **Style count as the true constraint:** Store display capacity is measured in **number of distinct styles (options)** that can be shown — not units. The `Min Option Count` per store (from the store capacity Excel, sourced from VM guidelines) is the binding physical constraint.
- **No structured display data:** Store managers currently photograph walls every Monday and share via WhatsApp — unstructured, unsearchable, and unavailable for analytics.

### What the system does

For each Arvind Fashions store, every Sunday night, the system:
1. Pulls the latest stock-on-hand (SOH) snapshot from Microsoft Fabric Data Warehouse
2. Computes rolling 4-week revenue rates per bucket (Category × Priceband)
3. Runs an **Integer Programming (IP) optimisation model** to recommend the optimal display share allocation across all active buckets
4. Surfaces recommendations through a **Streamlit internal tool** that planners and area managers can interact with, simulate what-if scenarios, and approve before Monday rearrangement

---

## 2. Key Concepts & Terminology

| Term | Definition |
|---|---|
| **Bucket** | A unique Collection × Category × Priceband combination (e.g. Arrow / Formal Shirts / Premium) |
| **display_share[store, bucket]** | The % of the display floor allocated to a bucket on Monday (the decision variable) |
| **display_capacity[store]** | Min Option Count — number of distinct styles the store can display on Monday, from store capacity Excel |
| **total_inventory[store]** | Total inventory physically in the store on Monday morning — the SOH snapshot, net of all sales |
| **revenue_rate[store, bucket]** | ₹ revenue generated per unit of inventory committed to this bucket over the last 4 weeks |
| **Pivotable size / CORE style** | Best-selling sizes (e.g. M, L in shirts) — if these sell out, warehouse replenishes next day |
| **Monday rearrangement** | Weekly physical rearrangement of the display floor based on IP solver recommendations |
| **Phase 1** | IP optimisation model using rolling 4-week revenue rates — live now |
| **Phase 1.5** | Hybrid: IP model + early ML using display Excel data once 4–6 months collected |
| **Phase 2** | Full ML model replacing revenue rate estimation, using 2 years of weekly display data |

---

## 3. Optimisation Model

### Decision Variable
```
display_share[store, bucket] = % of display floor style slots given to this bucket (integer, 1–45)
```

### Objective Function
```
Maximise:  SUM over all buckets [ display_share[store, bucket] × revenue_rate[store, bucket] ]
```

`display_capacity[store]` is a constant per store and does not affect which allocation the solver picks — it only appears in constraint C5.

### Revenue Rate
```
revenue_rate[store, bucket] = bucket_revenue[store, bucket, last 4 weeks]
                               / bucket_inventory[store, bucket, last 4 weeks]
```

Revenue per unit of total committed inventory (display + backroom + warehouse replenishments). Refreshed every Sunday from Fabric. Falls back to category average across comparable stores if fewer than 2 weeks of data exist for a bucket.

### Constraints

| ID | Constraint | Formula |
|---|---|---|
| C1 | Display shares sum to 100% | SUM(display_share) = 100 |
| C2 | Whole-number percentages only | display_share ∈ ℤ |
| C3 | No bucket exceeds 45% | display_share ≤ 45 |
| C4 | No bucket below 1% | display_share ≥ 1 |
| C5 | Style count ≤ display capacity | SUM(ROUND(share/100 × display_capacity)) ≤ display_capacity |
| C6 | Only existing buckets | display_share = 0 if bucket never stocked in store |

### Solver Meaningfulness — Bucket Count Warning

The solver's ability to find a meaningfully differentiated allocation depends on active bucket count:

| Active buckets | Solver freedom | Action |
|---|---|---|
| < 20 | Full — ideal | Proceed as designed |
| 20–49 | Good | Proceed, monitor outputs |
| 50–99 | Limited | Consider Category-only (drop Priceband) |
| ≥ 100 | None — floor binds | Must coarsen bucket definition |

**For Arrow specifically** (single brand, focused assortment: Formal Shirts / Chinos / Trousers / Casual Shirts × 2–3 pricepoints) expected bucket count per store is **6–15** — well within the ideal range.

---

## 4. Data Sources

### Fabric Data Warehouse (Microsoft)

| Table | Purpose |
|---|---|
| `[prd].[FACT_FNO_SALES_TC_ONLINE_BASE]` | Transaction-level sales — units, revenue, MRP, discount |
| `[prd].[FACT_FNO_SOH_DAILY]` | Daily stock-on-hand snapshot per SKU per store |

### External Inputs

| Input | Source | Used for |
|---|---|---|
| Store capacity Excel | Merchandising / VM team | `display_capacity[store]` — Min Option Count per store |
| Store closure records | Area Managers | Exclude closed-period data from revenue rate calculation |

### Dummy Data (this repo)

Sample data files in `data/raw/` simulate the Fabric tables for local development and testing. See `data/README.md` for schema details.

---

## 5. Tech Stack

| Component | Technology |
|---|---|
| Optimisation solver | Python — PuLP (open source IP solver) |
| Data layer | Microsoft Fabric Data Warehouse (T-SQL) |
| Database connector | `pyodbc` with Fabric ODBC driver |
| App framework | Streamlit |
| App hosting | Azure App Service |
| Image storage | Azure Blob Storage |
| Image capture | Power Apps (no-code) |
| Image analysis (Phase 2) | SAM (Segment Anything Model, Meta) + CLIP (OpenAI) |

---

## 6. Project Phases

### Phase 1 — IP Optimisation (current)
- Rolling 4-week revenue rates from Fabric
- Integer Programming solver (PuLP)
- Streamlit internal tool for planner interaction
- Store capacity Excel as display constraint

### Phase 1.5 — Hybrid ML (once 4–6 months display data available)
- Weekly display Excel uploads via Power Apps → Azure Blob
- ML model on observed display share data supplements revenue rates
- Shadow mode: ML runs alongside IP, validated before promotion

### Phase 2 — Full ML (once 2 years display data available)
- ML model replaces revenue rate estimation entirely
- SAM + CLIP extracts style counts from Monday wall photos
- Per-bucket display share becomes a directly observed input

---

## 7. Repository Structure

```
arvind-store-optimisation/
│
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── .env.example                       # Environment variables template
├── .gitignore
│
├── config/
│   └── config.yaml                    # Store list, brand config, solver params
│
├── data/
│   ├── README.md                      # Schema documentation
│   ├── raw/
│   │   ├── sales_sample.csv           # Dummy sales transactions
│   │   ├── soh_sample.csv             # Dummy SOH daily snapshots
│   │   └── store_capacity.csv         # Min/Max option count per store
│   └── processed/
│       └── revenue_rates_sample.csv   # Pre-computed revenue rates (dummy)
│
├── src/
│   ├── data_pipeline/
│   │   ├── __init__.py
│   │   ├── fabric_connector.py        # Fabric ODBC connection
│   │   ├── revenue_rate_builder.py    # Rolling 4-week rate computation
│   │   └── soh_snapshot.py            # Monday SOH extraction
│   │
│   ├── solver/
│   │   ├── __init__.py
│   │   ├── ip_model.py                # Core IP model (PuLP)
│   │   ├── constraints.py             # C1–C6 constraint definitions
│   │   └── run_solver.py              # Batch solver across all stores
│   │
│   ├── streamlit_app/
│   │   ├── app.py                     # Main Streamlit entry point
│   │   ├── pages/
│   │   │   ├── 01_store_selector.py   # Screen 1 — store filter
│   │   │   ├── 02_allocation.py       # Screen 2 — allocation table
│   │   │   ├── 03_whatif.py           # Screen 3 — what-if simulation
│   │   │   └── 04_export.py           # Screen 4 — export & activate
│   │   └── utils/
│   │       ├── charts.py              # Traffic light visualisations
│   │       └── export_helpers.py      # Excel / PDF generation
│   │
│   └── utils/
│       ├── __init__.py
│       ├── priceband.py               # Economy / Mid / Premium classification
│       └── size_break_monitor.py      # Daily CORE style SOH check
│
├── notebooks/
│   ├── 01_data_exploration.ipynb      # Initial EDA on sales and SOH data
│   ├── 02_revenue_rate_analysis.ipynb # Revenue rate distribution analysis
│   ├── 03_solver_demo.ipynb           # Step-by-step solver walkthrough
│   └── 04_bucket_count_diagnostic.ipynb # Solver meaningfulness check
│
├── tests/
│   ├── test_constraints.py            # Verify C1–C6 are always satisfied
│   ├── test_revenue_rate.py           # Revenue rate computation tests
│   └── test_solver.py                 # Solver output validation
│
└── docs/
    └── BRD_v2.0.docx                  # Full Business Requirements Document
```

---

## 8. Quick Start (Local Development with Dummy Data)

```bash
# 1. Clone the repo
git clone https://github.com/your-org/arvind-store-optimisation.git
cd arvind-store-optimisation

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate   # Mac/Linux
venv\Scripts\activate      # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment variables
cp .env.example .env
# Edit .env — add your Fabric connection string when ready

# 5. Run solver on dummy data
python src/solver/run_solver.py --data dummy --store all

# 6. Launch Streamlit app
streamlit run src/streamlit_app/app.py
```

---

## 9. Implementation Timeline

| Week | Milestone |
|---|---|
| 1 | Environment setup, store capacity Excel validation, bucket taxonomy sign-off |
| 2 | Rolling 4-week revenue rate pipeline in Fabric, Sunday refresh schedule |
| 3 | IP model coded in PuLP, all 6 constraints, full fleet test run |
| 4 | Edge case handling, infeasibility fallbacks, fleet stress test |
| 5 | Pilot validation — 50 stores, 3 regions, Area Manager feedback |
| 6 | Streamlit Screens 1 & 2 — store selector + allocation table |
| 7 | Streamlit Screens 3 & 4 — what-if panel + export & activate |
| 8 | Override capture, size-break daily job, internal end-to-end test |
| 9 | User acceptance testing — planners + Area Managers |
| 10 | Deploy to Azure App Service, first live Monday recommendations |

---

## 10. Key Business Rules

- **Monday only:** All display rearrangement recommendations activate on Monday. Mid-week changes queue for the following Monday.
- **Next-day size replenishment:** When a CORE style size reaches zero SOH, a warehouse replenishment request is triggered automatically — independent of the Monday cycle.
- **Override requires reason:** Any planner deviation from the solver recommendation must be logged with a written reason before saving — this data feeds Phase 1.5 model improvement.
- **Arrow first:** Phase 1 covers Arrow brand only. Expansion to USPA, Flying Machine, and Excalibur follows once the model is validated.
- **Quarterly taxonomy review:** Bucket definitions (Category × Priceband thresholds) are reviewed with Merchandising every quarter as Arrow's price range evolves.

---

## 11. Contact & Ownership

| Role | Responsibility |
|---|---|
| Analytics / Data Science | IP model, revenue rate pipeline, solver validation |
| Technology | Streamlit app, Fabric integration, Azure deployment |
| Merchandising | Bucket taxonomy, priceband thresholds, store capacity Excel |
| Area Managers | Pilot validation, override feedback, store closure records |
| Store Operations | Monday activation, Power App image uploads |

---

*Built for Arvind Fashions Limited | Arrow Brand | Phase 1 — Integer Programming Optimisation*
