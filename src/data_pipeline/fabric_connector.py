"""
fabric_connector.py
-------------------
Microsoft Fabric Data Warehouse connector.

Authentication order:
  1. notebookutils (inside a Fabric notebook — token is injected automatically)
  2. InteractiveBrowserCredential (local dev — opens a browser AAD login once,
     then caches the token in ~/.azure/)

Usage:
    from src.data_pipeline.fabric_connector import connect, fetch_eda_dataset

    conn = connect()
    df   = fetch_eda_dataset()
    conn.close()

Priceband classification
------------------------
Pricebands (Economy / Mid / Premium) are derived from actual MRP distribution
per category (not hardcoded). The pipeline runs in two steps:

  Step 1  fetch_mrp_distribution()
            - Runs _MRP_DIST_SQL against Fabric
            - Returns MRP percentiles per category

  Step 2  compute_priceband_breaks(mrp_df)
            - p33 -> Economy cap, p67 -> Mid cap, rounded to nearest Rs 500

  Step 3  fetch_eda_dataset(breaks)
            - Fetches style-level data via _EDA_SQL (no priceband in SQL)
            - Applies priceband classification in Python using the breaks dict
            - Aggregates to bucket level (store x category x priceband)
            - Returns bucket-level DataFrame identical to what the solver expects
"""

import json
import struct
from pathlib import Path

import numpy as np
import pandas as pd
import pyodbc

WAREHOUSE_SERVER   = "t5fulvvcjsjehnrpedrb4vbtli-crzekx4zfiqutls4y4njjiwi3y.datawarehouse.fabric.microsoft.com"
WAREHOUSE_DATABASE = "Arvind_Analytics_Warehouse"

