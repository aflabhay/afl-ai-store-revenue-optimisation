"""
╔══════════════════════════════════════════════════════════════════╗
║   ARROW BRAND — Store Revenue Optimization Tool                  ║
║   Rule-Based Stock Reallocation Advisor                          ║
║   Arvind Fashions Limited                                        ║
║                                                                  ║
║   Run:  streamlit run arrow_store_optimizer.py                   ║
║   Deps: pip install streamlit pandas numpy openpyxl xlsxwriter   ║
╚══════════════════════════════════════════════════════════════════╝
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
import random
from copy import deepcopy

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Arrow | Store Revenue Optimizer",
    page_icon="🏹",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# CUSTOM CSS — Clean industrial retail aesthetic
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}

/* Header */
.main-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #f8fafc;
    padding: 2rem 2.5rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    border-left: 5px solid #f59e0b;
}
.main-header h1 { 
    font-size: 1.8rem; font-weight: 600; 
    margin: 0 0 0.25rem 0; letter-spacing: -0.5px;
    font-family: 'IBM Plex Mono', monospace;
    color: #f8fafc;
}
.main-header p { 
    font-size: 0.85rem; color: #94a3b8; 
    margin: 0; font-weight: 300; letter-spacing: 0.5px;
}
.arrow-badge {
    display: inline-block;
    background: #f59e0b;
    color: #0f172a;
    font-size: 0.65rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 20px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 0.75rem;
}

/* KPI cards */
.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 1rem 0; }
.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 1.1rem 1.25rem;
    border-top: 3px solid #f59e0b;
}
.kpi-card.green { border-top-color: #10b981; }
.kpi-card.blue  { border-top-color: #3b82f6; }
.kpi-card.red   { border-top-color: #ef4444; }
.kpi-label { font-size: 0.72rem; color: #64748b; font-weight: 500; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 4px; }
.kpi-value { font-size: 1.6rem; font-weight: 600; color: #0f172a; font-family: 'IBM Plex Mono', monospace; line-height: 1; }
.kpi-delta { font-size: 0.78rem; margin-top: 4px; font-weight: 500; }
.kpi-delta.up   { color: #10b981; }
.kpi-delta.down { color: #ef4444; }
.kpi-delta.neutral { color: #64748b; }

/* Section headers */
.section-title {
    font-size: 0.7rem; font-weight: 600; letter-spacing: 2px;
    text-transform: uppercase; color: #94a3b8;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 0.5rem; margin: 1.5rem 0 1rem 0;
}

/* Allocation table */
.alloc-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.alloc-table thead tr { background: #0f172a; color: #f8fafc; }
.alloc-table thead th { padding: 10px 14px; text-align: left; font-weight: 500; letter-spacing: 0.5px; font-size: 0.72rem; text-transform: uppercase; }
.alloc-table tbody tr:nth-child(even) { background: #f8fafc; }
.alloc-table tbody tr:hover { background: #fef3c7; transition: background 0.15s; }
.alloc-table tbody td { padding: 9px 14px; border-bottom: 1px solid #e2e8f0; color: #334155; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: 600; }
.badge-up    { background: #dcfce7; color: #166534; }
.badge-down  { background: #fee2e2; color: #991b1b; }
.badge-same  { background: #f1f5f9; color: #475569; }
.badge-warn  { background: #fef9c3; color: #854d0e; }
.bar-base { height: 8px; border-radius: 4px; background: #e2e8f0; margin-top: 4px; }
.bar-fill { height: 8px; border-radius: 4px; background: #3b82f6; }
.bar-fill-rec { height: 8px; border-radius: 4px; background: #f59e0b; }

/* Rule sliders section */
.rule-card {
    background: #fafafa;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
}
.rule-title { font-weight: 600; font-size: 0.88rem; color: #0f172a; margin-bottom: 0.25rem; }
.rule-desc  { font-size: 0.75rem; color: #64748b; margin-bottom: 0.75rem; }

/* Info callout */
.callout {
    padding: 0.85rem 1.1rem;
    border-radius: 8px;
    font-size: 0.82rem;
    margin: 0.75rem 0;
    border-left: 3px solid;
}
.callout-info    { background: #eff6ff; border-color: #3b82f6; color: #1e40af; }
.callout-success { background: #f0fdf4; border-color: #10b981; color: #065f46; }
.callout-warn    { background: #fffbeb; border-color: #f59e0b; color: #92400e; }
.callout-danger  { background: #fef2f2; border-color: #ef4444; color: #991b1b; }

/* Explanation block */
.explain-block {
    background: #0f172a;
    color: #94a3b8;
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    line-height: 1.8;
    margin-top: 1rem;
}
.explain-block .highlight { color: #f59e0b; font-weight: 600; }
.explain-block .green { color: #34d399; }
.explain-block .red   { color: #f87171; }

/* Download button */
.dl-section {
    background: linear-gradient(135deg, #0f172a, #1e3a5f);
    border-radius: 10px;
    padding: 1.5rem;
    text-align: center;
    margin-top: 1.5rem;
}
.dl-section p { color: #94a3b8; font-size: 0.82rem; margin: 0 0 1rem 0; }

/* Streamlit overrides */
div[data-testid="stSlider"] > div { padding-top: 0 !important; }
.stSlider label { font-size: 0.8rem !important; font-weight: 500 !important; }
section[data-testid="stSidebar"] { background: #0f172a; }
section[data-testid="stSidebar"] .stMarkdown { color: #94a3b8; }
section[data-testid="stSidebar"] label { color: #cbd5e1 !important; }
section[data-testid="stSidebar"] .stSelectbox label { color: #cbd5e1 !important; }
section[data-testid="stSidebar"] h1, 
section[data-testid="stSidebar"] h2, 
section[data-testid="stSidebar"] h3 { color: #f8fafc !important; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SYNTHETIC DATA GENERATOR
# ─────────────────────────────────────────────
@st.cache_data
def generate_data(seed: int = 42) -> pd.DataFrame:
    """
    Generates realistic synthetic quarterly bucket data for Arrow stores.
    Schema mirrors BRD exactly:
      store_id, quarter, collection, category, pricepoint,
      stock_share_pct, units_sold, revenue, weighted_mrp, discount_depth
    """
    rng = np.random.default_rng(seed)

    stores = {
        "STORE_BLR_MG":    ("South", "Bengaluru"),
        "STORE_MUM_LINK":  ("West",  "Mumbai"),
        "STORE_DEL_CP":    ("North", "Delhi"),
        "STORE_HYD_HIL":   ("South", "Hyderabad"),
        "STORE_CHN_EXP":   ("South", "Chennai"),
        "STORE_PUN_FC":    ("West",  "Pune"),
        "STORE_KOL_QG":    ("East",  "Kolkata"),
        "STORE_AHM_AL":    ("West",  "Ahmedabad"),
    }

    collections = ["Heritage", "Urban Edge", "Classic Essentials", "Active Fit"]
    categories  = ["Formal Shirts", "Casual Shirts", "T-Shirts", "Trousers", "Chinos", "Jackets"]
    pricepoints = ["500-999", "1000-1999", "2000-3499", "3500+"]
    quarters    = ["Q1-2024", "Q2-2024", "Q3-2024", "Q4-2024"]

    # Seasonality multipliers per category per quarter
    season_mult = {
        "Formal Shirts": [1.0, 0.85, 0.90, 1.20],
        "Casual Shirts":  [0.90, 1.10, 1.05, 1.10],
        "T-Shirts":       [0.80, 1.30, 1.25, 0.85],
        "Trousers":       [1.05, 0.90, 0.95, 1.15],
        "Chinos":         [1.10, 1.00, 0.95, 1.10],
        "Jackets":        [1.40, 0.60, 0.70, 1.30],
    }

    # Base revenue per unit by pricepoint
    rev_map = {"500-999": 720, "1000-1999": 1450, "2000-3499": 2600, "3500+": 4200}

    records = []
    for store_id, (region, city) in stores.items():
        total_stock = int(rng.integers(800, 2500))
        store_tier = "Premium" if city in ["Mumbai", "Delhi"] else "Standard"

        for q_idx, quarter in enumerate(quarters):
            # Random stock shares summing to 100
            raw_shares = rng.dirichlet(np.ones(len(categories) * len(collections[:2])) * 2)
            raw_shares = np.clip(raw_shares, 0.01, 0.44)
            raw_shares /= raw_shares.sum()

            idx = 0
            for col in collections[:2]:      # 2 collections × 6 categories = 12 buckets
                for cat in categories:
                    for pp in [pricepoints[rng.integers(0, len(pricepoints))]]:
                        share = float(raw_shares[idx % len(raw_shares)])
                        idx += 1

                        units_alloc = int(total_stock * share)
                        base_sell_rate = rng.uniform(0.45, 0.85) * season_mult[cat][q_idx]
                        units_sold = int(units_alloc * min(base_sell_rate, 0.99))

                        mrp = rev_map[pp] * rng.uniform(0.9, 1.1)
                        disc = rng.uniform(0.05, 0.35)
                        selling_price = mrp * (1 - disc)
                        revenue = units_sold * selling_price

                        records.append({
                            "store_id":       store_id,
                            "region":         region,
                            "city":           city,
                            "store_tier":     store_tier,
                            "total_stock":    total_stock,
                            "quarter":        quarter,
                            "collection":     col,
                            "category":       cat,
                            "pricepoint":     pp,
                            "stock_share_pct": round(share * 100, 2),
                            "units_allocated": units_alloc,
                            "units_sold":      units_sold,
                            "sell_through_pct": round(units_sold / max(units_alloc, 1) * 100, 1),
                            "weighted_mrp":    round(mrp, 0),
                            "discount_depth":  round(disc * 100, 1),
                            "revenue":         round(revenue, 0),
                            "revenue_per_unit": round(revenue / max(units_sold, 1), 0),
                        })

    return pd.DataFrame(records)


# ─────────────────────────────────────────────
# RULE-BASED RECOMMENDATION ENGINE
# ─────────────────────────────────────────────
def run_rule_based_engine(
    df_store: pd.DataFrame,
    uplift_target_pct: float,
    max_bucket_share: float,       # default 45
    min_bucket_share: float,       # default 1
    transfer_step_pct: float,      # default 1.0
    max_iterations: int,           # default 50
    revenue_metric: str,           # "revenue" | "revenue_per_unit"
    concentration_penalty: float,  # 0.0 – 0.3
    lock_top_n: int,               # don't reduce top-N buckets
) -> dict:
    """
    Iterative 1%-step transfer rule-based engine.
    Returns baseline, recommended allocations, and diagnostics.
    """
    # Work on last quarter only
    last_q = df_store["quarter"].max()
    df_q = df_store[df_store["quarter"] == last_q].copy()

    if df_q.empty:
        return {"error": "No data for selected store/quarter"}

    # Build bucket label
    df_q["bucket"] = df_q["collection"] + " › " + df_q["category"] + " [" + df_q["pricepoint"] + "]"

    # Aggregate to bucket level (in case of duplicates)
    agg = df_q.groupby("bucket").agg(
        stock_share_pct=("stock_share_pct", "sum"),
        revenue=("revenue", "sum"),
        units_sold=("units_sold", "sum"),
        units_allocated=("units_allocated", "sum"),
        discount_depth=("discount_depth", "mean"),
        weighted_mrp=("weighted_mrp", "mean"),
    ).reset_index()

    # Correct aggregations: compute from totals, not mean of pre-computed values
    agg["revenue_per_unit"] = (
        agg["revenue"] / agg["units_sold"].replace(0, 1)
    ).round(0).astype(int)
    agg["sell_through_pct"] = (
        agg["units_sold"] / agg["units_allocated"].replace(0, 1) * 100
    ).round(1)

    # Normalise shares to sum exactly to 100
    agg["stock_share_pct"] = agg["stock_share_pct"] / agg["stock_share_pct"].sum() * 100
    agg["stock_share_pct"] = agg["stock_share_pct"].round(1)

    baseline_revenue = agg["revenue"].sum()
    target_revenue   = baseline_revenue * (1 + uplift_target_pct / 100)

    # Score metric for ranking
    agg["score"] = agg[revenue_metric]

    # Rank buckets
    agg_sorted = agg.sort_values("score", ascending=False).reset_index(drop=True)
    top_buckets = set(agg_sorted.head(lock_top_n)["bucket"].tolist()) if lock_top_n > 0 else set()

    # Copy shares for mutation
    shares = {row["bucket"]: row["stock_share_pct"] for _, row in agg.iterrows()}
    scores  = {row["bucket"]: row["score"] for _, row in agg.iterrows()}

    iterations_done = 0
    transfer_log    = []
    hhi_history     = []
    rev_history     = [baseline_revenue]

    def compute_projected_revenue(shares_dict):
        total = 0
        for _, row in agg.iterrows():
            b = row["bucket"]
            share_ratio = shares_dict[b] / row["stock_share_pct"] if row["stock_share_pct"] > 0 else 1
            total += row["revenue"] * share_ratio
        return total

    def compute_hhi(shares_dict):
        vals = list(shares_dict.values())
        total = sum(vals)
        return sum((v / total * 100) ** 2 for v in vals)

    for i in range(max_iterations):
        # Sort by score ascending (donor = worst)
        sorted_by_score = sorted(shares.keys(), key=lambda b: scores[b])

        # Find donor: lowest score, not locked, above min share
        donor = None
        for b in sorted_by_score:
            if b not in top_buckets and shares[b] - transfer_step_pct >= min_bucket_share:
                donor = b
                break

        # Find recipient: highest score, below max share
        sorted_by_score_desc = sorted(shares.keys(), key=lambda b: scores[b], reverse=True)
        recipient = None
        for b in sorted_by_score_desc:
            if shares[b] + transfer_step_pct <= max_bucket_share and b != donor:
                recipient = b
                break

        if donor is None or recipient is None:
            break

        shares[donor]    -= transfer_step_pct
        shares[recipient] += transfer_step_pct

        # Apply concentration penalty to scores
        hhi = compute_hhi(shares)
        hhi_history.append(hhi)
        proj_rev = compute_projected_revenue(shares)
        penalised_rev = proj_rev * (1 - concentration_penalty * (hhi / 10000))
        rev_history.append(proj_rev)

        transfer_log.append({
            "step": i + 1,
            "from": donor,
            "to": recipient,
            "projected_revenue": round(proj_rev, 0),
            "hhi": round(hhi, 1),
        })

        iterations_done += 1
        if penalised_rev >= target_revenue:
            break

    # Build output table
    final_proj_rev = compute_projected_revenue(shares)
    result_rows = []
    for _, row in agg.iterrows():
        b = row["bucket"]
        baseline_sh = row["stock_share_pct"]
        rec_sh      = round(shares[b], 1)
        delta       = round(rec_sh - baseline_sh, 1)
        proj_rev_b  = round(row["revenue"] * (rec_sh / baseline_sh) if baseline_sh > 0 else row["revenue"], 0)
        result_rows.append({
            "Bucket":              b,
            "Baseline Share (%)":  baseline_sh,
            "Recommended Share (%)": rec_sh,
            "Δ Share (%)":         delta,
            "Baseline Revenue (₹)": int(row["revenue"]),
            "Projected Revenue (₹)": int(proj_rev_b),
            "Revenue/Unit (₹)":    int(row["revenue_per_unit"]),
            "Sell-through (%)":    row["sell_through_pct"],
            "Discount Depth (%)":  row["discount_depth"],
            "Weighted MRP (₹)":    int(row["weighted_mrp"]),
            "Action":              "↑ Increase" if delta > 0 else ("↓ Reduce" if delta < 0 else "→ Hold"),
        })

    return {
        "baseline_revenue":     baseline_revenue,
        "projected_revenue":    final_proj_rev,
        "target_revenue":       target_revenue,
        "uplift_achieved_pct":  round((final_proj_rev / baseline_revenue - 1) * 100, 2),
        "iterations":           iterations_done,
        "transfer_log":         transfer_log,
        "rev_history":          rev_history,
        "hhi_final":            round(compute_hhi(shares), 1),
        "result_df":            pd.DataFrame(result_rows),
        "quarter":              last_q,
    }


# ─────────────────────────────────────────────
# EXCEL EXPORT
# ─────────────────────────────────────────────
def build_excel(result: dict, store_id: str, rules: dict) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        wb  = writer.book

        # ── Formats ──
        hdr_fmt = wb.add_format({"bold": True, "bg_color": "#0f172a", "font_color": "#f8fafc",
                                  "border": 1, "font_name": "Calibri", "font_size": 10})
        up_fmt  = wb.add_format({"bg_color": "#dcfce7", "font_color": "#166534", "border": 1,
                                  "font_name": "Calibri", "font_size": 10})
        dn_fmt  = wb.add_format({"bg_color": "#fee2e2", "font_color": "#991b1b", "border": 1,
                                  "font_name": "Calibri", "font_size": 10})
        nu_fmt  = wb.add_format({"bg_color": "#f1f5f9", "border": 1,
                                  "font_name": "Calibri", "font_size": 10})
        num_fmt = wb.add_format({"num_format": "₹#,##0", "border": 1,
                                  "font_name": "Calibri", "font_size": 10})
        pct_fmt = wb.add_format({"num_format": "0.0\"%\"", "border": 1,
                                  "font_name": "Calibri", "font_size": 10})
        title_fmt = wb.add_format({"bold": True, "font_size": 14,
                                    "font_color": "#0f172a", "font_name": "Calibri"})
        meta_fmt  = wb.add_format({"font_size": 10, "font_color": "#64748b", "font_name": "Calibri"})

        # ── Sheet 1: Allocation Plan ──
        df_out = result["result_df"]
        df_out.to_excel(writer, sheet_name="Allocation Plan", startrow=5, index=False)
        ws1 = writer.sheets["Allocation Plan"]

        ws1.write("A1", f"ARROW BRAND — Stock Reallocation Plan", title_fmt)
        ws1.write("A2", f"Store: {store_id}   |   Quarter: {result['quarter']}", meta_fmt)
        ws1.write("A3",
            f"Baseline Revenue: ₹{result['baseline_revenue']:,.0f}   |   "
            f"Projected Revenue: ₹{result['projected_revenue']:,.0f}   |   "
            f"Uplift: +{result['uplift_achieved_pct']}%", meta_fmt)
        ws1.write("A4", f"Rules Applied: max_share={rules['max_share']}%  |  "
                        f"min_share={rules['min_share']}%  |  step={rules['step']}%  |  "
                        f"concentration_penalty={rules['conc_penalty']}", meta_fmt)

        # Header row color
        for col_num, col_name in enumerate(df_out.columns):
            ws1.write(5, col_num, col_name, hdr_fmt)

        # Data rows with conditional formatting
        for row_num, row in df_out.iterrows():
            delta = row["Δ Share (%)"]
            for col_num, col_name in enumerate(df_out.columns):
                val = row[col_name]
                if col_name == "Action":
                    fmt = up_fmt if "Increase" in str(val) else (dn_fmt if "Reduce" in str(val) else nu_fmt)
                    ws1.write(row_num + 6, col_num, val, fmt)
                elif "Revenue" in col_name and "₹" in col_name:
                    ws1.write(row_num + 6, col_num, val, num_fmt)
                elif "%" in col_name:
                    ws1.write(row_num + 6, col_num, val, pct_fmt)
                else:
                    ws1.write(row_num + 6, col_num, val, nu_fmt)

        ws1.set_column("A:A", 42)
        ws1.set_column("B:K", 18)

        # ── Sheet 2: Transfer Log ──
        if result["transfer_log"]:
            df_log = pd.DataFrame(result["transfer_log"])
            df_log.to_excel(writer, sheet_name="Transfer Log", startrow=1, index=False)
            ws2 = writer.sheets["Transfer Log"]
            ws2.write("A1", "Step-by-step stock transfer log", title_fmt)
            ws2.set_column("A:A", 8)
            ws2.set_column("B:C", 45)
            ws2.set_column("D:E", 20)

        # ── Sheet 3: Rules Config ──
        ws3 = wb.add_worksheet("Rules Config")
        ws3.write("A1", "Parameter", hdr_fmt)
        ws3.write("B1", "Value", hdr_fmt)
        for i, (k, v) in enumerate(rules.items()):
            ws3.write(i + 1, 0, k, nu_fmt)
            ws3.write(i + 1, 1, str(v), nu_fmt)
        ws3.set_column("A:B", 30)

    return output.getvalue()


# ═══════════════════════════════════════════════
# MAIN APP
# ═══════════════════════════════════════════════

# Header
st.markdown("""
<div class="main-header">
    <div class="arrow-badge">🏹 Arrow Brand · Arvind Fashions</div>
    <h1>Store Revenue Optimizer</h1>
    <p>Rule-Based Stock Reallocation Advisor · Phase 1 Benchmark Engine</p>
