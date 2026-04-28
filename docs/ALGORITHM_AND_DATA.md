# Arrow Brand — Store Revenue Optimisation
## Algorithm, Dataset & Navigation Reference

> **Audience:** Leadership, Area Managers, Merchandising
> **Phase:** Phase 1 — Integer Programming Optimisation (live)
> **Brand:** Arrow | Arvind Fashions Limited

---

## 1. What This System Does

Every **Sunday night**, the system automatically:

1. Pulls the latest stock-on-hand (SOH) snapshot from the data warehouse
2. Computes **rolling 4-week revenue rates** per store × category × price tier (a "bucket")
3. Runs an **Integer Programming (IP) solver** to find the display allocation that maximises expected revenue
4. Surfaces recommendations in the **Streamlit internal tool** — planners and area managers can review, simulate, and approve before Monday rearrangement

Store teams receive a **Monday plan** showing exactly how many display style slots each bucket should get.

---

## 2. Core Concept: The Bucket

A **bucket** is the planning unit. It groups products that compete for the same display space.

```
Bucket = Category  |  Priceband
Example: FORMAL SHIRTS | Premium
         CASUAL SHIRTS  | Mid
         CHINOS         | Economy
```

**Priceband thresholds (Arrow, reviewed quarterly):**

| Priceband | MRP Range |
|-----------|-----------|
| Economy   | Rs 0 – Rs 1,999 |
| Mid       | Rs 2,000 – Rs 2,999 |
| Premium   | Rs 3,000+ |

For Arrow's focused assortment, each store typically has **8–12 active buckets** — well within the solver's ideal operating range.

---

## 3. Revenue Rate — The Key Input

```
revenue_rate[store, bucket] =  total revenue earned in this bucket over last 4 weeks
                               ────────────────────────────────────────────────────
                               average weekly stock-on-hand in this bucket last 4 weeks
```

This measures how many rupees of revenue each unit of inventory committed to a bucket generated. A high rate = this bucket converts inventory into revenue efficiently.

**Data sources:**
- Sales: `FACT_FNO_SALES_TC_ONLINE_BASE` — INVOICETYPE = SALES, QUALITY = Q1, QUANTITY > 0
- SOH: `FACT_FNO_SOH_DAILY` — QUALITY = Q1, ON_HOLD = 0

**Thin-data fallback:** If a bucket has fewer than 2 weeks of sales history (e.g. new arrival), its rate is seeded from the average rate of that category and priceband across comparable stores.

---

## 4. The Optimisation Model (IP Solver)

### Decision Variable
```
display_share[store, bucket]  =  % of display floor style slots given to this bucket
                                  Integer value, 1 to 45
```

### Objective Function
```
Maximise:  SUM over all buckets [ display_share[bucket] x revenue_rate[bucket] ]
```

The solver finds the integer allocation that maximises projected revenue, subject to all constraints.

### Constraints

| ID | Rule | Formula |
|----|------|---------|
| C1 | Shares must sum to 100% | SUM(display_share) = 100 |
| C2 | Whole-number percentages only | display_share in integers |
| C3 | No bucket exceeds 45% | display_share <= 45 |
| C4 | No bucket below 1% | display_share >= 1 |
| C5 | Style count within display capacity | SUM(share/100 x capacity) <= capacity |
| C6 | Only stock existing buckets | display_share = 0 if bucket never stocked |

**Why these constraints?**
C3/C4 prevent extreme concentration — no single bucket dominates or disappears entirely. C5 links the % recommendation to physical style slots (the MIN_OPTION_COUNT from VM guidelines). C1 ensures the entire floor is always allocated.

### Traffic Light Signals

| Signal | Meaning | When |
|--------|---------|------|
| INCREASE | Top performer — maximise display space | Recommended share >= 35% |
| HOLD | Mid-range performer — maintain allocation | 2% – 34% |
| REDUCE | Low performer — at minimum floor | Exactly 1% (floor constraint) |

---

## 5. Dataset Schema

### Sales Table (FACT_FNO_SALES_TC_ONLINE_BASE)

| Column | Description |
|--------|-------------|
| SAP_STORECODE | Store identifier |
| CATEGORY | Product category (FORMAL SHIRTS, CHINOS, etc.) |
| UNITMRP | MRP per unit in Rs — used to derive priceband |
| NETAMT | Net revenue after discount |
| INVOICE_DATE | Transaction date |
| QUANTITY | Units sold (positive = sale) |
| INVOICETYPE | SALES / RETURN — filter to SALES only |
| QUALITY | Q1 = first quality (exclude Q2 seconds) |
| FASHION | CORE = pivotable sizes (M, L in shirts etc.) |

### SOH Table (FACT_FNO_SOH_DAILY)

| Column | Description |
|--------|-------------|
| SAP_STORE_ID | Store identifier |
| CLASS | Product category — maps to CATEGORY in sales |
| MRP | MRP per unit — used to derive priceband |
| SOH | Stock on hand units at snapshot date |
| LOAD_RUN_DATE | Snapshot date — Monday morning for model input |
| ON_HOLD | Units unavailable for sale (exclude) |
| QUALITY | Q1 only |
| FASHION | CORE / FASHION |