_EDA_SQL = """
-- ============================================================
-- ARROW STORE REVENUE OPTIMISATION — STYLE-LEVEL EDA DATASET
-- Scope : Active Arrow stores | last 4 weeks
-- Grain : store x style x category
-- SOH   : FACT_FNO_BASE_SOH — Opening_SOH, 446 days history
--         AVG(Opening_SOH) over 4 weeks = true avg committed inventory
-- Note  : Priceband applied in Python using priceband_mapping.csv
-- ============================================================
WITH date_bounds AS (
    SELECT
        CONVERT(DATE, DATEADD(WEEK, -4, GETDATE())) AS window_start,
        CONVERT(DATE, GETDATE())                     AS window_end
),
active_arrow_stores AS (
    SELECT STORE_CODE, NAME_2 AS store_name
    FROM [Arvind_Analytics_Warehouse].[prd].[DIM_SAP_STORE_MASTER]
    WHERE ARROW  != 0
      AND STATUS  = 'ACTIVE'
),
sales_style AS (
    SELECT
        f.SAP_STORECODE                               AS store_id,
        f.STYLECODE                                   AS style_code,
        UPPER(LTRIM(RTRIM(f.CATEGORY)))              AS category,
        AVG(CAST(f.UNITMRP AS FLOAT))                AS avg_unit_mrp,
        SUM(f.NETAMT)                                 AS style_revenue_4w,
        SUM(f.QUANTITY)                               AS style_units_sold,
        SUM(f.TOTAL_MRP)                              AS style_total_mrp,
        SUM(f.TOTAL_MRP - f.NETAMT)                   AS style_discount,
        COUNT(DISTINCT f.INVOICENO)                   AS style_transactions,
        COUNT(DISTINCT CONVERT(DATE, f.INVOICE_DATE)) AS style_days_with_sales
    FROM [Arvind_Analytics_Warehouse].[prd].[FACT_FNO_SALES_TC_ONLINE_BASE] f
    INNER JOIN active_arrow_stores st ON f.SAP_STORECODE = st.STORE_CODE
    CROSS JOIN date_bounds d
    WHERE f.BRAND          = 'ARROW'
      AND f.INVOICETYPE    = 'SALES'
      AND f.QUALITY        = 'Q1'
      AND f.QUANTITY       > 0
      AND UPPER(LTRIM(RTRIM(f.CATEGORY))) NOT IN (
            'PROMO', 'SAMPLES', 'SCRAP', 'TRIMS', 'CARRY BAG'
      )
      AND CONVERT(DATE, f.INVOICE_DATE) >= d.window_start
      AND CONVERT(DATE, f.INVOICE_DATE) <  d.window_end
    GROUP BY f.SAP_STORECODE, f.STYLECODE, UPPER(LTRIM(RTRIM(f.CATEGORY)))
),
soh_style AS (
    -- AVG(Opening_SOH) over 4 weeks = true average inventory committed
    -- to this style each day — the correct denominator for revenue_rate.
    -- Opening_SOH is stock available at start of day before sales occur.
    -- SUM across sizes to get style-level SOH per day, then AVG across days.
    SELECT
        s.STORE_CODE                                    AS store_id,
        s.STYLECODE                                     AS style_code,
        AVG(daily_soh)                                  AS style_avg_daily_soh,
        AVG(daily_soh) * 7                              AS style_avg_weekly_soh,
        MIN(daily_soh)                                  AS style_min_soh,
        MAX(daily_soh)                                  AS style_max_soh,
        COUNT(DISTINCT s.INVENTORY_DATE)                AS style_soh_days
    FROM (
        -- Collapse sizes to style level per day first
        -- Qualify STORE_CODE with alias b to avoid ambiguity with active_arrow_stores
        SELECT
            b.STORE_CODE,
            b.STYLECODE,
            b.INVENTORY_DATE,
            SUM(b.Opening_SOH)  AS daily_soh
        FROM [Arvind_Analytics_Warehouse].[prd].[FACT_FNO_BASE_SOH] b
        INNER JOIN active_arrow_stores st ON b.STORE_CODE = st.STORE_CODE
        CROSS JOIN date_bounds d
        WHERE b.INVENTORY_DATE >= d.window_start
          AND b.INVENTORY_DATE <= d.window_end
        GROUP BY b.STORE_CODE, b.STYLECODE, b.INVENTORY_DATE
    ) s
    GROUP BY s.STORE_CODE, s.STYLECODE
),
soh_sizes AS (
    -- Count distinct sizes with Opening_SOH > 0 per store x style.
    -- Used to compute how many physical hangers each style occupies on display.
    -- display_capacity = total hangers; each style needs style_size_count hangers.
    SELECT
        b.STORE_CODE AS store_id,
        b.STYLECODE  AS style_code,
        COUNT(DISTINCT b.SIZE) AS style_size_count
    FROM [Arvind_Analytics_Warehouse].[prd].[FACT_FNO_BASE_SOH] b
    INNER JOIN active_arrow_stores st ON b.STORE_CODE = st.STORE_CODE
    CROSS JOIN date_bounds d
    WHERE b.INVENTORY_DATE >= d.window_start
      AND b.INVENTORY_DATE <= d.window_end
      AND b.Opening_SOH    >  0
    GROUP BY b.STORE_CODE, b.STYLECODE
),
latest_soh_date AS (
    -- Single-row CTE: the most recent inventory snapshot date.
    SELECT MAX(INVENTORY_DATE) AS snap_date
    FROM [Arvind_Analytics_Warehouse].[prd].[FACT_FNO_BASE_SOH]
),
current_soh_style AS (
    -- Today's exact SOH per store x style (sum across all sizes).
    -- This gives planners an accurate "right now" stock count, not a 4-week avg.
    SELECT
        b.STORE_CODE AS store_id,
        b.STYLECODE  AS style_code,
        SUM(b.Opening_SOH) AS current_soh
    FROM [Arvind_Analytics_Warehouse].[prd].[FACT_FNO_BASE_SOH] b
    INNER JOIN active_arrow_stores st ON b.STORE_CODE = st.STORE_CODE
    CROSS JOIN latest_soh_date ld
    WHERE b.INVENTORY_DATE = ld.snap_date
    GROUP BY b.STORE_CODE, b.STYLECODE
)
SELECT
    sl.store_id,
    st.store_name,
    sl.style_code,
    sl.category,
    sl.avg_unit_mrp,
    sl.style_revenue_4w,
    sl.style_units_sold,
    sl.style_total_mrp,
    sl.style_discount,
    sl.style_transactions,
    sl.style_days_with_sales,
    -- Correct SOH metrics from FACT_FNO_BASE_SOH
    COALESCE(so.style_avg_daily_soh,  0)    AS style_avg_daily_soh,
    COALESCE(so.style_avg_weekly_soh, 0)    AS style_avg_weekly_soh,
    COALESCE(so.style_min_soh,        0)    AS style_min_soh,
    COALESCE(so.style_max_soh,        0)    AS style_max_soh,
    COALESCE(so.style_soh_days,       0)    AS style_soh_days,
    -- Distinct sizes in stock — determines hanger count per style on display
    COALESCE(sz.style_size_count,     0)    AS style_size_count,
    -- Current (today's snapshot) SOH per style — accurate point-in-time stock
    COALESCE(cs.current_soh,          0)    AS current_soh,
    ld.snap_date                            AS soh_snapshot_date,
    d.window_start,
    d.window_end
FROM sales_style sl
INNER JOIN active_arrow_stores st ON st.STORE_CODE = sl.store_id
LEFT JOIN soh_style so
    ON  so.store_id   = sl.store_id
    AND so.style_code = sl.style_code
LEFT JOIN soh_sizes sz
    ON  sz.store_id   = sl.store_id
    AND sz.style_code = sl.style_code
LEFT JOIN current_soh_style cs
    ON  cs.store_id   = sl.store_id
    AND cs.style_code = sl.style_code
CROSS JOIN latest_soh_date ld
CROSS JOIN date_bounds d
ORDER BY sl.store_id, sl.category, sl.style_code;
"""
# ── Size break monitor SQL ───────────────────────────────────────────────────
# Fetches current size availability per store × style.
# Used in the Size Break Monitor EDA tab in the Streamlit app.
# Runs against FACT_FNO_BASE_SOH latest snapshot date.
_SIZE_BREAK_SQL = """
WITH latest_date AS (
    SELECT MAX(INVENTORY_DATE) AS snap_date
    FROM [Arvind_Analytics_Warehouse].[prd].[FACT_FNO_BASE_SOH]
),
active_arrow_stores AS (
    SELECT STORE_CODE, NAME_2 AS store_name
    FROM [Arvind_Analytics_Warehouse].[prd].[DIM_SAP_STORE_MASTER]
    WHERE ARROW != 0 AND STATUS = 'ACTIVE'
),
size_groups AS (
    SELECT SIZE, size_group FROM (VALUES
        ('S',   'ALPHA'),  ('M',  'ALPHA'), ('L',  'ALPHA'),
        ('XL',  'ALPHA'),  ('XXL','ALPHA'), ('3XL','ALPHA'),
        ('28',  'NUMERIC'),('30', 'NUMERIC'),('32', 'NUMERIC'),
        ('34',  'NUMERIC'),('36', 'NUMERIC'),('38', 'NUMERIC'),
        ('39',  'NUMERIC'),('40', 'NUMERIC'),('42', 'NUMERIC'),
        ('44',  'NUMERIC'),('46', 'NUMERIC'),('48', 'NUMERIC'),
        ('OP',  'SINGLE'), ('OS', 'SINGLE')
    ) AS t(SIZE, size_group)
),
current_soh AS (
    SELECT
        s.STORE_CODE,
        st.store_name,
        s.STYLECODE,
        s.SIZE,
        s.Opening_SOH,
        sg.size_group
    FROM [Arvind_Analytics_Warehouse].[prd].[FACT_FNO_BASE_SOH] s
    INNER JOIN active_arrow_stores st ON s.STORE_CODE = st.STORE_CODE
    INNER JOIN latest_date ld         ON s.INVENTORY_DATE = ld.snap_date
    LEFT  JOIN size_groups sg         ON s.SIZE = sg.SIZE
    WHERE s.SIZE NOT IN ('85','95','105','10','9','7','6','8','1','100','4XL','5XL','6XL')
),
style_summary AS (
    SELECT
        STORE_CODE,
        store_name,
        STYLECODE,
        size_group,
        COUNT(DISTINCT SIZE)                                                        AS sizes_present,
        SUM(Opening_SOH)                                                            AS total_soh,
        AVG(CAST(Opening_SOH AS FLOAT))                                             AS avg_soh_per_size,
        MIN(Opening_SOH)                                                            AS min_size_soh,
        MAX(Opening_SOH)                                                            AS max_size_soh,
        SUM(CASE WHEN Opening_SOH = 0  THEN 1 ELSE 0 END)                          AS zero_soh_sizes,
        SUM(CASE WHEN Opening_SOH <= 2 THEN 1 ELSE 0 END)                          AS thin_sizes,
        SUM(CASE WHEN Opening_SOH >= 3 THEN 1 ELSE 0 END)                          AS healthy_sizes,
        STRING_AGG(
            CASE WHEN Opening_SOH <= 2
                 THEN SIZE + '(' + CAST(CAST(Opening_SOH AS INT) AS VARCHAR) + ')'
            END, ', ')                                                               AS thin_size_list,
        STRING_AGG(
            CASE WHEN Opening_SOH = 0 THEN SIZE END, ', ')                         AS zero_size_list
    FROM current_soh
    GROUP BY STORE_CODE, store_name, STYLECODE, size_group
),
expected_sizes AS (
    SELECT 'ALPHA'   AS size_group, 6  AS expected_size_count
    UNION ALL
    SELECT 'NUMERIC' AS size_group, 10 AS expected_size_count
    UNION ALL
    SELECT 'SINGLE'  AS size_group, 1  AS expected_size_count
)
SELECT
    ss.STORE_CODE                                           AS store_id,
    ss.store_name,
    ss.STYLECODE                                            AS style_code,
    ss.size_group,
    ss.sizes_present,
    es.expected_size_count,
    ss.total_soh,
    ss.avg_soh_per_size,
    ss.min_size_soh,
    ss.max_size_soh,
    ss.zero_soh_sizes,
    ss.thin_sizes,
    ss.healthy_sizes,
    ss.thin_size_list,
    ss.zero_size_list,
    es.expected_size_count - ss.sizes_present               AS missing_sizes,
    CASE
        WHEN ss.zero_soh_sizes  > 0                         THEN 'BROKEN'
        WHEN ss.thin_sizes      > 0                         THEN 'AT RISK'
        WHEN ss.sizes_present   < es.expected_size_count    THEN 'INCOMPLETE RUN'
        ELSE                                                     'HEALTHY'
    END                                                     AS size_break_status,
    CASE
        WHEN ss.size_group = 'ALPHA'   AND ss.healthy_sizes >= 3 AND ss.zero_soh_sizes = 0 THEN 'PIVOTABLE'
        WHEN ss.size_group = 'NUMERIC' AND ss.healthy_sizes >= 4 AND ss.zero_soh_sizes = 0 THEN 'PIVOTABLE'
        WHEN ss.zero_soh_sizes > 2 OR ss.total_soh <= 3    THEN 'NOT PIVOTABLE'
        ELSE                                                     'MARGINAL'
    END                                                     AS pivotability,
    CASE
        WHEN ss.zero_soh_sizes  > 0 AND ss.size_group != 'SINGLE' THEN 'REPLENISH NOW'
        WHEN ss.thin_sizes      > 2                                THEN 'REPLENISH SOON'
        WHEN ss.thin_sizes      > 0                                THEN 'MONITOR'
        ELSE                                                            'OK'
    END                                                     AS replenishment_urgency,
    ld.snap_date
FROM style_summary ss
INNER JOIN latest_date ld    ON 1 = 1
LEFT  JOIN expected_sizes es ON es.size_group = ss.size_group
ORDER BY
    CASE WHEN ss.zero_soh_sizes > 0 THEN 1 WHEN ss.thin_sizes > 0 THEN 2 ELSE 3 END,
    ss.STORE_CODE, ss.STYLECODE;
"""


