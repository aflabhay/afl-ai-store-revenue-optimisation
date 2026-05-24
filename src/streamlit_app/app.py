"""
app.py
------
Arvind Fashions Store Revenue Optimisation — Streamlit Internal Tool
Main entry point. Runs the multi-page app.

Screens:
    1. Store Selector   — filter by region / brand / store, see 4-week revenue
    2. Allocation Table — current vs recommended display_share with traffic lights
    3. What-If Panel    — planner pins a bucket, app re-solves remaining
    4. Export & Activate — Excel / PDF for store team and area manager

Run locally:
    streamlit run src/streamlit_app/app.py
"""

import json
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Store Revenue Optimisation | Arvind Fashions",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS theme ─────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.stApp {
    background: #0f172a;
    color: #e2e8f0;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #1e293b !important;
    border-right: 1px solid #334155;
}
[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
[data-testid="stSidebar"] .stRadio label {
    color: #cbd5e1 !important;
    font-size: 0.9rem;
}
[data-testid="stSidebar"] hr {
    border-color: #334155;
}

/* ── Page title / headers ── */
h1 {
    color: #f8fafc !important;
    font-weight: 700 !important;
    letter-spacing: -0.5px;
    border-left: 4px solid #f59e0b;
    padding-left: 0.75rem;
}
h2, h3, h4 {
    color: #e2e8f0 !important;
    font-weight: 600 !important;
}
h4 {
    border-bottom: 1px solid #334155;
    padding-bottom: 0.35rem;
    margin-top: 1.5rem !important;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: #1e293b;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    border: 1px solid #334155;
    border-top: 3px solid #f59e0b;
}
[data-testid="stMetricLabel"] {
    color: #94a3b8 !important;
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}
[data-testid="stMetricValue"] {
    color: #f8fafc !important;
    font-size: 1.6rem !important;
    font-weight: 700 !important;
}
[data-testid="stMetricDelta"] {
    color: #34d399 !important;
}

/* ── Dataframe / table ── */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #334155;
}
.stDataFrame iframe {
    border-radius: 10px;
}

/* ── Select / input widgets ── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stTextArea"] textarea,
[data-testid="stSlider"] {
    background: #1e293b !important;
    color: #e2e8f0 !important;
    border-color: #334155 !important;
}
[data-testid="stSelectbox"] label,
[data-testid="stTextArea"] label,
[data-testid="stSlider"] label {
    color: #94a3b8 !important;
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}

/* ── Buttons ── */
.stButton > button {
    background: #f59e0b !important;
    color: #0f172a !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.5rem 1.4rem !important;
    font-size: 0.9rem !important;
    transition: background 0.2s;
}
.stButton > button:hover {
    background: #d97706 !important;
}

/* ── Download button ── */
.stDownloadButton > button {
    background: #1e293b !important;
    color: #f59e0b !important;
    font-weight: 600 !important;
    border: 1px solid #f59e0b !important;
    border-radius: 8px !important;
}
.stDownloadButton > button:hover {
    background: #f59e0b !important;
    color: #0f172a !important;
}

/* ── Alert boxes ── */
[data-testid="stAlert"] {
    border-radius: 10px;
    border-left-width: 4px;
}
div[data-baseweb="notification"] {
    background: #1e293b !important;
    color: #e2e8f0 !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary {
    color: #e2e8f0 !important;
    font-weight: 600;
}

/* ── General text ── */
p, li, span, div {
    color: #e2e8f0;
}
code {
    background: #1e293b !important;
    color: #93c5fd !important;
    border-radius: 4px;
    padding: 2px 6px;
}
hr {
    border-color: #334155 !important;
}

/* ── Horizontal rule between sections ── */
.section-divider {
    border: none;
    border-top: 1px solid #334155;
    margin: 1.5rem 0;
}
</style>
""", unsafe_allow_html=True)

# ── Load processed outputs ───────────────────────────────────────────────────
DATA_DIR = Path(__file__).parents[2] / "data"

@st.cache_data(ttl=0)
def load_recommendations():
    processed = DATA_DIR / "processed"
    files = sorted(processed.glob("recommendations_*.csv"), reverse=True)
    if not files:
        st.error("No recommendation files found. Run the solver first: python src/solver/run_solver.py")
        st.stop()
    return pd.read_csv(files[0]), files[0].stem.replace("recommendations_", "")

@st.cache_data(ttl=0)
def load_store_capacity():
    real = DATA_DIR / "processed" / "store_capacity_real.csv"
    if not real.exists():
        st.error("Store capacity file not found. Run: python src/solver/run_solver.py")
        st.stop()
    return pd.read_csv(real)

@st.cache_data(ttl=0)
def load_revenue_rates():
    processed = DATA_DIR / "processed"
    files = sorted(processed.glob("revenue_rates_*.csv"), reverse=True)
    if files:
        return pd.read_csv(files[0])
    # Fallback to recommendations file which always exists
    rec_files = sorted(processed.glob("recommendations_*.csv"), reverse=True)
    if rec_files:
        recs = pd.read_csv(rec_files[0])
        return recs[["store_id", "bucket_key", "revenue_rate"]].drop_duplicates()
    st.error("No data files found. Run: PYTHONPATH=. python src/solver/run_solver.py --store all")
    st.stop()


# ── EDA chart theme constants ─────────────────────────────────────────────────
_CHART_LAYOUT = dict(
    paper_bgcolor="#1e293b",
    plot_bgcolor="#0f172a",
    font=dict(color="#e2e8f0", family="Inter, sans-serif", size=12),
    margin=dict(l=10, r=10, t=44, b=10),
)
# Use this separately in charts that need a visible legend to avoid kwarg conflicts
_LEGEND = dict(bgcolor="#1e293b", bordercolor="#334155", borderwidth=1)
_SIGNAL_COLORS = {
    "INCREASE": "#34d399",
    "HOLD":     "#f59e0b",
    "REDUCE":   "#f87171",
    "NO SOH":   "#64748b",
    "NO SALES": "#94a3b8",
}
_PRICEBAND_COLORS = {"Economy": "#93c5fd", "Mid": "#f59e0b", "Premium": "#34d399"}
_READINESS_COLORS = {
    "IDEAL":            "#34d399",
    "GOOD":             "#f59e0b",
    "LIMITED":          "#f97316",
    "COARSEN REQUIRED": "#f87171",
}


@st.cache_data(ttl=3600)
def load_priceband_config() -> tuple[dict, pd.DataFrame | None]:
    """
    Load priceband_config.json and latest mrp_distribution_*.csv from data/processed/.
    Returns (breaks_dict, mrp_df_or_None).
    """
    processed = DATA_DIR / "processed"
    config_path = processed / "priceband_config.json"
    breaks = None
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f)
        breaks = cfg.get("breaks", {})

    mrp_files = sorted(processed.glob("mrp_distribution_*.csv"), reverse=True)
    mrp_df = pd.read_csv(mrp_files[0]) if mrp_files else None
    return breaks, mrp_df


@st.cache_data(ttl=3600)
def load_eda_data() -> tuple:
    """Load EDA dataset from data/processed/eda_data_YYYY-MM-DD.csv.

    To regenerate from the Fabric warehouse run:
        python src/data_pipeline/fabric_connector.py
    """
    processed = DATA_DIR / "processed"
    files = sorted(processed.glob("eda_data_*.csv"), reverse=True)
    if not files:
        st.error(
            "No EDA data file found. Run: python src/data_pipeline/fabric_connector.py"
        )
        st.stop()
    return pd.read_csv(files[0]), files[0].name, "fabric"


# ── Sidebar navigation ───────────────────────────────────────────────────────
st.sidebar.markdown("""
<div style="padding:1rem 0 0.8rem;border-bottom:1px solid #334155;margin-bottom:0.5rem;">
  <div style="font-size:1.25rem;font-weight:800;color:#f59e0b;letter-spacing:2px;">
    ARROW
  </div>
  <div style="font-size:0.7rem;color:#64748b;letter-spacing:1px;text-transform:uppercase;">
    Arvind Fashions Limited
  </div>
  <div style="font-size:0.78rem;color:#94a3b8;margin-top:0.4rem;font-weight:600;">
    Store Revenue Optimisation
  </div>