### Store Capacity Table (store_capacity.csv)

| Column | Description |
|--------|-------------|
| STORE_CODE | SAP store code |
| STORE_NAME | Display name |
| REGION | Region code (KAR, TN, MH, NCR, MUM) |
| SALES_AREA | Floor area sq ft |
| MIN_OPTION_COUNT | Display capacity — number of style slots on floor |

### Solver Output (recommendations_YYYY-MM-DD.csv)

| Column | Description |
|--------|-------------|
| store_id | SAP store code |
| bucket_key | CATEGORY \| Priceband |
| display_share_pct | Recommended % of display floor for this bucket |
| revenue_rate | Rs revenue per unit of inventory (4-week rolling) |
| style_slots | Physical style slot count (share% x MIN_OPTION_COUNT) |
| expected_rev_index | display_share x revenue_rate (solver objective contribution) |
| signal | INCREASE / HOLD / REDUCE |

---

## 6. App Navigation Guide

The Streamlit tool has **4 screens**, accessed via the left sidebar. Always start at Screen 1.

```
SIDEBAR RADIO
  |
  +-- 1. Store Selector         (start here)
  |        Select region -> Select store -> store saved to session
  |        -> Success message confirms selection
  |
  +-- 2. Allocation Table       (requires store selected)
  |        View IP solver recommendations for chosen store
  |        Traffic lights: green=INCREASE, yellow=HOLD, red=REDUCE
  |        Style Slots column = physical count on the display floor
  |
  +-- 3. What-If Simulation     (requires store selected)
  |        Pin a bucket to a custom % -> solver re-runs on remaining
  |        MUST enter override reason before saving
  |        Planners use this to test "what if we feature this collection?"
  |
  +-- 4. Export & Activate      (requires store selected)
           Download Monday allocation plan (.csv) for store team
           Shows size-break risk flags (CORE styles near zero SOH)
           Activation date = next Monday
```

### Step-by-Step Demo Walkthrough

1. Open sidebar, click **Store Selector**
2. Filter by Region (e.g. KAR for Karnataka)
3. Select a store from the dropdown (e.g. Brigade Rd|BLR)
4. Green success message appears — store is now active for all screens
5. Click **Allocation Table** in sidebar
6. Review traffic-light table: top 1–2 buckets get INCREASE (green), most others at REDUCE (floor minimum)
7. Click **What-If Simulation** — pick a bucket, drag the share slider, add a reason, click "Re-run solver"
8. Click **Export & Activate** — download the Monday plan CSV

---

## 7. Demo App (arrow_store_optimiser.py)

A self-contained benchmark tool for leadership demos. Run with:
```
streamlit run arrow_store_optimiser.py
```

Uses synthetic quarterly data (8 stores, 12 buckets each) with a **rule-based iterative engine** — NOT the IP solver. This is the Phase 1 benchmark. The IP solver (`src/streamlit_app/app.py`) is the production system.

**Rule-based engine logic:**
1. Score all buckets by selected metric (revenue or revenue/unit)
2. Lock the top-N buckets from reduction
3. Iterative loop: transfer 1% stock from lowest-scored bucket to highest-scored
4. Stop when: target uplift achieved, max iterations hit, or no valid transfer exists
5. Concentration penalty (HHI index) discourages over-allocation to one bucket

**Sidebar controls:**
- Store dropdown — choose one of 8 synthetic Arrow stores
- Target Revenue Uplift % — how much revenue growth to aim for
- Max bucket share cap / min floor — constraint bounds
- Transfer step size — granularity of each reallocation step
- Lock top-N — protect best performers from being reduced
- Concentration penalty — diversity control (0 = none, 0.30 = heavy)

---

## 8. Algorithm Progression (Roadmap)

| Phase | Algorithm | Data Required | Status |
|-------|-----------|---------------|--------|
| Phase 1 | Integer Programming (PuLP) using rolling 4-week revenue rates | SOH + Sales from Fabric | Live |
| Phase 1.5 | IP + early ML on observed display data | 4–6 months of display Excel uploads | Next |
| Phase 2 | Full ML model (LightGBM) + SAM/CLIP image analysis | 2 years of weekly display data + wall photos | Future |

---

## 9. Key Business Rules

- **Monday only:** Recommendations activate on the next Monday. No mid-week changes.
- **Next-day size replenishment:** CORE style sizes at SOH <= 2 units trigger automatic warehouse replenishment — independent of the weekly cycle. See `src/utils/size_break_monitor.py`.
- **Override requires reason:** Any deviation from solver output must be logged with a written reason before saving. This feeds Phase 1.5 model improvement.
- **Arrow first:** Phase 1 covers Arrow brand only (USPA, Flying Machine, Excalibur follow post-validation).
- **Quarterly taxonomy review:** Priceband thresholds reviewed with Merchandising as Arrow's price range evolves.

---

*Arrow Brand | Arvind Fashions Limited | Phase 1 — Integer Programming | Internal Use Only*