# ── MRP percentile discovery SQL ─────────────────────────────────────────────
# SQL Server: PERCENTILE_CONT requires OVER (PARTITION BY ...) — cannot be
# used as a plain GROUP BY aggregate. Split into:
#   raw         — filtered rows (category, stylecode, unitmrp)
#   percentiles — window-function percentiles per category, SELECT DISTINCT
#   counts      — COUNT DISTINCT / MIN / MAX via GROUP BY
# then JOIN counts and percentiles on category.
_MRP_DIST_SQL = """
WITH date_bounds AS (
    SELECT
        CONVERT(DATE, DATEADD(WEEK, -4, GETDATE())) AS window_start,
        CONVERT(DATE, GETDATE())                     AS window_end
),
active_arrow_stores AS (
    SELECT STORE_CODE
    FROM [Arvind_Analytics_Warehouse].[prd].[DIM_SAP_STORE_MASTER]
    WHERE ARROW != 0 AND STATUS = 'ACTIVE'
),
raw AS (
    SELECT
        UPPER(LTRIM(RTRIM(f.CATEGORY))) AS category,
        f.STYLECODE,
        f.UNITMRP
    FROM [Arvind_Analytics_Warehouse].[prd].[FACT_FNO_SALES_TC_ONLINE_BASE] f
    INNER JOIN active_arrow_stores st ON f.SAP_STORECODE = st.STORE_CODE
    CROSS JOIN date_bounds d
    WHERE f.BRAND       = 'ARROW'
      AND f.INVOICETYPE = 'SALES'
      AND UPPER(LTRIM(RTRIM(f.CATEGORY))) NOT IN (
            'PROMO', 'SAMPLES', 'SCRAP', 'TRIMS', 'CARRY BAG'
      )
      AND CONVERT(DATE, f.INVOICE_DATE) >= d.window_start
      AND CONVERT(DATE, f.INVOICE_DATE) <  d.window_end
),
percentiles AS (
    SELECT DISTINCT
        category,
        PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY UNITMRP) OVER (PARTITION BY category) AS p10,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY UNITMRP) OVER (PARTITION BY category) AS p25,
        PERCENTILE_CONT(0.33) WITHIN GROUP (ORDER BY UNITMRP) OVER (PARTITION BY category) AS p33,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY UNITMRP) OVER (PARTITION BY category) AS p50,
        PERCENTILE_CONT(0.67) WITHIN GROUP (ORDER BY UNITMRP) OVER (PARTITION BY category) AS p67,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY UNITMRP) OVER (PARTITION BY category) AS p75,
        PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY UNITMRP) OVER (PARTITION BY category) AS p90
    FROM raw
),
counts AS (
    SELECT
        category,
        COUNT(DISTINCT STYLECODE) AS style_count,
        COUNT(*)                  AS transaction_rows,
        MIN(UNITMRP)              AS min_mrp,
        MAX(UNITMRP)              AS max_mrp
    FROM raw
    GROUP BY category
)
SELECT
    c.category,
    c.style_count,
    c.transaction_rows,
    c.min_mrp,
    c.max_mrp,
    p.p10,
    p.p25,
    p.p33,
    p.p50,
    p.p67,
    p.p75,
    p.p90
FROM counts c
INNER JOIN percentiles p ON p.category = c.category
ORDER BY c.style_count DESC;
"""