</div>
""", unsafe_allow_html=True)

page = st.sidebar.radio(
    "Navigate",
    ["🏪 Store Selector", "📊 Allocation Table", "🔧 What-If Simulation", "📤 Export & Activate", "🔍 EDA Explorer"],
)

# ── Load data ─────────────────────────────────────────────────────────────────
recs_df, run_date = load_recommendations()
capacity_df       = load_store_capacity()
rates_df          = load_revenue_rates()

# Merge capacity for display — REGION is optional (may be absent in older capacity files)
_cap_cols = [c for c in ["STORE_CODE", "STORE_NAME", "MIN_OPTION_COUNT"] if c in capacity_df.columns]
recs_df = recs_df.merge(capacity_df[_cap_cols], left_on="store_id", right_on="STORE_CODE", how="left")
if "STORE_NAME" not in recs_df.columns:
    recs_df["STORE_NAME"] = recs_df["store_id"].astype(str)

st.sidebar.markdown(f"**Solver run:** `{run_date}`")
st.sidebar.markdown(f"**Stores loaded:** `{recs_df['store_id'].nunique()}`")

st.sidebar.markdown("---")
st.sidebar.markdown("**Navigation guide**")
st.sidebar.markdown(
    "1. 🏪 **Store Selector** — choose region & store\n"
    "2. 📊 **Allocation Table** — view IP recommendations\n"
    "3. 🔧 **What-If Simulation** — pin a bucket & re-solve\n"
    "4. 📤 **Export & Activate** — download Monday plan\n"
    "5. 🔍 **EDA Explorer** — fleet-wide data analysis\n\n"
    "*Select a store first before navigating to screens 2–4.*"
)

st.sidebar.markdown("---")
st.sidebar.markdown("**How the algorithm works**")
st.sidebar.markdown("""
Every Sunday night the solver reads the last **4 weeks of sales & SOH** data
and runs an **Integer Programming (IP)** model for each store.

**Step 1 — Revenue Rate**
Each bucket (Category × Price tier) gets a score:
`Revenue Rate = 4-week revenue ÷ avg weekly SOH`
Higher rate = more revenue generated per unit of stock held.

**Step 2 — Proportional Floor**
Every bucket is guaranteed a *minimum* share of floor space, proportional
to its revenue rate. No bucket is starved of space.

**Step 3 — IP Solver (PuLP / HiGHS)**
The remaining "free budget" is allocated by maximising total expected revenue
subject to:
- Each bucket stays within a min floor and a 45% cap
- All shares sum to exactly 100%

**Output**
A recommended `display_share_%` per bucket — translated into style slot counts
based on the store's display capacity.

*The planner can override any bucket via What-If Simulation before exporting.*
""")



# ────────────────────────────────────────────────────────────────────────────
# SCREEN 1 — STORE SELECTOR
# ────────────────────────────────────────────────────────────────────────────
if page == "🏪 Store Selector":
    st.markdown("""
<div style="background:linear-gradient(135deg,#1e293b,#0f172a);border-radius:14px;
            padding:1.5rem 2rem;margin-bottom:1.5rem;border-left:5px solid #f59e0b;">
  <div style="font-size:1.6rem;font-weight:800;color:#f8fafc;letter-spacing:-0.5px;">
    Store Selector
  </div>
  <div style="color:#94a3b8;margin-top:0.3rem;font-size:0.9rem;">
    Choose a store and navigate to the Allocation Table for IP recommendations.
  </div>
</div>
""", unsafe_allow_html=True)

    # Show currently selected store banner if navigating back
    if "selected_store_id" in st.session_state:
        sid   = st.session_state["selected_store_id"]
        snam  = st.session_state["selected_store_name"]
        slbl  = st.session_state.get("selected_store_label", f"{sid} - {snam}")
        st.markdown(
            f'<div style="background:#1e293b;border-radius:8px;padding:0.6rem 1rem;'
            f'border:1px solid #334155;border-left:4px solid #34d399;margin-bottom:1rem;'
            f'display:inline-flex;align-items:center;gap:0.8rem;">'
            f'<span style="font-size:0.72rem;color:#34d399;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:0.5px;">Active store</span>'
            f'<span style="color:#f8fafc;font-weight:600;">{slbl}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    col1, col2 = st.columns([2, 1])
    with col1:
        # Build "{store_id} - {store_name}" labels for easy search
        store_pairs = (
            recs_df[["store_id", "STORE_NAME"]]
            .drop_duplicates()
            .sort_values("store_id")
        )
        store_labels = [
            f"{int(r.store_id)} - {r.STORE_NAME}" if pd.notna(r.STORE_NAME) else str(int(r.store_id))
            for r in store_pairs.itertuples()
        ]
        store_options = ["All"] + store_labels

        # Pre-select previously chosen store when navigating back
        default_idx = 0
        if "selected_store_label" in st.session_state and st.session_state["selected_store_label"] in store_options:
            default_idx = store_options.index(st.session_state["selected_store_label"])
        selected_store_label = st.selectbox("Store", store_options, index=default_idx)

    with col2:
        st.metric("Brand", "Arrow", help="Phase 1 covers Arrow brand only")

    # Resolve selected store_id from label
    selected_store_id_filter = None
    if selected_store_label != "All":
        selected_store_id_filter = int(selected_store_label.split(" - ")[0])

    # Summary table
    summary = (
        recs_df.groupby(["store_id", "STORE_NAME", "MIN_OPTION_COUNT"])
        .agg(
            buckets=("bucket_key", "count"),
            top_bucket=("display_share_pct", "max"),
            total_rev_index=("expected_rev_index", "sum"),
        )
        .reset_index()
    )

    if selected_store_id_filter is not None:
        summary = summary[summary["store_id"] == selected_store_id_filter]

    summary["Health"] = summary["buckets"].apply(
        lambda n: "🟢 GOOD" if n < 20 else ("🟡 MANAGEABLE" if n < 50 else "🔴 WARNING")
    )

    st.markdown(
        '<div style="font-size:0.75rem;color:#64748b;text-transform:uppercase;'
        'letter-spacing:0.8px;margin:1rem 0 0.4rem;">Arrow Stores Overview</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(
        summary[["store_id", "STORE_NAME", "MIN_OPTION_COUNT", "buckets", "top_bucket", "Health"]].rename(columns={
            "store_id": "Store Code", "STORE_NAME": "Store",
            "MIN_OPTION_COUNT": "Display Capacity", "buckets": "Active Buckets",
            "top_bucket": "Max Recommended Share %", "Health": "Solver Health",
        }),
        use_container_width=True, hide_index=True,
    )

    with st.expander("What does Solver Health mean?"):
        st.markdown(
            """
The solver works by dividing 100% of display space across all active **buckets**
(a bucket = one Category + Price tier, e.g. *Formal Shirts | Premium*).

Each bucket must receive at least 1% of display space (the minimum floor constraint).
So if a store has **100 active buckets**, the floor alone consumes 100 × 1% = 100% —
leaving **zero room** for the solver to differentiate between high and low performers.
The more buckets there are, the less freedom the solver has.

| Status | Active Buckets | What it means |
|--------|---------------|---------------|
| 🟢 **GOOD** | < 20 | Solver has full freedom — recommendations are meaningfully differentiated |
| 🟡 **MANAGEABLE** | 20 – 49 | Solver works but differentiation narrows — monitor outputs |
| 🔴 **WARNING** | 50+ | Too many buckets — floor constraint leaves little room to optimise; consider collapsing Price tiers |

**For Arrow stores**, the expected bucket count is **8–12** (4–5 categories × 2–3 price tiers),
so all stores should be 🟢 GOOD.
            """
        )

    # Store selection for downstream screens
    if selected_store_label != "All" and selected_store_id_filter is not None:
        match = recs_df[recs_df["store_id"] == selected_store_id_filter]
        if not match.empty:
            st.session_state["selected_store_id"]    = selected_store_id_filter
            st.session_state["selected_store_name"]  = match["STORE_NAME"].values[0]
            st.session_state["selected_store_label"] = selected_store_label
        st.markdown(f"""
<div style="background:#1e293b;border-radius:10px;padding:1rem 1.4rem;
            border:1px solid #334155;border-left:4px solid #34d399;margin-top:1rem;">
  <div style="font-size:0.75rem;color:#34d399;font-weight:700;letter-spacing:0.6px;
              text-transform:uppercase;">Store Selected</div>
  <div style="font-size:1rem;font-weight:700;color:#f8fafc;margin:0.3rem 0 0.15rem;">
    {selected_store_label}
  </div>
  <div style="font-size:0.82rem;color:#94a3b8;">
    Navigate to <b style="color:#f59e0b;">Allocation Table</b> in the sidebar to view IP recommendations.
  </div>
</div>
""", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# SCREEN 2 — ALLOCATION TABLE
# ────────────────────────────────────────────────────────────────────────────
elif page == "📊 Allocation Table":
    st.markdown("""