</div>
""", unsafe_allow_html=True)

# Load data
df = generate_data(seed=42)

# ─────────────────────────────────────────────
# SIDEBAR — Controls
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏪 Store Selection")
    store_list = sorted(df["store_id"].unique().tolist())
    store_id = st.selectbox("Select Store", store_list, index=0)

    store_meta = df[df["store_id"] == store_id][["region", "city", "store_tier", "total_stock"]].iloc[0]
    st.markdown(f"""
    <div style="background:#1e293b; border-radius:8px; padding:0.75rem 1rem; margin:0.5rem 0; font-size:0.8rem; color:#94a3b8;">
    🌍 <b style="color:#f8fafc">{store_meta['city']}</b> · {store_meta['region']}<br>
    🏷️ Tier: <b style="color:#f8fafc">{store_meta['store_tier']}</b><br>
    📦 Total Stock: <b style="color:#f59e0b">{store_meta['total_stock']:,} units</b>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("## 🎯 Uplift Target")
    uplift_pct = st.slider(
        "Target Revenue Uplift (%)",
        min_value=1, max_value=30, value=10, step=1,
        help="How much % revenue increase do you want over last quarter?"
    )

    st.markdown("---")
    st.markdown("## ⚙️ Rule Parameters")
    st.caption("Slide to adjust how the engine reallocates stock")

    max_bucket_share = st.slider(
        "Max bucket share cap (%)",
        min_value=20, max_value=45, value=45, step=1,
        help="No single bucket can exceed this % of total stock. BRD constraint: ≤45%"
    )
    min_bucket_share = st.slider(
        "Min bucket share floor (%)",
        min_value=1, max_value=10, value=1, step=1,
        help="No bucket can fall below this %. Prevents a category from going to zero."
    )
    transfer_step = st.slider(
        "Transfer step size (%)",
        min_value=1, max_value=5, value=1, step=1,
        help="Each iteration shifts this many % points. Smaller = finer grained, more iterations."
    )
    max_iters = st.slider(
        "Max iterations",
        min_value=10, max_value=200, value=50, step=10,
        help="Upper limit on transfer steps. Stops earlier if target is hit."
    )
    conc_penalty = st.slider(
        "Concentration penalty",
        min_value=0.0, max_value=0.30, value=0.05, step=0.01,
        help="Penalises over-concentrating stock in one bucket. Higher = more diversified output."
    )
    lock_top_n = st.slider(
        "Lock top-N buckets (no reduction)",
        min_value=0, max_value=5, value=2, step=1,
        help="Protect the top N performing buckets from being reduced."
    )

    st.markdown("---")
    st.markdown("## 📊 Scoring Metric")
    revenue_metric = st.radio(
        "Rank buckets by",
        ["revenue", "revenue_per_unit"],
        index=0,
        help="'revenue' = maximise total revenue contribution. 'revenue_per_unit' = maximise efficiency per unit stocked."
    )

    st.markdown("---")
    run_btn = st.button("▶ Run Optimizer", type="primary", use_container_width=True)