# ── Deduplicated style-level MRP SQL (for KDE) ───────────────────────────────
# One row per style × category, fleet-wide (store dimension collapsed).
# This is what KDE runs on — each style counts once regardless of how many
# stores stock it, so popular styles don't inflate the density curve.
_MRP_STYLE_SQL = """
WITH date_bounds AS (
    SELECT
        CONVERT(DATE, DATEADD(WEEK, -4, GETDATE())) AS window_start,
        CONVERT(DATE, GETDATE())                     AS window_end
),
active_arrow_stores AS (
    SELECT STORE_CODE
    FROM [Arvind_Analytics_Warehouse].[prd].[DIM_SAP_STORE_MASTER]
    WHERE ARROW != 0 AND STATUS = 'ACTIVE'
)
SELECT
    UPPER(LTRIM(RTRIM(f.CATEGORY)))  AS category,
    f.STYLECODE                      AS style_code,
    AVG(CAST(f.UNITMRP AS FLOAT))    AS avg_mrp
FROM [Arvind_Analytics_Warehouse].[prd].[FACT_FNO_SALES_TC_ONLINE_BASE] f
INNER JOIN active_arrow_stores st ON f.SAP_STORECODE = st.STORE_CODE
CROSS JOIN date_bounds d
WHERE f.BRAND          = 'ARROW'
  AND f.INVOICETYPE    = 'SALES'
  AND f.QUALITY        = 'Q1'
  AND f.QUANTITY       > 0
  AND UPPER(LTRIM(RTRIM(f.CATEGORY))) NOT IN (
        'PROMO', 'SAMPLES', 'SCRAP', 'TRIMS', 'CARRY BAG'
  )
  AND CONVERT(DATE, f.INVOICE_DATE) >= d.window_start
  AND CONVERT(DATE, f.INVOICE_DATE) <  d.window_end
GROUP BY UPPER(LTRIM(RTRIM(f.CATEGORY))), f.STYLECODE
ORDER BY category, avg_mrp;
"""


# ── KDE break detection ───────────────────────────────────────────────────────