<div style="background:linear-gradient(135deg,#1e293b,#0f172a);border-radius:14px;
            padding:1.5rem 2rem;margin-bottom:1.5rem;border-left:5px solid #f59e0b;">
  <div style="font-size:1.6rem;font-weight:800;color:#f8fafc;letter-spacing:-0.5px;">
    Allocation Table
  </div>
  <div style="color:#94a3b8;margin-top:0.3rem;font-size:0.9rem;">
    IP-optimised display share per bucket — floor guaranteed + solver-allocated extra.
  </div>
</div>
""", unsafe_allow_html=True)

    if "selected_store_id" not in st.session_state:
        st.info("Select a store from the Store Selector first.")
        st.stop()

    store_id   = st.session_state["selected_store_id"]
    store_name = st.session_state["selected_store_name"]
    st.markdown(
        f'<div style="display:inline-flex;align-items:center;gap:0.7rem;margin-bottom:1rem;">'
        f'<span style="background:#f59e0b;color:#0f172a;font-weight:700;font-size:0.8rem;'
        f'padding:3px 10px;border-radius:20px;letter-spacing:0.5px;">STORE {store_id}</span>'
        f'<span style="color:#f8fafc;font-size:1.1rem;font-weight:600;">{store_name}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    store_recs = recs_df[recs_df["store_id"] == store_id].copy()
    cap        = capacity_df[capacity_df["STORE_CODE"] == store_id]["MIN_OPTION_COUNT"].values[0]

    store_recs["signal_icon"] = store_recs["signal"].map(
        {"INCREASE": "🟢", "HOLD": "🟡", "REDUCE": "🔴"}
    ).fillna("⚪")
    store_recs["Style Slots"] = (store_recs["display_share_pct"] / 100 * cap).round().astype(int)

    has_floor = "floor_share" in store_recs.columns
    if has_floor:
        store_recs["extra_share"] = (
            store_recs["display_share_pct"] - store_recs["floor_share"]
        ).clip(lower=0)
        floor_total        = int(store_recs["floor_share"].sum())
        free_budget        = 100 - floor_total
        buckets_with_extra = int((store_recs["extra_share"] > 0).sum())
        top_extra_bucket   = store_recs.loc[
            store_recs["extra_share"].idxmax(), "bucket_key"
        ]
        top_extra_pct      = int(store_recs["extra_share"].max())

    # ── KPI strip ────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Buckets", len(store_recs))
    c2.metric("Display Capacity", f"{cap} styles")
    if has_floor:
        c3.metric(
            "Floor Budget",
            f"{floor_total}%",
            help="Sum of all proportional floors — guaranteed minimum for every bucket",
        )
        c4.metric(
            "Free Budget (Solver)",
            f"{free_budget}%",
            help="Remaining display share the IP solver allocates to maximise revenue",
        )
    else:
        c3.metric("Total Share", f"{store_recs['display_share_pct'].sum()}%")

    # ── Full detail table ────────────────────────────────────────────────
    st.markdown("#### Full allocation detail")
    cols_to_show = [
        "signal_icon", "bucket_key", "floor_share", "display_share_pct",
        "revenue_rate", "Style Slots", "expected_rev_index",
    ]
    col_rename = {
        "signal_icon":        "",
        "bucket_key":         "Bucket",
        "floor_share":        "Floor %",
        "display_share_pct":  "Recommended %",
        "revenue_rate":       "Revenue Rate (₹/unit)",
        "expected_rev_index": "Rev Index",
    }
    if not has_floor:
        cols_to_show = [c for c in cols_to_show if c != "floor_share"]
        col_rename.pop("floor_share", None)

    st.dataframe(
        store_recs[cols_to_show].rename(columns=col_rename),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown(
        f"**Style slots used:** {store_recs['Style Slots'].sum()} / {cap} &nbsp;|&nbsp; "
        f"**Total share:** {store_recs['display_share_pct'].sum()}%",
        unsafe_allow_html=True,
    )

    if has_floor:
        # ── Stacked bar visual per bucket ─────────────────────────────────
        st.markdown("---")

        sorted_recs = store_recs.sort_values("display_share_pct", ascending=False)
        bar_scale   = 380  # px representing 45%

        bar_html = """
