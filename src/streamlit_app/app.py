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

import streamlit as st
import pandas as pd
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
        st.error("No recommendation files found. Run the solver first: python src/solver/run_solver.py --data dummy")
        st.stop()
    return pd.read_csv(files[0]), files[0].stem.replace("recommendations_", "")

@st.cache_data(ttl=0)
def load_store_capacity():
    return pd.read_csv(DATA_DIR / "raw" / "store_capacity.csv")

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
    st.error("No data files found. Run: PYTHONPATH=. python src/solver/run_solver.py --data dummy --store all")
    st.stop()


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
    ["🏪 Store Selector", "📊 Allocation Table", "🔧 What-If Simulation", "📤 Export & Activate"],
)

# ── Load data ─────────────────────────────────────────────────────────────────
recs_df, run_date = load_recommendations()
capacity_df       = load_store_capacity()
rates_df          = load_revenue_rates()

# Merge capacity for display
recs_df = recs_df.merge(
    capacity_df[["STORE_CODE", "STORE_NAME", "REGION", "MIN_OPTION_COUNT"]],
    left_on="store_id", right_on="STORE_CODE", how="left"
)

st.sidebar.markdown(f"**Solver run:** `{run_date}`")
st.sidebar.markdown(f"**Stores loaded:** `{recs_df['store_id'].nunique()}`")

st.sidebar.markdown("---")
st.sidebar.markdown("**Navigation guide**")
st.sidebar.markdown(
    "1. 🏪 **Store Selector** — choose region & store\n"
    "2. 📊 **Allocation Table** — view IP recommendations\n"
    "3. 🔧 **What-If Simulation** — pin a bucket & re-solve\n"
    "4. 📤 **Export & Activate** — download Monday plan\n\n"
    "*Select a store first before navigating to screens 2–4.*"
)


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
    Filter by region, choose a store, and navigate to the Allocation Table for IP recommendations.
  </div>
</div>
""", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        regions = ["All"] + sorted(recs_df["REGION"].dropna().unique().tolist())
        selected_region = st.selectbox("Region", regions)
    with col2:
        stores = recs_df["STORE_NAME"].dropna().unique().tolist()
        if selected_region != "All":
            stores = recs_df[recs_df["REGION"] == selected_region]["STORE_NAME"].dropna().unique().tolist()
        selected_store_name = st.selectbox("Store", ["All"] + sorted(stores))
    with col3:
        st.metric("Brand", "Arrow", help="Phase 1 covers Arrow brand only")

    # Summary table
    summary = (
        recs_df.groupby(["store_id", "STORE_NAME", "REGION", "MIN_OPTION_COUNT"])
        .agg(
            buckets=("bucket_key", "count"),
            top_bucket=("display_share_pct", "max"),
            total_rev_index=("expected_rev_index", "sum"),
        )
        .reset_index()
    )

    if selected_region != "All":
        summary = summary[summary["REGION"] == selected_region]
    if selected_store_name != "All":
        summary = summary[summary["STORE_NAME"] == selected_store_name]

    summary["Health"] = summary["buckets"].apply(
        lambda n: "🟢 GOOD" if n < 20 else ("🟡 MANAGEABLE" if n < 50 else "🔴 WARNING")
    )

    st.markdown(
        '<div style="font-size:0.75rem;color:#64748b;text-transform:uppercase;'
        'letter-spacing:0.8px;margin:1rem 0 0.4rem;">Arrow Stores Overview</div>',
        unsafe_allow_html=True,
    )
    st.dataframe(
        summary[["store_id", "STORE_NAME", "REGION", "MIN_OPTION_COUNT", "buckets", "top_bucket", "Health"]].rename(columns={
            "store_id": "Store Code", "STORE_NAME": "Store", "REGION": "Region",
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
    if selected_store_name != "All":
        store_id = recs_df[recs_df["STORE_NAME"] == selected_store_name]["store_id"].values[0]
        st.session_state["selected_store_id"]   = int(store_id)
        st.session_state["selected_store_name"] = selected_store_name
        st.markdown(f"""
<div style="background:#1e293b;border-radius:10px;padding:1rem 1.4rem;
            border:1px solid #334155;border-left:4px solid #34d399;margin-top:1rem;">
  <div style="font-size:0.75rem;color:#34d399;font-weight:700;letter-spacing:0.6px;
              text-transform:uppercase;">Store Selected</div>
  <div style="font-size:1rem;font-weight:700;color:#f8fafc;margin:0.3rem 0 0.15rem;">
    {selected_store_name}
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