def _kde_breaks_for_category(
    mrp_values: np.ndarray,
    plot_path: Path = None,
    category: str = "",
    p33_cap: float = None,
    p67_cap: float = None,
) -> tuple:
    """
    Find 2 natural valley points in MRP distribution using Kernel Density Estimation.

    Strategy: fit KDE with Scott's bandwidth, evaluate on 500-point grid,
    find local minima (order=20 ≈ 180 Rs buffer each side), pick the 2 with
    the lowest density (deepest valleys = most significant price gaps).

    Parameters
    ----------
    mrp_values : array of style-level MRP values (one per style, deduplicated)
    plot_path  : if provided, save KDE chart as PNG here
    category   : category name for plot title
    p33_cap    : p33/p67 breaks drawn on plot for comparison
    p67_cap    : p33/p67 breaks drawn on plot for comparison

    Returns
    -------
    (economy_cap, mid_cap) as floats, or (None, None) if < 2 valleys found.
    """
    from scipy.stats import gaussian_kde
    from scipy.signal import argrelmin

    if len(mrp_values) < 10:
        return None, None

    kde = gaussian_kde(mrp_values, bw_method="scott")
    x_grid = np.linspace(mrp_values.min(), mrp_values.max(), 500)
    density = kde(x_grid)

    # order=20: valley must be lower than 20 neighbors on each side
    # With 500 pts over typical Rs 500-5000 range → ~180 Rs buffer each side
    minima_idx = argrelmin(density, order=20)[0]

    economy_cap, mid_cap = None, None
    if len(minima_idx) >= 2:
        # Take the 2 deepest valleys (lowest density = biggest price gap)
        sorted_by_depth = sorted(minima_idx, key=lambda i: density[i])
        top2 = sorted(sorted_by_depth[:2])          # sort back by MRP value
        economy_cap = float(x_grid[top2[0]])
        mid_cap     = float(x_grid[top2[1]])

    # ── Save KDE plot ─────────────────────────────────────────────────────
    if plot_path is not None:
        import matplotlib
        matplotlib.use("Agg")                        # non-interactive backend
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.fill_between(x_grid, density, alpha=0.25, color="#f59e0b")
        ax.plot(x_grid, density, color="#f59e0b", linewidth=1.8, label="KDE density")

        # Rug plot — actual style MRPs
        ax.plot(mrp_values, np.full_like(mrp_values, -0.00002),
                "|", color="#94a3b8", alpha=0.5, markersize=6, label=f"Styles (n={len(mrp_values)})")

        # KDE valleys
        if economy_cap is not None:
            ax.axvline(economy_cap, color="#10b981", linewidth=1.8, linestyle="--",
                       label=f"KDE Economy cap  ₹{economy_cap:,.0f}")
            ax.axvline(mid_cap,     color="#3b82f6", linewidth=1.8, linestyle="--",
                       label=f"KDE Mid cap      ₹{mid_cap:,.0f}")

        # p33/p67 comparison
        if p33_cap is not None:
            ax.axvline(p33_cap, color="#10b981", linewidth=1.2, linestyle=":",
                       alpha=0.7, label=f"p33 Economy cap  ₹{p33_cap:,.0f}")
            ax.axvline(p67_cap, color="#3b82f6", linewidth=1.2, linestyle=":",
                       alpha=0.7, label=f"p67 Mid cap      ₹{p67_cap:,.0f}")

        # Mark all found valleys
        for idx in minima_idx:
            ax.plot(x_grid[idx], density[idx], "v", color="#ef4444", markersize=7, alpha=0.7)

        ax.set_title(f"MRP Distribution — {category}  |  KDE Price Break Detection",
                     fontsize=13, pad=10)
        ax.set_xlabel("MRP (₹)", fontsize=11)
        ax.set_ylabel("Density", fontsize=11)
        ax.legend(fontsize=9, loc="upper right")
        ax.set_facecolor("#0f172a")
        fig.patch.set_facecolor("#1e293b")
        ax.tick_params(colors="#94a3b8")
        ax.xaxis.label.set_color("#94a3b8")
        ax.yaxis.label.set_color("#94a3b8")
        ax.title.set_color("#e2e8f0")
        for spine in ax.spines.values():
            spine.set_edgecolor("#334155")
        ax.grid(axis="x", color="#334155", linewidth=0.5, linestyle="--")

        fig.tight_layout()
        fig.savefig(plot_path, dpi=120, bbox_inches="tight",
                    facecolor=fig.get_facecolor())
        plt.close(fig)

    return economy_cap, mid_cap


# ── Priceband computation ─────────────────────────────────────────────────────

def compute_priceband_breaks(
    mrp_dist_df: pd.DataFrame,
    style_mrp_df: pd.DataFrame = None,
    plot_dir: Path = None,
) -> dict:
    """
    Compute data-driven priceband break points per category.

    Primary method: KDE on deduplicated style-level MRPs — finds natural price
    gaps (valleys in density curve). Uses the 2 deepest valleys as Economy and
    Mid caps. Falls back to p33/p67 when KDE cannot find 2 valleys (too few
    styles or unimodal distribution).

    Both KDE and p33/p67 breaks are stored in the returned dict for CSV export.

    Parameters
    ----------
    mrp_dist_df : DataFrame with p33, p67 per category (from _MRP_DIST_SQL)
    style_mrp_df: DataFrame with (category, style_code, avg_mrp) — one row per
                  style, deduplicated fleet-wide (from _MRP_STYLE_SQL).
                  If None, falls back to p33/p67 for all categories.
    plot_dir    : if provided, saves one KDE PNG per category here.

    Returns
    -------
    dict  {category: {economy_cap, mid_cap, p33_economy_cap, p67_mid_cap,
                      kde_economy_cap, kde_mid_cap, method}, "_default": {...}}
    """
    if plot_dir is not None:
        plot_dir = Path(plot_dir)
        plot_dir.mkdir(parents=True, exist_ok=True)

    # Index style MRPs by category for fast lookup
    style_by_cat = {}
    if style_mrp_df is not None:
        for cat, grp in style_mrp_df.groupby("category"):
            style_by_cat[cat] = grp["avg_mrp"].dropna().values

    breaks = {}
    for _, row in mrp_dist_df.iterrows():
        cat = row["category"]

        # ── p33/p67 breaks (rounded to nearest Rs 500) ───────────────────
        p33_cap = int(round(float(row["p33"]) / 500) * 500)
        p67_cap = int(round(float(row["p67"]) / 500) * 500)
        p33_cap = max(p33_cap, 500)
        if p67_cap <= p33_cap:
            p67_cap = p33_cap + 500

        # ── KDE breaks ───────────────────────────────────────────────────
        mrp_arr = style_by_cat.get(cat, np.array([]))
        plot_path = (plot_dir / f"kde_{cat.replace(' ', '_').replace('/', '_')}.png"
                     if plot_dir is not None else None)

        kde_eco, kde_mid = _kde_breaks_for_category(
            mrp_arr,
            plot_path=plot_path,
            category=cat,
            p33_cap=p33_cap,
            p67_cap=p67_cap,
        )

        if kde_eco is not None:
            economy_cap = kde_eco
            mid_cap     = kde_mid
            method      = "KDE"
        else:
            economy_cap = p33_cap
            mid_cap     = p67_cap
            method      = "p33/p67_fallback"

        breaks[cat] = {
            "economy_cap":     economy_cap,   # used for classification
            "mid_cap":         mid_cap,
            "p33_economy_cap": p33_cap,
            "p67_mid_cap":     p67_cap,
            "kde_economy_cap": round(kde_eco, 2) if kde_eco is not None else None,
            "kde_mid_cap":     round(kde_mid, 2) if kde_mid is not None else None,
            "method":          method,
        }

    breaks["_default"] = {
        "economy_cap": 2000, "mid_cap": 3000,
        "p33_economy_cap": 2000, "p67_mid_cap": 3000,
        "kde_economy_cap": None, "kde_mid_cap": None,
        "method": "default",
    }
    return breaks