# ─────────────────────────────────────────────
# RUN ENGINE
# ─────────────────────────────────────────────
rules_config = {
    "max_share": max_bucket_share,
    "min_share": min_bucket_share,
    "step": transfer_step,
    "max_iters": max_iters,
    "conc_penalty": conc_penalty,
    "lock_top_n": lock_top_n,
    "revenue_metric": revenue_metric,
    "uplift_target_pct": uplift_pct,
}

df_store = df[df["store_id"] == store_id].copy()
result = run_rule_based_engine(
    df_store=df_store,
    uplift_target_pct=uplift_pct,
    max_bucket_share=max_bucket_share,
    min_bucket_share=min_bucket_share,
    transfer_step_pct=float(transfer_step),
    max_iterations=max_iters,
    revenue_metric=revenue_metric,
    concentration_penalty=conc_penalty,
    lock_top_n=lock_top_n,
)

# ─────────────────────────────────────────────
# KPI CARDS
# ─────────────────────────────────────────────
if "error" not in result:
    uplift_achieved = result["uplift_achieved_pct"]
    target_hit      = uplift_achieved >= uplift_pct * 0.95  # within 5%

    st.markdown(f"""
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Baseline Revenue</div>
        <div class="kpi-value">₹{result['baseline_revenue']/1e5:.1f}L</div>
        <div class="kpi-delta neutral">{result['quarter']}</div>
      </div>
      <div class="kpi-card green">
        <div class="kpi-label">Projected Revenue</div>
        <div class="kpi-value">₹{result['projected_revenue']/1e5:.1f}L</div>
        <div class="kpi-delta up">▲ +{uplift_achieved:.1f}% uplift</div>
      </div>
      <div class="kpi-card blue">
        <div class="kpi-label">Iterations Used</div>
        <div class="kpi-value">{result['iterations']}</div>
        <div class="kpi-delta neutral">of {max_iters} max</div>
      </div>
      <div class="kpi-card {'green' if target_hit else 'red'}">
        <div class="kpi-label">Target Status</div>
        <div class="kpi-value">{'✓ HIT' if target_hit else '✗ MISS'}</div>
        <div class="kpi-delta {'up' if target_hit else 'down'}">
          {'Target achieved' if target_hit else f'Need +{uplift_pct}%, got +{uplift_achieved:.1f}%'}
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not target_hit:
        st.markdown(f"""
        <div class="callout callout-warn">
        ⚠️ Target of <b>+{uplift_pct}%</b> not fully achieved with current rules.
        Try: increase Max Iterations, reduce the Min bucket floor, or lower the Concentration Penalty.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="callout callout-success">
        ✅ Revenue uplift target of <b>+{uplift_pct}%</b> achieved in <b>{result['iterations']} steps</b>.
        HHI concentration index: <b>{result['hhi_final']}</b>
        (lower = more diversified allocation).
        </div>
        """, unsafe_allow_html=True)

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Allocation Plan", "📈 Charts", "🔄 Transfer Log", "🧠 How It Works"
    ])

    # ── TAB 1: Allocation Table ──
    with tab1:
        st.markdown('<div class="section-title">Bucket-level stock reallocation</div>', unsafe_allow_html=True)

        df_res = result["result_df"].copy()

        # Color-code the dataframe
        def color_delta(val):
            if isinstance(val, str):
                if "Increase" in val: return "background-color:#dcfce7; color:#166534"
                if "Reduce"   in val: return "background-color:#fee2e2; color:#991b1b"
                return "background-color:#f1f5f9; color:#475569"
            if isinstance(val, (int, float)):
                if val > 0: return "color:#166534; font-weight:600"
                if val < 0: return "color:#991b1b; font-weight:600"
            return ""

        styled = df_res.style\
            .applymap(color_delta, subset=["Δ Share (%)", "Action"])\
            .format({
                "Baseline Share (%)":    "{:.1f}",
                "Recommended Share (%)": "{:.1f}",
                "Δ Share (%)":           "{:+.1f}",
                "Baseline Revenue (₹)":  "₹{:,.0f}",
                "Projected Revenue (₹)": "₹{:,.0f}",
                "Revenue/Unit (₹)":      "₹{:,.0f}",
                "Sell-through (%)":      "{:.1f}",
                "Discount Depth (%)":    "{:.1f}",
                "Weighted MRP (₹)":      "₹{:,.0f}",
            })

        st.dataframe(styled, use_container_width=True, height=420)

        # Summary stats
        n_up   = (df_res["Δ Share (%)"] > 0).sum()
        n_down = (df_res["Δ Share (%)"] < 0).sum()
        n_hold = (df_res["Δ Share (%)"] == 0).sum()
        st.caption(f"↑ {n_up} buckets increased  ·  ↓ {n_down} buckets reduced  ·  → {n_hold} held unchanged")

    # ── TAB 2: Charts ──
    with tab2:
        import streamlit as st

        col1, col2 = st.columns(2)

        with col1:
            st.markdown('<div class="section-title">Baseline vs Recommended stock share (%)</div>', unsafe_allow_html=True)
            chart_df = df_res[["Bucket", "Baseline Share (%)", "Recommended Share (%)"]]\
                       .sort_values("Recommended Share (%)", ascending=False).head(12)
            chart_df_plot = chart_df.set_index("Bucket")
            st.bar_chart(chart_df_plot, height=320)

        with col2:
            st.markdown('<div class="section-title">Revenue projection by bucket (₹)</div>', unsafe_allow_html=True)
            rev_df = df_res[["Bucket", "Baseline Revenue (₹)", "Projected Revenue (₹)"]]\
                     .sort_values("Projected Revenue (₹)", ascending=False).head(12)
            rev_df_plot = rev_df.set_index("Bucket")
            st.bar_chart(rev_df_plot, height=320)

        st.markdown('<div class="section-title">Revenue convergence over iterations</div>', unsafe_allow_html=True)
        rev_hist_df = pd.DataFrame({
            "Projected Revenue (₹)": result["rev_history"],
            "Target Revenue (₹)":    [result["target_revenue"]] * len(result["rev_history"]),
        })
        st.line_chart(rev_hist_df, height=220)
        st.caption("Each step = one 1%-transfer between buckets. Flat line = target achieved or constraints hit.")

        # Sell-through vs Share bubble
        st.markdown('<div class="section-title">Sell-through vs discount depth (by bucket)</div>', unsafe_allow_html=True)
        scatter_df = df_res[["Bucket", "Sell-through (%)", "Discount Depth (%)", "Recommended Share (%)"]].copy()
        scatter_df = scatter_df.rename(columns={
            "Sell-through (%)":    "Sell_through",
            "Discount Depth (%)":  "Discount_depth",
            "Recommended Share (%)": "Rec_share",
        })
        st.scatter_chart(scatter_df, x="Discount_depth", y="Sell_through",
                         size="Rec_share", color="Rec_share", height=280)
        st.caption("Ideal buckets: top-left (high sell-through, low discount). Size = recommended stock share.")

    # ── TAB 3: Transfer Log ──
    with tab3:
        st.markdown('<div class="section-title">Step-by-step transfer decisions</div>', unsafe_allow_html=True)

        if result["transfer_log"]:
            log_df = pd.DataFrame(result["transfer_log"])
            log_df["Revenue Δ (₹)"] = log_df["projected_revenue"].diff().fillna(0).astype(int)

            st.dataframe(
                log_df.rename(columns={
                    "step": "Step", "from": "Stock Reduced From",
                    "to": "Stock Added To", "projected_revenue": "Projected Revenue (₹)",
                    "hhi": "HHI Concentration"
                }).style.format({
                    "Projected Revenue (₹)": "₹{:,.0f}",
                    "Revenue Δ (₹)": "{:+,.0f}",
                    "HHI Concentration": "{:.0f}"
                }),
                use_container_width=True, height=360
            )
        else:
            st.info("No transfers were made. The target may have been 0% or constraints were too tight.")

    # ── TAB 4: How It Works ──
    with tab4:
        st.markdown('<div class="section-title">Algorithm explanation</div>', unsafe_allow_html=True)

        st.markdown(f"""
        <div class="explain-block">
<span class="highlight">ARROW BRAND RULE-BASED STOCK OPTIMIZER</span><br>
<span class="highlight">Store:</span> {store_id}  |  <span class="highlight">Quarter:</span> {result['quarter']}<br>
─────────────────────────────────────────────────────<br><br>

<span class="highlight">STEP 1 — Data prep</span><br>
  · Aggregate sales to (Collection × Category × Pricepoint) buckets<br>
  · Compute sell-through, revenue, revenue/unit per bucket for last quarter<br>
  · Normalise stock shares → sum to exactly 100%<br><br>

<span class="highlight">STEP 2 — Scoring</span><br>
  · Rank all buckets by: <span class="highlight">{revenue_metric}</span><br>
  · Lock top-{lock_top_n} buckets from reduction (protect best performers)<br><br>

<span class="highlight">STEP 3 — Iterative transfer loop</span><br>
  · Each iteration: transfer <span class="highlight">{transfer_step}%</span> stock from<br>
    LOWEST-ranked bucket → HIGHEST-ranked bucket<br>
  · Constraints enforced at every step:<br>
    <span class="green">  ✓</span> No bucket > <span class="highlight">{max_bucket_share}%</span> of total stock<br>
    <span class="green">  ✓</span> No bucket &lt; <span class="highlight">{min_bucket_share}%</span> of total stock<br>
    <span class="green">  ✓</span> Sum of all shares = 100% always<br>
    <span class="green">  ✓</span> Only whole-number % changes<br>
  · Concentration penalty λ = <span class="highlight">{conc_penalty}</span><br>
    (penalises piling into one bucket via HHI index)<br><br>

<span class="highlight">STEP 4 — Stopping conditions</span><br>
  <span class="green">  ✓</span> Target uplift of <span class="highlight">+{uplift_pct}%</span> achieved → STOP<br>
  · Max iterations ({max_iters}) reached → STOP<br>
  · No valid donor or recipient found → STOP<br><br>

<span class="highlight">RESULT</span><br>
  · Iterations used:  <span class="highlight">{result['iterations']}</span><br>
  · Baseline revenue: <span class="highlight">₹{result['baseline_revenue']:,.0f}</span><br>
  · Projected revenue: <span class="green">₹{result['projected_revenue']:,.0f}</span><br>
  · Uplift achieved:  <span class="{'green' if uplift_achieved >= uplift_pct * 0.95 else 'red'}">+{uplift_achieved:.2f}%</span>
  (target: +{uplift_pct}%)<br>
  · HHI concentration: <span class="highlight">{result['hhi_final']}</span><br>
  (10,000 = all stock in 1 bucket · 0 = perfectly equal)<br>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Next iteration: what comes after this</div>', unsafe_allow_html=True)
        st.markdown("""
        | Phase | What it adds | When to build |
        |---|---|---|
        | **Phase 2** | LightGBM model learns non-linear revenue curves | After 6+ quarters of data |
        | **Phase 3** | SHAP explanations per bucket | After Phase 2 model validated |
        | **Phase 4** | Discount depth optimizer | Once reallocation is live |
        | **Future** | Size mix within buckets | After category-level model stable |
        """)

    # ─────────────────────────────────────────────
    # DOWNLOAD SECTION
    # ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="section-title">Export</div>', unsafe_allow_html=True)

    col_dl1, col_dl2, col_dl3 = st.columns(3)

    # Excel download
    excel_bytes = build_excel(result, store_id, rules_config)
    with col_dl1:
        st.download_button(
            label="⬇ Download Excel Report",
            data=excel_bytes,
            file_name=f"Arrow_StoreOpt_{store_id}_{result['quarter']}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    # CSV download
    csv_bytes = result["result_df"].to_csv(index=False).encode()
    with col_dl2:
        st.download_button(
            label="⬇ Download CSV (Allocation)",
            data=csv_bytes,
            file_name=f"Arrow_Allocation_{store_id}_{result['quarter']}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # Transfer log CSV
    if result["transfer_log"]:
        log_csv = pd.DataFrame(result["transfer_log"]).to_csv(index=False).encode()
        with col_dl3:
            st.download_button(
                label="⬇ Download Transfer Log",
                data=log_csv,
                file_name=f"Arrow_TransferLog_{store_id}_{result['quarter']}.csv",
                mime="text/csv",
                use_container_width=True,
            )

else:
    st.error(f"Engine error: {result['error']}")

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style="text-align:center; font-size:0.72rem; color:#94a3b8; padding:1rem 0 0.5rem">
  Arrow Brand · Store Revenue Optimizer · Phase 1 — Rule-Based Benchmark<br>
  Arvind Fashions Limited · Internal Planning Tool · Not for external distribution
</div>
""", unsafe_allow_html=True)