<style>
.alloc-wrap{background:#1e293b;border-radius:10px;padding:1.2rem 1.5rem;margin-bottom:0.5rem;}
.alloc-title{font-size:1rem;font-weight:700;color:#f8fafc;margin-bottom:0.25rem;}
.alloc-sub{font-size:0.75rem;color:#94a3b8;margin-bottom:1rem;}
.alloc-row{display:flex;align-items:center;margin:7px 0;font-size:0.82rem;}
.alloc-name{width:235px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
            color:#e2e8f0;font-weight:500;}
.alloc-bars{display:flex;height:20px;border-radius:5px;overflow:hidden;
            background:#334155;width:380px;}
.bar-floor{background:#64748b;height:100%;}
.bar-extra{background:#f59e0b;height:100%;}
.alloc-label{margin-left:10px;color:#f8fafc;font-weight:700;min-width:38px;}
.alloc-detail{margin-left:6px;color:#94a3b8;font-size:0.73rem;}
.alloc-legend{display:flex;gap:20px;font-size:0.75rem;color:#94a3b8;
              margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid #334155;}
.leg-box{display:inline-block;width:13px;height:13px;border-radius:3px;
         vertical-align:middle;margin-right:5px;}
</style>
<div class="alloc-wrap">
  <div class="alloc-title">Display allocation breakdown — Floor vs Solver</div>
  <div class="alloc-sub">Bar width relative to 45% cap. Total = floor + solver extra.</div>
  <div class="alloc-legend">
    <span><span class="leg-box" style="background:#64748b;"></span>Proportional floor (Step 1 — guaranteed)</span>
    <span><span class="leg-box" style="background:#f59e0b;"></span>Solver optimised extra (Step 2)</span>
  </div>
"""
        for _, row in sorted_recs.iterrows():
            floor_px = round(row["floor_share"] / 45 * bar_scale)
            extra_px = round(row["extra_share"] / 45 * bar_scale)
            total    = int(row["display_share_pct"])
            floor_v  = int(row["floor_share"])
            extra_v  = int(row["extra_share"])
            icon     = row["signal_icon"]
            detail   = (
                f"{floor_v}% floor + {extra_v}% solver = {total}%"
                if extra_v > 0
                else f"{floor_v}% floor only"
            )
            bar_html += f"""
<div class="alloc-row">
  <div class="alloc-name">{icon} {row['bucket_key']}</div>
  <div class="alloc-bars">
    <div class="bar-floor" style="width:{floor_px}px;"></div>
    <div class="bar-extra" style="width:{extra_px}px;"></div>
  </div>
  <div class="alloc-label">{total}%</div>
  <div class="alloc-detail">{detail}</div>
</div>"""

        bar_html += "</div>"   # close .alloc-wrap
        st.markdown(bar_html, unsafe_allow_html=True)

        # ── How-it-works explanation ──────────────────────────────────────
        st.markdown("---")
        st.markdown(
            f"""
<div style="background:#0f172a;border-radius:10px;padding:1.4rem 1.6rem;
            font-size:0.85rem;line-height:2.1;color:#e2e8f0;">

<div style="font-size:1rem;font-weight:700;color:#f8fafc;margin-bottom:1rem;
            padding-bottom:0.6rem;border-bottom:1px solid #1e293b;">
  How the 100% display space was allocated
</div>

<span style="color:#f59e0b;font-weight:700;font-size:0.95rem;">
  Step 1 — Proportional Floor &nbsp;({floor_total}% of display)
</span><br>
Each bucket receives a <b style="color:#fff;">guaranteed minimum</b> proportional to its
share of total revenue rate across all buckets.<br>
<code style="background:#1e293b;color:#94a3b8;padding:2px 8px;border-radius:4px;font-size:0.78rem;">
floor[bucket] = max(1%, round( rate[bucket] / total_rate &times; 100 &times; 0.50 ))
</code><br>
<span style="color:#94a3b8;font-size:0.8rem;">
<b style="color:#cbd5e1;">Why &times; 0.50?</b> &nbsp;
This is the <b style="color:#cbd5e1;">floor_weight</b> — it controls what fraction of each
bucket's proportional fair share is locked in as a guaranteed minimum.
At 0.50, every bucket is guaranteed <i>at least half</i> of what a perfectly proportional
split would give it, leaving the other 50% of display space free for the solver to
optimise. Setting it to 1.0 would be fully proportional (no optimisation); 0.0 would
revert to a flat 1% floor for all buckets regardless of performance.
</span><br>
This ensures buckets with similar revenue rates all get meaningful display space —
not just the single top performer.

<br><br>

<span style="color:#f59e0b;font-weight:700;font-size:0.95rem;">
  Step 2 — Free Budget &nbsp;({free_budget}% of display) &nbsp;— IP Solver
</span><br>
The remaining <b style="color:#fff;">{free_budget}%</b> is handed to the
<b style="color:#fff;">Integer Programming solver</b> with one objective:<br>
<code style="background:#1e293b;color:#94a3b8;padding:2px 8px;border-radius:4px;font-size:0.78rem;">
Maximise &nbsp; SUM( display_share[b] &times; revenue_rate[b] ) &nbsp; for all buckets b
</code><br>
The solver allocated this free budget to the
<b style="color:#fff;">top {buckets_with_extra} bucket(s)</b> by revenue rate, up to the 45% cap.<br>
<span style="color:#94a3b8;">
Largest gain: &nbsp;<b style="color:#f59e0b;">{top_extra_bucket}</b>
&nbsp;received +{top_extra_pct}% above its floor.
</span>

<br><br>

<span style="color:#f59e0b;font-weight:700;font-size:0.95rem;">
  Step 3 — Final = Floor + Solver Extra
</span><br>
<span style="background:#1e293b;color:#cbd5e1;padding:2px 8px;border-radius:4px;">Recommended&nbsp;%</span>
&nbsp;=&nbsp;
<span style="background:#1e3a5f;color:#93c5fd;padding:2px 8px;border-radius:4px;">Proportional&nbsp;Floor</span>
&nbsp;+&nbsp;
<span style="background:#451a03;color:#fcd34d;padding:2px 8px;border-radius:4px;">Solver&nbsp;Extra</span>
<br>
Buckets that received <b style="color:#fff;">only their floor</b> show grey bars above —
the solver's free budget was fully consumed by higher-rate buckets.

</div>
""",
            unsafe_allow_html=True,
        )


# ────────────────────────────────────────────────────────────────────────────
# SCREEN 3 — WHAT-IF SIMULATION
# ────────────────────────────────────────────────────────────────────────────
elif page == "🔧 What-If Simulation":
    st.markdown("""
<div style="background:linear-gradient(135deg,#1e293b,#0f172a);border-radius:14px;
            padding:1.5rem 2rem;margin-bottom:1.5rem;border-left:5px solid #f59e0b;">
  <div style="font-size:1.6rem;font-weight:800;color:#f8fafc;letter-spacing:-0.5px;">
    What-If Simulation
  </div>
  <div style="color:#94a3b8;margin-top:0.3rem;font-size:0.9rem;">
    Pin a bucket to a fixed share — the solver re-optimises remaining buckets automatically.
  </div>
</div>
""", unsafe_allow_html=True)

    if "selected_store_id" not in st.session_state:
        st.info("Select a store from the Store Selector first.")
        st.stop()

    store_id   = st.session_state["selected_store_id"]
    store_name = st.session_state["selected_store_name"]
    st.markdown(
        f'<div style="display:inline-flex;align-items:center;gap:0.7rem;margin-bottom:1rem;">'
        f'<span style="background:#f59e0b;color:#0f172a;font-weight:700;font-size:0.8rem;'
        f'padding:3px 10px;border-radius:20px;letter-spacing:0.5px;">STORE {store_id}</span>'
        f'<span style="color:#f8fafc;font-size:1.1rem;font-weight:600;">{store_name}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    store_recs = recs_df[recs_df["store_id"] == store_id].copy()
    cap        = capacity_df[capacity_df["STORE_CODE"] == store_id]["MIN_OPTION_COUNT"].values[0]

    pinned_bucket = st.selectbox("Select bucket to pin", store_recs["bucket_key"].tolist())
    pinned_share  = st.slider("Pinned share (%)", 1, 45, int(store_recs[store_recs["bucket_key"] == pinned_bucket]["display_share_pct"].values[0]))

    override_reason = st.text_area("Override reason (required before saving)", placeholder="e.g. Festival season — Formal Shirts demand expected to spike in this region")

    if st.button("Re-run solver with pinned bucket"):
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))
        from src.solver.ip_model import solve_store, SolverConfig

        remaining = store_recs[store_recs["bucket_key"] != pinned_bucket].copy()
        remaining_budget = 100 - pinned_share

        if remaining_budget < len(remaining):
            st.error(f"Pinned share too high — only {remaining_budget}% left for {len(remaining)} other buckets (need at least 1% each).")
        else:
            # Temporarily adjust budget for remaining buckets
            config = SolverConfig(total_share=remaining_budget, min_share=1, max_share=45)
            result = solve_store(store_id, remaining[["bucket_key", "revenue_rate"]], cap, config)

            if result["status"] == "OPTIMAL":
                rows = [{"bucket_key": pinned_bucket, "display_share_pct": pinned_share, "PINNED": "📌"}]
                for b in result["buckets"]:
                    rows.append({"bucket_key": b["bucket_key"], "display_share_pct": b["display_share_pct"], "PINNED": ""})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.success(f"Total share: {sum(r['display_share_pct'] for r in rows)}%")

                if override_reason:
                    st.info(f"Override reason logged: *{override_reason}*")
                else:
                    st.warning("Please enter an override reason before saving.")
            else:
                st.error(f"Solver failed: {result['message']}")


# ────────────────────────────────────────────────────────────────────────────
# SCREEN 4 — EXPORT & ACTIVATE
# ────────────────────────────────────────────────────────────────────────────
elif page == "📤 Export & Activate":
    st.markdown("""
<div style="background:linear-gradient(135deg,#1e293b,#0f172a);border-radius:14px;
            padding:1.5rem 2rem;margin-bottom:1.5rem;border-left:5px solid #f59e0b;">
  <div style="font-size:1.6rem;font-weight:800;color:#f8fafc;letter-spacing:-0.5px;">
    Export & Activate
  </div>
  <div style="color:#94a3b8;margin-top:0.3rem;font-size:0.9rem;">
    Download the Monday rearrangement plan for the store team and area manager.
  </div>
</div>
""", unsafe_allow_html=True)

    if "selected_store_id" not in st.session_state:
        st.info("Select a store from the Store Selector first.")
        st.stop()

    store_id   = st.session_state["selected_store_id"]
    store_name = st.session_state["selected_store_name"]
    st.markdown(
        f'<div style="display:inline-flex;align-items:center;gap:0.7rem;margin-bottom:1rem;">'
        f'<span style="background:#f59e0b;color:#0f172a;font-weight:700;font-size:0.8rem;'
        f'padding:3px 10px;border-radius:20px;letter-spacing:0.5px;">STORE {store_id}</span>'
        f'<span style="color:#f8fafc;font-size:1.1rem;font-weight:600;">{store_name}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    store_recs = recs_df[recs_df["store_id"] == store_id].copy()
    cap        = capacity_df[capacity_df["STORE_CODE"] == store_id]["MIN_OPTION_COUNT"].values[0]
    store_recs["Style Slots"] = (store_recs["display_share_pct"] / 100 * cap).round().astype(int)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**📊 Store Team Excel**")
        csv = store_recs[["bucket_key", "display_share_pct", "Style Slots", "signal"]].to_csv(index=False)
        st.download_button(
            label="Download Allocation Excel (.csv)",
            data=csv,
            file_name=f"allocation_{store_id}_{run_date}.csv",
            mime="text/csv",
        )

    with col2:
        st.markdown("**📋 Size-Break Risk Flags**")
        st.info("Daily SOH monitoring job flags CORE styles with SOH ≤ 2 units for next-day warehouse replenishment. Check `src/utils/size_break_monitor.py` for the daily job.")

    st.markdown("---")
    slots_used  = store_recs['Style Slots'].sum()
    total_share = store_recs['display_share_pct'].sum()
    st.markdown(f"""
<div style="display:flex;gap:1.2rem;flex-wrap:wrap;margin-top:0.5rem;">
  <div style="background:#1e293b;border-radius:10px;padding:0.9rem 1.4rem;
              border:1px solid #334155;border-top:3px solid #f59e0b;min-width:160px;">
    <div style="font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.8px;">Activation Date</div>
    <div style="font-size:1.1rem;font-weight:700;color:#f8fafc;margin-top:0.3rem;">Next Monday</div>
  </div>
  <div style="background:#1e293b;border-radius:10px;padding:0.9rem 1.4rem;
              border:1px solid #334155;border-top:3px solid #34d399;min-width:160px;">
    <div style="font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.8px;">Style Slots</div>
    <div style="font-size:1.1rem;font-weight:700;color:#f8fafc;margin-top:0.3rem;">{slots_used} / {cap}</div>
  </div>
  <div style="background:#1e293b;border-radius:10px;padding:0.9rem 1.4rem;
              border:1px solid #334155;border-top:3px solid #818cf8;min-width:160px;">
    <div style="font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.8px;">Total Display Share</div>
    <div style="font-size:1.1rem;font-weight:700;color:#f8fafc;margin-top:0.3rem;">{total_share}%</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# SCREEN 5 — EDA EXPLORER
# ────────────────────────────────────────────────────────────────────────────
elif page == "🔍 EDA Explorer":
    st.markdown("""
<div style="background:linear-gradient(135deg,#1e293b,#0f172a);border-radius:14px;
            padding:1.5rem 2rem;margin-bottom:1.5rem;border-left:5px solid #f59e0b;">
  <div style="font-size:1.6rem;font-weight:800;color:#f8fafc;letter-spacing:-0.5px;">
    EDA Explorer
  </div>
  <div style="color:#94a3b8;margin-top:0.3rem;font-size:0.9rem;">
    Fleet-wide exploratory analysis — revenue rates, sell-through, signals, and data quality.
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Load data ─────────────────────────────────────────────────────────
    eda_df, file_label, eda_source = load_eda_data()

    ctrl_col, status_col = st.columns([1, 5])
    with ctrl_col:
        if st.button("Clear cache", help="Reload from disk on next run"):
            load_eda_data.clear()
            st.rerun()
    with status_col:
        colour = "#34d399" if eda_source == "fabric" else "#f59e0b"
        st.markdown(
            f'<div style="font-size:0.72rem;color:#64748b;padding-top:0.6rem;">'
            f'Loaded: <code style="background:#1e293b;color:{colour};padding:2px 8px;'
            f'border-radius:4px;">{file_label}</code> &nbsp;·&nbsp; '
            f'To refresh: <code style="background:#1e293b;color:#93c5fd;padding:2px 6px;'
            f'border-radius:4px;">python src/data_pipeline/fabric_connector.py</code>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Filters ──────────────────────────────────────────────────────────
    fc1, fc2 = st.columns(2)
    with fc1:
        all_cats = ["All"] + sorted(eda_df["category"].dropna().unique().tolist())
        cat_f = st.selectbox("Category", all_cats, key="eda_cat")
    with fc2:
        price_f = st.selectbox("Priceband", ["All", "Economy", "Mid", "Premium"], key="eda_price")

    filt = eda_df.copy()
    if cat_f != "All":
        filt = filt[filt["category"] == cat_f]
    if price_f != "All":
        filt = filt[filt["priceband"] == price_f]

    if filt.empty:
        st.warning("No data matches the selected filters.")
        st.stop()

    # ── KPI strip ─────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Stores", int(filt["store_id"].nunique()))
    k2.metric("Buckets", len(filt))
    total_rev = filt["bucket_revenue_4w"].sum()
    k3.metric(
        "Fleet 4W Revenue",
        f"₹{total_rev/1e7:.2f} Cr" if total_rev >= 1e7 else f"₹{total_rev/1e5:.1f} L",
    )
    avg_rate = filt["revenue_rate"].dropna().mean()
    k4.metric("Avg Revenue Rate", f"₹{avg_rate:,.0f}" if avg_rate == avg_rate else "–")
    pct_inc = (filt["signal_preview"] == "INCREASE").sum() / max(len(filt), 1) * 100
    k5.metric("INCREASE signals", f"{pct_inc:.1f}%")

    st.markdown("---")

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📡 Fleet Overview",
        "📈 Revenue Rate",
        "🔄 Sell-Through & Discounts",
        "📦 SOH Analysis",
        "🗂️ Data Quality",
        "💰 Price Bands",
    ])

    # ══════════════════════════════════════════════════════════════════════
    # TAB 1 — FLEET OVERVIEW
    # ══════════════════════════════════════════════════════════════════════
    with tab1:
        t1c1, t1c2 = st.columns(2)

        # Signal distribution donut
        with t1c1:
            sig_counts = filt["signal_preview"].value_counts().reset_index()
            sig_counts.columns = ["signal", "count"]
            fig_sig = go.Figure(go.Pie(
                labels=sig_counts["signal"],
                values=sig_counts["count"],
                hole=0.55,
                marker_colors=[_SIGNAL_COLORS.get(s, "#94a3b8") for s in sig_counts["signal"]],
                textinfo="label+percent",
                textfont=dict(size=12, color="#e2e8f0"),
            ))
            fig_sig.update_layout(
                title=dict(text="Signal Preview Distribution", font=dict(size=14, color="#f8fafc")),
                showlegend=False,
                height=320,
                **_CHART_LAYOUT,
            )
            st.plotly_chart(fig_sig, use_container_width=True)

        # Solver readiness bar (per store)
        with t1c2:
            read_order  = ["IDEAL", "GOOD", "LIMITED", "COARSEN REQUIRED"]
            read_counts = (
                filt.groupby("store_id")["solver_readiness"].first().value_counts()
            )
            read_df = pd.DataFrame({
                "Readiness": [r for r in read_order if r in read_counts.index],
                "Stores":    [int(read_counts[r]) for r in read_order if r in read_counts.index],
            })
            fig_read = px.bar(
                read_df, x="Readiness", y="Stores",
                color="Readiness",
                color_discrete_map=_READINESS_COLORS,
                text="Stores",
            )
            fig_read.update_traces(textposition="outside", textfont_color="#f8fafc")
            fig_read.update_layout(
                title=dict(text="Solver Readiness by Store", font=dict(size=14, color="#f8fafc")),
                showlegend=False,
                height=320,
                xaxis=dict(title="", gridcolor="#334155"),
                yaxis=dict(title="Stores", gridcolor="#334155"),
                **_CHART_LAYOUT,
            )
            st.plotly_chart(fig_read, use_container_width=True)

        # Signal mix stacked bar by category
        st.markdown("#### Signal Mix by Category")
        cat_sig = (
            filt.groupby(["category", "signal_preview"])
            .size()
            .reset_index(name="count")
        )
        if not cat_sig.empty:
            fig_cs = px.bar(
                cat_sig, x="category", y="count", color="signal_preview",
                color_discrete_map=_SIGNAL_COLORS,
                barmode="stack",
                labels={"category": "Category", "count": "Buckets", "signal_preview": "Signal"},
            )
            fig_cs.update_layout(
                height=300,
                xaxis=dict(title="", gridcolor="#334155"),
                yaxis=dict(title="Buckets", gridcolor="#334155"),
                **_CHART_LAYOUT,
            )
            fig_cs.update_layout(legend={**_LEGEND, "title": "Signal"})
            st.plotly_chart(fig_cs, use_container_width=True)

        # Store-level summary table
        st.markdown("#### Store-Level Summary")
        store_sum = (
            filt.groupby(["store_id", "store_name"])
            .agg(
                Buckets           = ("bucket_key",        "count"),
                Revenue_4W        = ("bucket_revenue_4w", "sum"),
                Avg_Revenue_Rate  = ("revenue_rate",      "mean"),
                INCREASE_count    = ("signal_preview",    lambda x: (x == "INCREASE").sum()),
                Solver_Readiness  = ("solver_readiness",  "first"),
            )
            .reset_index()
        )
        store_sum["Revenue_4W"]       = store_sum["Revenue_4W"].map(lambda v: f"₹{v:,.0f}")
        store_sum["Avg_Revenue_Rate"] = store_sum["Avg_Revenue_Rate"].map(
            lambda v: f"₹{v:,.0f}" if v == v else "–"
        )
        st.dataframe(
            store_sum.rename(columns={
                "store_id":         "Store ID",
                "store_name":       "Store",
                "Buckets":          "Buckets",
                "Revenue_4W":       "4W Revenue",
                "Avg_Revenue_Rate": "Avg Rate",
                "INCREASE_count":   "INCREASE",
                "Solver_Readiness": "Readiness",
            }),
            use_container_width=True,
            hide_index=True,
        )

    # ══════════════════════════════════════════════════════════════════════
    # TAB 2 — REVENUE RATE
    # ══════════════════════════════════════════════════════════════════════
    with tab2:
        rate_data = filt[filt["revenue_rate"].notna() & (filt["revenue_rate"] > 0)].copy()

        if rate_data.empty:
            st.info("No revenue rate data for the current filter selection.")
        else:
            # Histogram — fleet-wide distribution
            fig_hist = px.histogram(
                rate_data, x="revenue_rate", nbins=30,
                color_discrete_sequence=["#f59e0b"],
                labels={"revenue_rate": "Revenue Rate (₹/unit)"},
            )
            fig_hist.update_layout(
                title=dict(text="Revenue Rate Distribution — all buckets", font=dict(size=14, color="#f8fafc")),
                height=280,
                xaxis=dict(title="Revenue Rate (₹/unit)", gridcolor="#334155"),
                yaxis=dict(title="Bucket Count", gridcolor="#334155"),
                bargap=0.05,
                **_CHART_LAYOUT,
            )
            st.plotly_chart(fig_hist, use_container_width=True)

            # Box plots: by Category and by Priceband side-by-side
            bc1, bc2 = st.columns(2)
            with bc1:
                fig_box_cat = px.box(
                    rate_data, x="category", y="revenue_rate",
                    color="category",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    labels={"revenue_rate": "Revenue Rate (₹/unit)", "category": ""},
                )
                fig_box_cat.update_layout(
                    title=dict(text="Revenue Rate by Category", font=dict(size=13, color="#f8fafc")),
                    showlegend=False,
                    height=360,
                    xaxis=dict(title="", tickangle=-30, gridcolor="#334155"),
                    yaxis=dict(title="Revenue Rate", gridcolor="#334155"),
                    **_CHART_LAYOUT,
                )
                st.plotly_chart(fig_box_cat, use_container_width=True)

            with bc2:
                pb_order   = ["Economy", "Mid", "Premium"]
                pb_present = [p for p in pb_order if p in rate_data["priceband"].values]
                fig_box_pb = px.box(
                    rate_data, x="priceband", y="revenue_rate",
                    color="priceband",
                    category_orders={"priceband": pb_present},
                    color_discrete_map=_PRICEBAND_COLORS,
                    labels={"revenue_rate": "Revenue Rate (₹/unit)", "priceband": ""},
                )
                fig_box_pb.update_layout(
                    title=dict(text="Revenue Rate by Priceband", font=dict(size=13, color="#f8fafc")),
                    showlegend=False,
                    height=360,
                    xaxis=dict(title="", gridcolor="#334155"),
                    yaxis=dict(title="", gridcolor="#334155"),
                    **_CHART_LAYOUT,
                )
                st.plotly_chart(fig_box_pb, use_container_width=True)

            # Top 10 / Bottom 10 buckets
            top_n = 10
            tt1, tt2 = st.columns(2)
            _rate_cols = ["store_name", "bucket_key", "revenue_rate", "signal_preview"]
            _rate_rename = {
                "store_name":     "Store",
                "bucket_key":     "Bucket",
                "revenue_rate":   "Rate (₹/unit)",
                "signal_preview": "Signal",
            }
            with tt1:
                st.markdown(f"**Top {top_n} buckets by Revenue Rate**")
                top10 = (
                    rate_data.nlargest(top_n, "revenue_rate")[_rate_cols]
                    .rename(columns=_rate_rename)
                )
                top10["Rate (₹/unit)"] = top10["Rate (₹/unit)"].map(lambda v: f"₹{v:,.0f}")
                st.dataframe(top10, use_container_width=True, hide_index=True)
            with tt2:
                st.markdown(f"**Bottom {top_n} buckets by Revenue Rate**")
                bot10 = (
                    rate_data.nsmallest(top_n, "revenue_rate")[_rate_cols]
                    .rename(columns=_rate_rename)
                )
                bot10["Rate (₹/unit)"] = bot10["Rate (₹/unit)"].map(lambda v: f"₹{v:,.0f}")
                st.dataframe(bot10, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════
    # TAB 3 — SELL-THROUGH & DISCOUNTS
    # ══════════════════════════════════════════════════════════════════════
    with tab3:
        sc1, sc2 = st.columns(2)

        # Scatter: revenue_rate vs sell_through_pct
        with sc1:
            scatter_data = filt[
                filt["sell_through_pct"].notna() & filt["revenue_rate"].notna()
            ]
            if not scatter_data.empty:
                fig_scatter = px.scatter(
                    scatter_data,
                    x="sell_through_pct",
                    y="revenue_rate",
                    color="signal_preview",
                    color_discrete_map=_SIGNAL_COLORS,
                    hover_data={
                        "store_name":      True,
                        "bucket_key":      True,
                        "sell_through_pct":":.1f",
                        "revenue_rate":    ":,.0f",
                    },
                    labels={
                        "sell_through_pct": "Sell-Through %",
                        "revenue_rate":     "Revenue Rate (₹/unit)",
                        "signal_preview":   "Signal",
                    },
                )
                fig_scatter.update_layout(
                    title=dict(text="Revenue Rate vs Sell-Through %", font=dict(size=13, color="#f8fafc")),
                    height=360,
                    xaxis=dict(title="Sell-Through %", gridcolor="#334155"),
                    yaxis=dict(title="Revenue Rate (₹/unit)", gridcolor="#334155"),
                    **_CHART_LAYOUT,
                )
                st.plotly_chart(fig_scatter, use_container_width=True)
            else:
                st.info("Sell-through data not available.")

        # Sell-through distribution
        with sc2:
            st_data = filt[filt["sell_through_pct"].notna()]
            if not st_data.empty:
                fig_sth = px.histogram(
                    st_data, x="sell_through_pct", nbins=20,
                    color_discrete_sequence=["#34d399"],
                    labels={"sell_through_pct": "Sell-Through %"},
                )
                fig_sth.update_layout(
                    title=dict(text="Sell-Through % Distribution", font=dict(size=13, color="#f8fafc")),
                    height=360,
                    xaxis=dict(title="Sell-Through %", gridcolor="#334155"),
                    yaxis=dict(title="Bucket Count",    gridcolor="#334155"),
                    bargap=0.05,
                    **_CHART_LAYOUT,
                )
                st.plotly_chart(fig_sth, use_container_width=True)

        # Discount analysis
        disc_data = filt[filt["discount_pct"].notna()]
        if not disc_data.empty:
            dc1, dc2 = st.columns(2)
            with dc1:
                fig_disc = px.histogram(
                    disc_data, x="discount_pct", nbins=20,
                    color_discrete_sequence=["#f87171"],
                    labels={"discount_pct": "Discount %"},
                )
                fig_disc.update_layout(
                    title=dict(text="Discount % Distribution", font=dict(size=13, color="#f8fafc")),
                    height=280,
                    xaxis=dict(title="Discount %",   gridcolor="#334155"),
                    yaxis=dict(title="Bucket Count", gridcolor="#334155"),
                    bargap=0.05,
                    **_CHART_LAYOUT,
                )
                st.plotly_chart(fig_disc, use_container_width=True)

            with dc2:
                fig_disc_cat = px.box(
                    disc_data, x="category", y="discount_pct",
                    color="category",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    labels={"discount_pct": "Discount %", "category": ""},
                )
                fig_disc_cat.update_layout(
                    title=dict(text="Discount % by Category", font=dict(size=13, color="#f8fafc")),
                    showlegend=False,
                    height=280,
                    xaxis=dict(title="", tickangle=-30, gridcolor="#334155"),
                    yaxis=dict(title="Discount %", gridcolor="#334155"),
                    **_CHART_LAYOUT,
                )
                st.plotly_chart(fig_disc_cat, use_container_width=True)

        # Deadstock risk table: high SOH + low sell-through
        st.markdown("#### Deadstock Risk — High SOH, Low Sell-Through")
        soh_median = filt["avg_weekly_soh"].median()
        dead_risk  = filt[
            filt["sell_through_pct"].notna() &
            filt["avg_weekly_soh"].notna()   &
            (filt["sell_through_pct"] < 20)  &
            (filt["avg_weekly_soh"]   > soh_median)
        ].sort_values("sell_through_pct")[[
            "store_name", "bucket_key", "sell_through_pct",
            "avg_weekly_soh", "discount_pct", "revenue_rate", "signal_preview",
        ]].rename(columns={
            "store_name":      "Store",
            "bucket_key":      "Bucket",
            "sell_through_pct":"STR %",
            "avg_weekly_soh":  "Avg Weekly SOH",
            "discount_pct":    "Disc %",
            "revenue_rate":    "Rate (₹/unit)",
            "signal_preview":  "Signal",
        })
        if dead_risk.empty:
            st.success("No deadstock risk buckets detected.")
        else:
            dead_risk["Avg Weekly SOH"] = dead_risk["Avg Weekly SOH"].map(lambda v: f"{v:,.0f}")
            dead_risk["Rate (₹/unit)"]  = dead_risk["Rate (₹/unit)"].map(
                lambda v: f"₹{v:,.0f}" if v == v else "–"
            )
            st.dataframe(dead_risk, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════
    # TAB 4 — SOH ANALYSIS
    # ══════════════════════════════════════════════════════════════════════
    with tab4:
        soh_data = filt[filt["avg_weekly_soh"].notna() & (filt["avg_weekly_soh"] > 0)].copy()

        if soh_data.empty:
            st.info("No SOH data available for the current filter selection.")
        else:
            # KPI strip
            sk1, sk2, sk3, sk4 = st.columns(4)
            sk1.metric("Buckets with SOH", len(soh_data))
            sk2.metric("Total SOH Units", f"{soh_data['total_soh_units'].sum():,.0f}")
            sk3.metric("Avg Weekly SOH / Bucket", f"{soh_data['avg_weekly_soh'].mean():,.0f}")
            zero_soh = (filt["avg_weekly_soh"].fillna(0) == 0).sum()
            sk4.metric("Buckets with Zero SOH", int(zero_soh))

            st.markdown("---")
            sc1, sc2 = st.columns(2)

            # SOH distribution histogram
            with sc1:
                fig_soh_hist = px.histogram(
                    soh_data, x="avg_weekly_soh", nbins=30,
                    color_discrete_sequence=["#93c5fd"],
                    labels={"avg_weekly_soh": "Avg Weekly SOH (units)"},
                )
                fig_soh_hist.update_layout(
                    title=dict(text="Avg Weekly SOH Distribution", font=dict(size=13, color="#f8fafc")),
                    height=300,
                    xaxis=dict(title="Avg Weekly SOH", gridcolor="#334155"),
                    yaxis=dict(title="Bucket Count",   gridcolor="#334155"),
                    bargap=0.05,
                    **_CHART_LAYOUT,
                )
                st.plotly_chart(fig_soh_hist, use_container_width=True)

            # SOH by category box
            with sc2:
                fig_soh_cat = px.box(
                    soh_data, x="category", y="avg_weekly_soh",
                    color="category",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    labels={"avg_weekly_soh": "Avg Weekly SOH", "category": ""},
                )
                fig_soh_cat.update_layout(
                    title=dict(text="SOH by Category", font=dict(size=13, color="#f8fafc")),
                    showlegend=False,
                    height=300,
                    xaxis=dict(title="", tickangle=-30, gridcolor="#334155"),
                    yaxis=dict(title="Avg Weekly SOH",  gridcolor="#334155"),
                    **_CHART_LAYOUT,
                )
                st.plotly_chart(fig_soh_cat, use_container_width=True)

            sc3, sc4 = st.columns(2)

            # SOH by priceband
            with sc3:
                pb_order = ["Economy", "Mid", "Premium"]
                fig_soh_pb = px.box(
                    soh_data, x="priceband", y="avg_weekly_soh",
                    color="priceband",
                    category_orders={"priceband": pb_order},
                    color_discrete_map=_PRICEBAND_COLORS,
                    labels={"avg_weekly_soh": "Avg Weekly SOH", "priceband": ""},
                )
                fig_soh_pb.update_layout(
                    title=dict(text="SOH by Priceband", font=dict(size=13, color="#f8fafc")),
                    showlegend=False,
                    height=300,
                    xaxis=dict(title="", gridcolor="#334155"),
                    yaxis=dict(title="Avg Weekly SOH", gridcolor="#334155"),
                    **_CHART_LAYOUT,
                )
                st.plotly_chart(fig_soh_pb, use_container_width=True)

            # SOH vs Revenue Rate scatter
            with sc4:
                scatter_soh = soh_data[soh_data["revenue_rate"].notna()]
                if not scatter_soh.empty:
                    fig_soh_rate = px.scatter(
                        scatter_soh,
                        x="avg_weekly_soh", y="revenue_rate",
                        color="signal_preview",
                        color_discrete_map=_SIGNAL_COLORS,
                        hover_data={"store_name": True, "bucket_key": True},
                        labels={
                            "avg_weekly_soh": "Avg Weekly SOH",
                            "revenue_rate":   "Revenue Rate (₹/unit)",
                            "signal_preview": "Signal",
                        },
                    )
                    fig_soh_rate.update_layout(
                        title=dict(text="SOH vs Revenue Rate", font=dict(size=13, color="#f8fafc")),
                        height=300,
                        xaxis=dict(title="Avg Weekly SOH", gridcolor="#334155"),
                        yaxis=dict(title="Revenue Rate",   gridcolor="#334155"),
                        **_CHART_LAYOUT,
                    )
                    fig_soh_rate.update_layout(legend={**_LEGEND, "title": "Signal"})
                    st.plotly_chart(fig_soh_rate, use_container_width=True)

            # Store-level SOH summary
            st.markdown("#### SOH by Store")
            store_soh = (
                soh_data.groupby(["store_id", "store_name"])
                .agg(
                    Buckets         = ("bucket_key",       "count"),
                    Total_SOH       = ("total_soh_units",  "sum"),
                    Avg_Weekly_SOH  = ("avg_weekly_soh",   "sum"),   # sum across buckets = store total
                    Avg_Rate        = ("revenue_rate",     "mean"),
                )
                .reset_index()
                .sort_values("Total_SOH", ascending=False)
            )
            store_soh["Total_SOH"]      = store_soh["Total_SOH"].map(lambda v: f"{v:,.0f}")
            store_soh["Avg_Weekly_SOH"] = store_soh["Avg_Weekly_SOH"].map(lambda v: f"{v:,.0f}")
            store_soh["Avg_Rate"]       = store_soh["Avg_Rate"].map(
                lambda v: f"₹{v:,.0f}" if v == v else "–"
            )
            st.dataframe(
                store_soh.rename(columns={
                    "store_id":       "Store ID",
                    "store_name":     "Store",
                    "Buckets":        "Buckets",
                    "Total_SOH":      "Total SOH Units",
                    "Avg_Weekly_SOH": "Weekly SOH (store total)",
                    "Avg_Rate":       "Avg Revenue Rate",
                }),
                use_container_width=True, hide_index=True,
            )

    # ══════════════════════════════════════════════════════════════════════
    # TAB 5 — DATA QUALITY
    # ══════════════════════════════════════════════════════════════════════
    with tab5:
        dq1, dq2 = st.columns(2)

        with dq1:
            dq_counts = filt["data_quality_flag"].value_counts().reset_index()
            dq_counts.columns = ["flag", "count"]
            _dq_colors = {
                "OK":                          "#34d399",
                "THIN — use category fallback":"#f59e0b",
                "NO SALES DATA":               "#f87171",
            }
            fig_dq = px.bar(
                dq_counts, x="flag", y="count",
                color="flag",
                color_discrete_map=_dq_colors,
                text="count",
                labels={"flag": "", "count": "Buckets"},
            )
            fig_dq.update_traces(textposition="outside", textfont_color="#f8fafc")
            fig_dq.update_layout(
                title=dict(text="Data Quality Flags", font=dict(size=13, color="#f8fafc")),
                showlegend=False,
                height=320,
                xaxis=dict(gridcolor="#334155", tickangle=-15),
                yaxis=dict(title="Buckets", gridcolor="#334155"),
                **_CHART_LAYOUT,
            )
            st.plotly_chart(fig_dq, use_container_width=True)

        with dq2:
            days_data = filt[filt["days_with_sales"].notna()]
            if not days_data.empty:
                fig_days = px.histogram(
                    days_data, x="days_with_sales", nbins=15,
                    color_discrete_sequence=["#93c5fd"],
                    labels={"days_with_sales": "Days with Sales (last 4 weeks)"},
                )
                fig_days.add_vline(
                    x=14, line_dash="dash", line_color="#f59e0b",
                    annotation_text="14-day threshold",
                    annotation_font_color="#f59e0b",
                    annotation_position="top right",
                )
                fig_days.update_layout(
                    title=dict(text="Days with Sales Distribution", font=dict(size=13, color="#f8fafc")),
                    height=320,
                    xaxis=dict(title="Days with Sales", gridcolor="#334155"),
                    yaxis=dict(title="Bucket Count",    gridcolor="#334155"),
                    bargap=0.05,
                    **_CHART_LAYOUT,
                )
                st.plotly_chart(fig_days, use_container_width=True)

        # Thin / no-data bucket table
        st.markdown("#### Buckets with Data Quality Issues")
        thin_data = filt[filt["data_quality_flag"] != "OK"].sort_values("data_quality_flag")[[
            "store_name", "bucket_key", "days_with_sales", "data_quality_flag", "revenue_rate",
        ]].rename(columns={
            "store_name":        "Store",
            "bucket_key":        "Bucket",
            "days_with_sales":   "Days w/ Sales",
            "data_quality_flag": "Quality Flag",
            "revenue_rate":      "Rate (₹/unit)",
        })

        if thin_data.empty:
            st.success("All buckets have sufficient data (≥ 14 days with sales).")
        else:
            thin_data["Rate (₹/unit)"] = thin_data["Rate (₹/unit)"].map(
                lambda v: f"₹{v:,.0f}" if v == v else "seeded from category avg"
            )
            st.dataframe(thin_data, use_container_width=True, hide_index=True)
            st.caption(
                f"{len(thin_data)} bucket(s) have thin data. "
                "The solver seeds their revenue_rate from the category average across comparable stores."
            )

    # ══════════════════════════════════════════════════════════════════════
    # TAB 6 — PRICE BAND ANALYSIS
    # ══════════════════════════════════════════════════════════════════════
    with tab6:
        pb_breaks, mrp_df = load_priceband_config()

        if pb_breaks is None:
            st.info(
                "No priceband config found. Run `python src/data_pipeline/fabric_connector.py` "
                "to generate data-driven breaks. Showing uniform break analysis below."
            )

        # ── Section 1: Current priceband performance ──────────────────────
        st.markdown("#### Current Priceband Performance")
        st.caption("Revenue and rate distribution across pricebands using the breaks applied at last data fetch.")

        pb1, pb2 = st.columns(2)

        # Stacked bar: revenue contribution by priceband per category
        with pb1:
            rev_pb = (
                filt[filt["bucket_revenue_4w"].notna()]
                .groupby(["category", "priceband"])["bucket_revenue_4w"]
                .sum()
                .reset_index()
            )
            if not rev_pb.empty:
                fig_rev_pb = px.bar(
                    rev_pb, x="category", y="bucket_revenue_4w",
                    color="priceband",
                    color_discrete_map=_PRICEBAND_COLORS,
                    barmode="stack",
                    labels={"bucket_revenue_4w": "4W Revenue (₹)", "category": "", "priceband": "Priceband"},
                )
                fig_rev_pb.update_layout(
                    title=dict(text="Revenue by Category × Priceband", font=dict(size=13, color="#f8fafc")),
                    height=350,
                    xaxis=dict(title="", tickangle=-30, gridcolor="#334155"),
                    yaxis=dict(title="4W Revenue (₹)", gridcolor="#334155"),
                    **_CHART_LAYOUT,
                )
                fig_rev_pb.update_layout(legend={**_LEGEND, "title": "Priceband"})
                st.plotly_chart(fig_rev_pb, use_container_width=True)

        # Revenue rate box by priceband per category
        with pb2:
            rate_pb = filt[filt["revenue_rate"].notna() & (filt["revenue_rate"] > 0)]
            if not rate_pb.empty:
                fig_rate_pb = px.box(
                    rate_pb, x="category", y="revenue_rate",
                    color="priceband",
                    color_discrete_map=_PRICEBAND_COLORS,
                    labels={"revenue_rate": "Revenue Rate (₹/unit)", "category": ""},
                )
                fig_rate_pb.update_layout(
                    title=dict(text="Revenue Rate by Category × Priceband", font=dict(size=13, color="#f8fafc")),
                    height=350,
                    xaxis=dict(title="", tickangle=-30, gridcolor="#334155"),
                    yaxis=dict(title="Revenue Rate (₹/unit)", gridcolor="#334155"),
                    **_CHART_LAYOUT,
                )
                fig_rate_pb.update_layout(legend={**_LEGEND, "title": "Priceband"})
                st.plotly_chart(fig_rate_pb, use_container_width=True)

        # Summary table: bucket count, revenue share, avg rate per category × priceband
        pb_summary = (
            filt.groupby(["category", "priceband"])
            .agg(
                Buckets    = ("bucket_key",        "count"),
                Revenue_4W = ("bucket_revenue_4w", "sum"),
                Avg_Rate   = ("revenue_rate",       "mean"),
                Avg_SOH    = ("avg_weekly_soh",     "mean"),
            )
            .reset_index()
            .sort_values(["category", "priceband"])
        )
        total_rev = pb_summary["Revenue_4W"].sum()
        pb_summary["Rev_Share_%"] = (pb_summary["Revenue_4W"] / total_rev * 100).round(1)
        pb_summary["Revenue_4W"]  = pb_summary["Revenue_4W"].map(lambda v: f"₹{v:,.0f}")
        pb_summary["Avg_Rate"]    = pb_summary["Avg_Rate"].map(lambda v: f"₹{v:,.0f}" if v == v else "–")
        pb_summary["Avg_SOH"]     = pb_summary["Avg_SOH"].map(lambda v: f"{v:,.0f}" if v == v else "–")
        st.dataframe(
            pb_summary.rename(columns={
                "category":   "Category",
                "priceband":  "Priceband",
                "Buckets":    "Buckets",
                "Revenue_4W": "4W Revenue",
                "Rev_Share_%":"Rev Share %",
                "Avg_Rate":   "Avg Rate (₹/unit)",
                "Avg_SOH":    "Avg Weekly SOH",
            }),
            use_container_width=True, hide_index=True,
        )

        # ── Section 2: Data-driven break analysis ─────────────────────────
        st.markdown("---")
        st.markdown("#### Data-Driven Priceband Breaks")

        if mrp_df is not None and not mrp_df.empty:
            st.caption(
                "MRP percentile distribution per category from the last 4 weeks of Arrow sales. "
                "Recommended breaks use p33 (Economy cap) and p67 (Mid cap) — tertile split, rounded to ₹500."
            )

            # MRP distribution chart: box-style using p10/p25/p50/p75/p90
            fig_mrp = go.Figure()
            pb_cols   = ["p10", "p25", "p33", "p50", "p67", "p75", "p90"]
            available = [c for c in pb_cols if c in mrp_df.columns]
            for _, row in mrp_df.iterrows():
                if not all(c in row for c in ["p25", "p50", "p75"]):
                    continue
                fig_mrp.add_trace(go.Box(
                    name=row["category"],
                    q1=[row["p25"]], median=[row["p50"]], q3=[row["p75"]],
                    lowerfence=[row.get("p10", row["p25"])],
                    upperfence=[row.get("p90", row["p75"])],
                    boxpoints=False,
                ))
            fig_mrp.update_layout(
                title=dict(text="MRP Distribution per Category (p10–p90)", font=dict(size=13, color="#f8fafc")),
                height=380,
                xaxis=dict(title="Category", gridcolor="#334155"),
                yaxis=dict(title="MRP (₹)", gridcolor="#334155"),
                showlegend=False,
                **_CHART_LAYOUT,
            )
            st.plotly_chart(fig_mrp, use_container_width=True)

            # Recommended vs current breaks comparison table
            from src.data_pipeline.fabric_connector import compute_priceband_breaks
            rec_breaks = compute_priceband_breaks(mrp_df)

            _CURRENT_DEFAULT = {"economy_cap": 2000, "mid_cap": 3000}
            rows_comp = []
            for _, row in mrp_df.sort_values("style_count", ascending=False).iterrows():
                cat = row["category"]
                rec = rec_breaks.get(cat, rec_breaks["_default"])
                cur = (pb_breaks or {}).get(cat, _CURRENT_DEFAULT)
                rows_comp.append({
                    "Category":         cat,
                    "Styles (4W)":      int(row["style_count"]),
                    "MRP p50 (median)": f"₹{int(row['p50']):,}",
                    "Current Economy ≤":f"₹{cur['economy_cap']:,}",
                    "Current Mid ≤":    f"₹{cur['mid_cap']:,}",
                    "Rec Economy ≤":    f"₹{rec['economy_cap']:,}",
                    "Rec Mid ≤":        f"₹{rec['mid_cap']:,}",
                    "Changed?":         "✅" if cur != rec else "–",
                })
            st.dataframe(pd.DataFrame(rows_comp), use_container_width=True, hide_index=True)

            st.info(
                "To apply recommended breaks: re-run `python src/data_pipeline/fabric_connector.py` "
                "— it will save the new config and re-fetch EDA data with per-category pricebands."
            )
        else:
            st.warning(
                "MRP distribution file not found. "
                "Run `python src/data_pipeline/fabric_connector.py` to generate it."
            )