def _classify_priceband(mrp: float, economy_cap: int, mid_cap: int) -> str:
    if mrp <= economy_cap:
        return "Economy"
    elif mrp <= mid_cap:
        return "Mid"
    return "Premium"


def _apply_priceband(style_df: pd.DataFrame, breaks: dict) -> pd.DataFrame:
    """
    Add 'priceband' and 'bucket_key' columns to style-level DataFrame
    using per-category break points from the breaks dict.
    """
    df = style_df.copy()
    default = breaks.get("_default", {"economy_cap": 2000, "mid_cap": 3000})

    def classify(row):
        b = breaks.get(row["category"], default)
        return _classify_priceband(row["avg_unit_mrp"], b["economy_cap"], b["mid_cap"])

    df["priceband"]  = df.apply(classify, axis=1)
    df["bucket_key"] = df["category"] + " | " + df["priceband"]
    return df


def _aggregate_to_buckets(style_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate style-level data to bucket level (store x category x priceband).
    Computes all derived metrics (revenue_rate, sell_through_pct, signals, etc.)
    that the solver and Streamlit app need.
    """
    grp_cols = ["store_id", "store_name", "category", "priceband", "bucket_key"]

    # style_count_in_bucket = styles with actual Opening_SOH > 0 in the 4-week window.
    # Only these can physically fill display slots — styles with zero avg daily SOH
    # have no stock and must not count toward the C7 cap.
    style_df["_has_soh"] = (style_df["style_avg_daily_soh"] > 0).astype(int)

    # current_soh: present only when fetched via the updated SQL (Option B).
    # Default to 0 if column is absent so aggregation always works.
    if "current_soh" not in style_df.columns:
        style_df["current_soh"] = 0

    grp = style_df.groupby(grp_cols)

    bucket = grp.agg(
        bucket_revenue_4w      = ("style_revenue_4w",    "sum"),
        units_sold_4w          = ("style_units_sold",    "sum"),
        total_mrp_4w           = ("style_total_mrp",     "sum"),
        total_discount_4w      = ("style_discount",      "sum"),
        transaction_count      = ("style_transactions",  "sum"),
        days_with_sales        = ("style_days_with_sales", "max"),
        avg_weekly_soh         = ("style_avg_weekly_soh", "sum"),
        min_daily_soh          = ("style_min_soh",       "min"),
        max_daily_soh          = ("style_max_soh",       "max"),
        soh_snapshot_days      = ("style_soh_days",      "max"),
        # Only styles with Opening_SOH > 0 count — these are physically fulfillable
        style_count_in_bucket  = ("_has_soh",            "sum"),
        # current_soh_bucket: today's exact SOH summed across all styles and sizes in bucket
        current_soh_bucket     = ("current_soh",         "sum"),
        window_start           = ("window_start",        "first"),
        window_end             = ("window_end",          "first"),
    ).reset_index()

    style_df.drop(columns=["_has_soh"], inplace=True)

    # avg_sizes_per_style: average distinct sizes per style at CATEGORY level (not bucket).
    # Sizes are a property of a category (SHIRT = S/M/L/XL/XXL regardless of priceband).
    # Computing at category level avoids sampling noise from priceband splits.
    # Fleet-wide average across all stores and all SOH > 0 styles in the category.
    if "style_size_count" in style_df.columns:
        _soh_styles = style_df[style_df["style_avg_daily_soh"] > 0]
        _category_avg_sizes = (
            _soh_styles.groupby("category")["style_size_count"]
            .mean()
            .reset_index()
            .rename(columns={"style_size_count": "avg_sizes_per_style"})
        )
        bucket = bucket.merge(_category_avg_sizes, on="category", how="left")
        bucket["avg_sizes_per_style"] = bucket["avg_sizes_per_style"].fillna(1.0).round(2)
    else:
        bucket["avg_sizes_per_style"] = 1.0

    # hangers_required: physical hanger count if all SOH-eligible styles are displayed.
    # display_capacity (Min Option Count) is hanger count, NOT style count.
    # Correct display slots = floor(display_share% * display_capacity / avg_sizes_per_style)
    bucket["hangers_required"] = (
        bucket["style_count_in_bucket"] * bucket["avg_sizes_per_style"]
    ).round(0).astype(int)

    # Derived metrics
    bucket["discount_pct"] = (
        (bucket["total_discount_4w"] / bucket["total_mrp_4w"] * 100)
        .where(bucket["total_mrp_4w"] > 0)
        .round(1)
    )
    # revenue_rate: 4-week revenue / avg_weekly_soh
    # avg_weekly_soh = SUM across styles of AVG(Opening_SOH over 28 days) * 7
    # Both numerator and denominator represent the same 4-week window.
    bucket["revenue_rate"] = (
        (bucket["bucket_revenue_4w"] / bucket["avg_weekly_soh"])
        .where(bucket["avg_weekly_soh"] > 0)
        .round(2)
    )
    # sell_through: units sold as % of (avg weekly inventory + units sold)
    bucket["sell_through_pct"] = (
        (
            bucket["units_sold_4w"]
            / (bucket["avg_weekly_soh"] + bucket["units_sold_4w"])
            * 100
        )
        .where(bucket["avg_weekly_soh"] > 0)
        .round(1)
    )
    bucket["avg_basket_value"] = (
        (bucket["bucket_revenue_4w"] / bucket["transaction_count"])
        .where(bucket["transaction_count"] > 0)
        .round(0)
    )
    bucket["avg_daily_revenue"] = (
        (bucket["bucket_revenue_4w"] / bucket["days_with_sales"])
        .where(bucket["days_with_sales"] > 0)
        .round(0)
    )

    # Per-store p25/p75 for signal_preview
    valid = bucket[bucket["revenue_rate"].notna()]
    store_pcts = (
        valid.groupby("store_id")["revenue_rate"]
        .quantile([0.25, 0.75])
        .unstack()
        .rename(columns={0.25: "_p25", 0.75: "_p75"})
        .reset_index()
    )
    bucket = bucket.merge(store_pcts, on="store_id", how="left")

    bucket["signal_preview"] = bucket.apply(
        lambda r: (
            "NO SOH"   if r["avg_weekly_soh"] == 0 else
            "NO SALES" if pd.isna(r["revenue_rate"]) else
            "INCREASE" if r["revenue_rate"] >= r["_p75"] else
            "REDUCE"   if r["revenue_rate"] <= r["_p25"] else
            "HOLD"
        ),
        axis=1,
    )
    bucket = bucket.drop(columns=["_p25", "_p75"])

    # Solver readiness
    n_buckets = bucket.groupby("store_id")["bucket_key"].transform("count")
    bucket["active_buckets_in_store"] = n_buckets
    bucket["solver_readiness"] = n_buckets.map(
        lambda n: (
            "IDEAL"            if n < 20  else
            "GOOD"             if n < 50  else
            "LIMITED"          if n < 100 else
            "COARSEN REQUIRED"
        )
    )

    # Data quality
    bucket["data_quality_flag"] = bucket["days_with_sales"].apply(
        lambda d: (
            "NO SALES DATA"             if pd.isna(d) else
            "THIN — use category fallback" if d < 14 else
            "OK"
        )
    )

    return bucket


# ── Connection ────────────────────────────────────────────────────────────────

def _get_token() -> str:
    """Obtain an AAD bearer token for the Fabric warehouse."""
    try:
        import notebookutils  # available inside Fabric notebooks
        return notebookutils.credentials.getToken("https://database.windows.net/")
    except ImportError:
        pass
    from azure.identity import InteractiveBrowserCredential
    credential = InteractiveBrowserCredential()
    return credential.get_token("https://database.windows.net/.default").token


def connect() -> pyodbc.Connection:
    """Open an authenticated pyodbc connection to the Fabric warehouse."""
    token        = _get_token()
    token_bytes  = bytes(token, "UTF-16LE")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={WAREHOUSE_SERVER},1433;"
        f"Database={WAREHOUSE_DATABASE};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
    )
    return pyodbc.connect(conn_str, attrs_before={1256: token_struct}, autocommit=True)


# ── Public fetch functions ────────────────────────────────────────────────────

def fetch_size_breaks() -> pd.DataFrame:
    """
    Fetch size break monitor data from the latest SOH snapshot.
    Returns one row per store × style with size availability metrics,
    size_break_status, pivotability, and replenishment_urgency.
    """
    conn = connect()
    try:
        print("Fetching size break monitor data...")
        df = pd.read_sql(_SIZE_BREAK_SQL, conn)
        print(f"  {len(df):,} store-style rows fetched.")
        return df
    finally:
        conn.close()


def fetch_mrp_distribution() -> pd.DataFrame:
    """
    Fetch MRP percentile distribution per category from the Fabric warehouse.
    Used to compute data-driven priceband break points via compute_priceband_breaks().
    """
    conn = connect()
    try:
        print("Fetching MRP distribution per category...")
        df = pd.read_sql(_MRP_DIST_SQL, conn)
        print(f"  {len(df):,} categories fetched.")
        return df
    finally:
        conn.close()


def fetch_style_mrp() -> pd.DataFrame:
    """
    Fetch deduplicated style-level MRP data for KDE price break detection.
    Returns one row per style × category (fleet-wide — store dimension collapsed).
    Each style counts once so popular styles don't inflate the KDE density.
    """
    conn = connect()
    try:
        print("Fetching deduplicated style-level MRP for KDE...")
        df = pd.read_sql(_MRP_STYLE_SQL, conn)
        print(f"  {len(df):,} style-category rows fetched ({df['category'].nunique()} categories).")
        return df
    finally:
        conn.close()


def fetch_eda_dataset(breaks: dict = None) -> pd.DataFrame:
    """
    Fetch style-level data from Fabric, apply per-category priceband classification,
    and aggregate to bucket level (store x category x priceband).

    Parameters
    ----------
    breaks : dict, optional
        Per-category priceband breaks from compute_priceband_breaks().
        When None, loads from data/processed/priceband_config.json if it exists,
        otherwise falls back to uniform defaults (Economy < Rs 2000, Mid < Rs 3000).

    Returns
    -------
    pd.DataFrame
        One row per store-bucket with revenue_rate, sell_through_pct,
        style_count_in_bucket, signal_preview, solver_readiness, and all
        columns the solver and Streamlit app expect.
    """
    # Load breaks from saved config if not supplied
    if breaks is None:
        config_path = Path(__file__).parents[2] / "data" / "processed" / "priceband_config.json"
        if config_path.exists():
            with open(config_path) as fh:
                breaks = json.load(fh).get("breaks", {})
        if not breaks:
            breaks = {"_default": {"economy_cap": 2000, "mid_cap": 3000}}

    conn = connect()
    try:
        print("Fetching style-level EDA data from Fabric...")
        style_df = pd.read_sql(_EDA_SQL, conn)
        print(f"  {len(style_df):,} style rows fetched.")
    finally:
        conn.close()

    print("Applying per-category priceband classification in Python...")
    style_df = _apply_priceband(style_df, breaks)

    print("Aggregating to bucket level (store x category x priceband)...")
    bucket_df = _aggregate_to_buckets(style_df)
    print(f"  {len(bucket_df):,} store-bucket rows.")

    return bucket_df


# ── CLI entrypoint ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Two-pass fetch: MRP distribution -> priceband breaks -> EDA dataset.

    Usage:
        python src/data_pipeline/fabric_connector.py

    Outputs (all in data/processed/):
        mrp_distribution_YYYY-MM-DD.csv   — MRP percentiles per category
        priceband_config.json             — per-category break points (used by app)
        priceband_mapping.csv             — human-readable mapping table
        eda_data_YYYY-MM-DD.csv           — bucket-level EDA dataset for solver + app
    """
    import argparse
    from datetime import date

    parser = argparse.ArgumentParser(
        description="Fetch Arrow EDA dataset from Fabric warehouse"
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).parents[2] / "data" / "processed"),
        help="Output directory (default: data/processed/)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("  Arrow EDA Dataset Generator")
    print(f"  Warehouse : {WAREHOUSE_SERVER}")
    print(f"  Database  : {WAREHOUSE_DATABASE}")
    print(f"  Output    : {out_dir}/")
    print(f"{'='*60}\n")

    today = date.today().isoformat()

    # ── Step 1: MRP distribution + KDE price break detection ─────────────
    print("Step 1/3  MRP price distribution per category...")
    mrp_df   = fetch_mrp_distribution()
    mrp_path = out_dir / f"mrp_distribution_{today}.csv"
    mrp_df.to_csv(mrp_path, index=False)
    print(f"  Saved: {mrp_path.name}")

    print("Step 1b/3  Deduplicated style MRPs for KDE...")
    style_mrp_df = fetch_style_mrp()

    kde_plot_dir = out_dir / "kde_plots"
    breaks = compute_priceband_breaks(mrp_df, style_mrp_df, plot_dir=kde_plot_dir)

    kde_count = sum(1 for v in breaks.values() if v.get("method") == "KDE")
    fb_count  = sum(1 for v in breaks.values() if "fallback" in v.get("method", ""))
    print(f"  KDE breaks: {kde_count} categories | p33/p67 fallback: {fb_count} categories")
    print(f"  KDE plots saved to: {kde_plot_dir}/")

    # Save JSON config (loaded by app and fetch_eda_dataset)
    config_path = out_dir / "priceband_config.json"
    with open(config_path, "w") as fh:
        json.dump({"generated_on": today, "breaks": breaks}, fh, indent=2)
    print(f"  Priceband config saved: {config_path.name}")

    # Save human-readable CSV mapping — both KDE and p33/p67 breaks
    mapping_rows = [
        {
            "category":        cat,
            "economy_cap":     v["economy_cap"],
            "mid_cap":         v["mid_cap"],
            "method":          v["method"],
            "kde_economy_cap": v["kde_economy_cap"],
            "kde_mid_cap":     v["kde_mid_cap"],
            "p33_economy_cap": v["p33_economy_cap"],
            "p67_mid_cap":     v["p67_mid_cap"],
        }
        for cat, v in sorted(breaks.items())
    ]
    pd.DataFrame(mapping_rows).to_csv(out_dir / "priceband_mapping.csv", index=False)
    print(f"  Priceband mapping CSV saved: priceband_mapping.csv")

    print(f"\n  {'Category':<25} {'Method':<18} {'Economy cap':>14}  {'Mid cap':>12}")
    print(f"  {'-'*72}")
    for cat, b in sorted((k, v) for k, v in breaks.items() if k != "_default"):
        eco = b['economy_cap']
        mid = b['mid_cap']
        eco_str = f"Rs {eco:>8,.0f}" if isinstance(eco, float) else f"Rs {eco:>8,}"
        mid_str = f"Rs {mid:>8,.0f}" if isinstance(mid, float) else f"Rs {mid:>8,}"
        print(f"  {cat:<25} {b['method']:<18} {eco_str}  {mid_str}")
    print(
        f"  {'_default (fallback)':<25} {'default':<18} "
        f"Rs {breaks['_default']['economy_cap']:>8,}  Rs {breaks['_default']['mid_cap']:>8,}"
    )

    # ── Step 2: EDA dataset with KDE pricebands ──────────────────────────
    print(f"\nStep 2/3  EDA dataset with KDE per-category pricebands...")
    df = fetch_eda_dataset(breaks)

    out_path = out_dir / f"eda_data_{today}.csv"
    df.to_csv(out_path, index=False)

    print(f"\nRows       : {len(df):,}")
    print(f"Stores     : {df['store_id'].nunique():,}")
    print(f"Buckets    : {len(df):,}")
    valid_rate = df["revenue_rate"].notna().sum()
    print(f"Valid rate : {valid_rate:,} / {len(df):,} buckets")
    print(f"Saved      : {out_path}")

    # ── Step 3: Size break monitor ────────────────────────────────────────
    print(f"\nStep 3/3  Size break monitor (latest SOH snapshot)...")

    sb_df = fetch_size_breaks()
    sb_path = out_dir / "size_breaks_latest.csv"
    sb_df.to_csv(sb_path, index=False)
    broken = (sb_df["size_break_status"] == "BROKEN").sum()
    at_risk = (sb_df["size_break_status"] == "AT RISK").sum()
    replenish_now = (sb_df["replenishment_urgency"] == "REPLENISH NOW").sum()
    print(f"  Styles: {len(sb_df):,} | Broken: {broken} | At Risk: {at_risk} | Replenish Now: {replenish_now}")
    print(f"  Saved: {sb_path.name}")

    print("\nRun solver next: python src/solver/run_solver.py --store all")
