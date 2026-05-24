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
    df   = fetch_eda_dataset(conn)
    conn.close()
"""

import json
import struct
import pandas as pd
import pyodbc

WAREHOUSE_SERVER   = "t5fulvvcjsjehnrpedrb4vbtli-crzekx4zfiqutls4y4njjiwi3y.datawarehouse.fabric.microsoft.com"
WAREHOUSE_DATABASE = "Arvind_Analytics_Warehouse"


# ── EDA SQL template ─────────────────────────────────────────────────────────
# <<PRICEBAND_CASE>> is replaced at runtime with a per-category CASE WHEN
# expression built from priceband_config.json.
# When no config exists, _build_eda_sql() injects the uniform fallback.
_EDA_SQL_TEMPLATE = """
-- ============================================================
-- ARROW STORE REVENUE OPTIMISATION — EDA DATASET
-- Scope : 130 active Arrow stores with sales (last 4 weeks)
-- Grain : store × category × priceband (bucket level)
-- Join  : SOH ↔ Sales via STYLE_CODE — category from sales side
-- Use   : Exploratory Data Analysis before IP solver build
-- ⚠️  ESTIMATE BEFORE RUNNING
-- Scans : FACT_FNO_SOH_DAILY + FACT_FNO_SALES_TC_ONLINE_BASE
--         + DIM_SAP_STORE_MASTER (dim, negligible)
-- Estimated : ~1.5–3.0 GB | Cost : ~$0.009–$0.019
-- ============================================================

WITH date_bounds AS (
    SELECT
        CONVERT(DATE, DATEADD(WEEK, -4, GETDATE()))  AS window_start,
        CONVERT(DATE, GETDATE())                      AS window_end
),

-- ── 1. Active Arrow stores ────────────────────────────────────────────
active_arrow_stores AS (
    SELECT STORE_CODE, NAME_2 AS store_name, REGION
    FROM [Arvind_Analytics_Warehouse].[prd].[DIM_SAP_STORE_MASTER]
    WHERE ARROW  != 0
      AND STATUS  = 'ACTIVE'
),

-- ── 2. Sales — revenue & volume per store × style ────────────────────
--    Category taxonomy comes entirely from this side
sales_style AS (
    SELECT
        f.SAP_STORECODE                                 AS store_id,
        f.STYLECODE                                     AS style_code,
        UPPER(LTRIM(RTRIM(f.CATEGORY)))                AS category,
        <<PRICEBAND_CASE>>                             AS priceband,
        SUM(f.NETAMT)                                  AS style_revenue_4w,
        SUM(f.QUANTITY)                                AS style_units_sold,
        SUM(f.TOTAL_MRP)                               AS style_total_mrp,
        SUM(f.TOTAL_MRP - f.NETAMT)                    AS style_discount,
        COUNT(DISTINCT f.INVOICENO)                    AS style_transactions,
        COUNT(DISTINCT CONVERT(DATE, f.INVOICE_DATE))  AS style_days_with_sales
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
    GROUP BY
        f.SAP_STORECODE,
        f.STYLECODE,
        UPPER(LTRIM(RTRIM(f.CATEGORY))),
        <<PRICEBAND_CASE>>
),

-- ── 3. SOH — inventory per store × style ─────────────────────────────
--    No CLASS or SUBBRAND used — style_code is the only join key
soh_style AS (
    SELECT
        s.SAP_STORE_ID                                                          AS store_id,
        s.STYLE_CODE                                                            AS style_code,
        SUM(CAST(s.SOH AS FLOAT))                                              AS style_total_soh,
        AVG(CAST(s.SOH AS FLOAT))                                              AS style_avg_daily_soh,
        MIN(s.SOH)                                                             AS style_min_soh,
        MAX(s.SOH)                                                             AS style_max_soh,
        COUNT(DISTINCT CONVERT(DATE, LEFT(CAST(s.LOAD_RUN_DATE AS VARCHAR), 8), 112))
                                                                               AS style_soh_days
    FROM [Arvind_Analytics_Warehouse].[prd].[FACT_FNO_SOH_DAILY] s
    INNER JOIN active_arrow_stores st ON s.SAP_STORE_ID = st.STORE_CODE
    CROSS JOIN date_bounds d
    WHERE s.BRAND = 'ARROW'
      AND CONVERT(DATE, LEFT(CAST(s.LOAD_RUN_DATE AS VARCHAR), 8), 112) >= d.window_start
      AND CONVERT(DATE, LEFT(CAST(s.LOAD_RUN_DATE AS VARCHAR), 8), 112) <= d.window_end
    GROUP BY
        s.SAP_STORE_ID,
        s.STYLE_CODE
),

-- ── 4. Join sales + SOH at style level, then roll up to bucket ────────
--    Category & priceband come from sales; SOH numbers from soh_style
style_joined AS (
    SELECT
        sl.store_id,
        sl.style_code,
        sl.category,
        sl.priceband,
        sl.style_revenue_4w,
        sl.style_units_sold,
        sl.style_total_mrp,
        sl.style_discount,
        sl.style_transactions,
        sl.style_days_with_sales,
        COALESCE(so.style_avg_daily_soh, 0) * 7    AS style_avg_weekly_soh,
        COALESCE(so.style_total_soh,     0)         AS style_total_soh,
        COALESCE(so.style_min_soh,       0)         AS style_min_soh,
        COALESCE(so.style_max_soh,       0)         AS style_max_soh,
        COALESCE(so.style_soh_days,      0)         AS style_soh_days
    FROM sales_style sl
    LEFT JOIN soh_style so
        ON  sl.store_id   = so.store_id
        AND sl.style_code = so.style_code
),

-- ── 5. Roll up from style to bucket (store × category × priceband) ───
bucket_agg AS (
    SELECT
        store_id,
        category,
        priceband,
        CONCAT(category, ' | ', priceband)          AS bucket_key,
        SUM(style_revenue_4w)                       AS bucket_revenue_4w,
        SUM(style_units_sold)                       AS units_sold_4w,
        SUM(style_total_mrp)                        AS total_mrp_4w,
        SUM(style_discount)                         AS total_discount_4w,
        CASE
            WHEN SUM(style_total_mrp) > 0
            THEN ROUND(SUM(style_discount) / SUM(style_total_mrp) * 100, 1)
            ELSE 0
        END                                         AS discount_pct,
        SUM(style_transactions)                     AS transaction_count,
        MAX(style_days_with_sales)                  AS days_with_sales,
        SUM(style_avg_weekly_soh)                   AS avg_weekly_soh,      -- sum across styles = bucket SOH
        SUM(style_total_soh)                        AS total_soh_units,
        MIN(style_min_soh)                          AS min_daily_soh,
        MAX(style_max_soh)                          AS max_daily_soh,
        MAX(style_soh_days)                         AS soh_snapshot_days,
        COUNT(DISTINCT style_code)                  AS style_count_in_bucket
    FROM style_joined
    GROUP BY store_id, category, priceband
),

-- ── 6. Join bucket aggregates to store master, compute final metrics ──
base AS (
    SELECT
        b.store_id,
        st.store_name,
        st.REGION,
        b.category,
        b.priceband,
        b.bucket_key,
        b.bucket_revenue_4w,
        b.units_sold_4w,
        b.total_mrp_4w,
        b.total_discount_4w,
        b.discount_pct,
        b.transaction_count,
        b.days_with_sales,
        b.style_count_in_bucket,
        b.avg_weekly_soh,
        b.total_soh_units,
        b.min_daily_soh,
        b.max_daily_soh,
        b.soh_snapshot_days,
        -- Revenue rate — core solver input
        -- Denominator: avg_weekly_soh × 4 = total SOH exposure over same 4-week window
        -- This matches the numerator (4-week revenue) making units ₹/unit over 4 weeks
        CASE
            WHEN b.avg_weekly_soh > 0
            THEN ROUND(b.bucket_revenue_4w / (b.avg_weekly_soh * 4), 2)
            ELSE NULL
        END                                         AS revenue_rate,
        -- Sell-through proxy
        CASE
            WHEN b.total_soh_units > 0
            THEN ROUND(
                    CAST(b.units_sold_4w AS FLOAT) /
                    NULLIF(b.total_soh_units + b.units_sold_4w, 0) * 100
                 , 1)
            ELSE NULL
        END                                         AS sell_through_pct,
        -- Avg basket value
        CASE
            WHEN b.transaction_count > 0
            THEN ROUND(b.bucket_revenue_4w / b.transaction_count, 0)
            ELSE NULL
        END                                         AS avg_basket_value,
        -- Avg daily revenue
        ROUND(b.bucket_revenue_4w /
            NULLIF(b.days_with_sales, 0), 0)        AS avg_daily_revenue,
        d.window_start,
        d.window_end
    FROM bucket_agg b
    INNER JOIN active_arrow_stores st ON st.STORE_CODE = b.store_id
    CROSS JOIN date_bounds d
),

-- ── 7. Per-store percentiles for signal preview ───────────────────────
store_percentiles AS (
    SELECT DISTINCT
        store_id,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY revenue_rate)
            OVER (PARTITION BY store_id)            AS p75_revenue_rate,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY revenue_rate)
            OVER (PARTITION BY store_id)            AS p25_revenue_rate
    FROM base
    WHERE revenue_rate IS NOT NULL
)

-- ── 8. FINAL SELECT ───────────────────────────────────────────────────
SELECT
    b.store_id,
    b.store_name,
    b.REGION,
    b.category,
    b.priceband,
    b.bucket_key,

    -- Revenue metrics
    b.bucket_revenue_4w,
    b.units_sold_4w,
    b.total_mrp_4w,
    b.total_discount_4w,
    b.discount_pct,
    b.transaction_count,
    b.avg_daily_revenue,
    b.style_count_in_bucket,

    -- Inventory metrics
    b.avg_weekly_soh,
    b.total_soh_units,
    b.min_daily_soh,
    b.max_daily_soh,
    b.soh_snapshot_days,

    -- Core solver input
    b.revenue_rate,

    -- Derived metrics
    b.sell_through_pct,
    b.avg_basket_value,

    -- Traffic light signal preview
    CASE
        WHEN b.avg_weekly_soh    IS NULL OR b.avg_weekly_soh = 0 THEN 'NO SOH'
        WHEN b.bucket_revenue_4w IS NULL                          THEN 'NO SALES'
        WHEN b.revenue_rate >= p.p75_revenue_rate                 THEN 'INCREASE'
        WHEN b.revenue_rate <= p.p25_revenue_rate                 THEN 'REDUCE'
        ELSE                                                           'HOLD'
    END                                                           AS signal_preview,

    -- Solver readiness
    COUNT(*) OVER (PARTITION BY b.store_id)                       AS active_buckets_in_store,
    CASE
        WHEN COUNT(*) OVER (PARTITION BY b.store_id) < 20  THEN 'IDEAL'
        WHEN COUNT(*) OVER (PARTITION BY b.store_id) < 50  THEN 'GOOD'
        WHEN COUNT(*) OVER (PARTITION BY b.store_id) < 100 THEN 'LIMITED'
        ELSE                                                     'COARSEN REQUIRED'
    END                                                           AS solver_readiness,

    -- Data quality
    b.days_with_sales,
    CASE
        WHEN b.days_with_sales IS NULL THEN 'NO SALES DATA'
        WHEN b.days_with_sales < 14    THEN 'THIN — use category fallback'
        ELSE                                'OK'
    END                                                           AS data_quality_flag,

    -- Window reference
    b.window_start,
    b.window_end

FROM base b
LEFT JOIN store_percentiles p ON p.store_id = b.store_id
ORDER BY
    b.store_id,
    CASE WHEN b.revenue_rate IS NULL THEN 1 ELSE 0 END,
    b.revenue_rate DESC;
"""


# ── MRP percentile discovery SQL ─────────────────────────────────────────────
# Fetches MRP distribution per category to derive data-driven priceband breaks.
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
)
SELECT
    UPPER(LTRIM(RTRIM(f.CATEGORY)))                            AS category,
    COUNT(DISTINCT f.STYLECODE)                                AS style_count,
    COUNT(*)                                                   AS transaction_rows,
    MIN(f.UNITMRP)                                             AS min_mrp,
    MAX(f.UNITMRP)                                             AS max_mrp,
    PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY f.UNITMRP)   AS p10,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY f.UNITMRP)   AS p25,
    PERCENTILE_CONT(0.33) WITHIN GROUP (ORDER BY f.UNITMRP)   AS p33,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY f.UNITMRP)   AS p50,
    PERCENTILE_CONT(0.67) WITHIN GROUP (ORDER BY f.UNITMRP)   AS p67,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY f.UNITMRP)   AS p75,
    PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY f.UNITMRP)   AS p90
FROM [Arvind_Analytics_Warehouse].[prd].[FACT_FNO_SALES_TC_ONLINE_BASE] f
INNER JOIN active_arrow_stores st ON f.SAP_STORECODE = st.STORE_CODE
CROSS JOIN date_bounds d
WHERE f.BRAND       = 'ARROW'
  AND f.INVOICETYPE = 'SALES'
  AND f.QUALITY     = 'Q1'
  AND f.QUANTITY    > 0
  AND UPPER(LTRIM(RTRIM(f.CATEGORY))) NOT IN (
        'PROMO', 'SAMPLES', 'SCRAP', 'TRIMS', 'CARRY BAG'
  )
  AND CONVERT(DATE, f.INVOICE_DATE) >= d.window_start
  AND CONVERT(DATE, f.INVOICE_DATE) <  d.window_end
GROUP BY UPPER(LTRIM(RTRIM(f.CATEGORY)))
ORDER BY style_count DESC;
"""


def compute_priceband_breaks(mrp_dist_df: pd.DataFrame) -> dict:
    """
    Compute data-driven priceband break points from MRP percentile distribution.

    Strategy: tertile split using p33 (Economy cap) and p67 (Mid cap).
    Values are rounded to the nearest ₹500 for clean, readable thresholds.

    Returns
    -------
    dict  {category: {"economy_cap": int, "mid_cap": int}, "_default": {...}}
    """
    breaks = {}
    for _, row in mrp_dist_df.iterrows():
        cat = row["category"]
        economy_cap = int(round(float(row["p33"]) / 500) * 500)
        mid_cap     = int(round(float(row["p67"]) / 500) * 500)

        # Ensure minimum ₹500 separation between bands
        economy_cap = max(economy_cap, 500)
        if mid_cap <= economy_cap:
            mid_cap = economy_cap + 500

        breaks[cat] = {"economy_cap": economy_cap, "mid_cap": mid_cap}

    breaks["_default"] = {"economy_cap": 2000, "mid_cap": 3000}
    return breaks


def _build_priceband_case(category_col: str, mrp_col: str, breaks: dict) -> str:
    """
    Build a nested SQL CASE WHEN expression for per-category pricebands.

    Example output (2 categories):
        CASE
            WHEN {category_col} = 'SHIRTS'   THEN
                CASE WHEN {mrp_col} <= 1500 THEN 'Economy' WHEN {mrp_col} <= 2500 THEN 'Mid' ELSE 'Premium' END
            WHEN {category_col} = 'TROUSERS' THEN
                CASE WHEN {mrp_col} <= 2000 THEN 'Economy' WHEN {mrp_col} <= 3500 THEN 'Mid' ELSE 'Premium' END
            ELSE
                CASE WHEN {mrp_col} <= 2000 THEN 'Economy' WHEN {mrp_col} <= 3000 THEN 'Mid' ELSE 'Premium' END
        END
    """
    default = breaks.get("_default", {"economy_cap": 2000, "mid_cap": 3000})
    lines = ["CASE"]
    for cat in sorted(k for k in breaks if k != "_default"):
        e, m = breaks[cat]["economy_cap"], breaks[cat]["mid_cap"]
        lines.append(
            f"            WHEN {category_col} = '{cat}' THEN\n"
            f"                CASE WHEN {mrp_col} <= {e} THEN 'Economy' "
            f"WHEN {mrp_col} <= {m} THEN 'Mid' ELSE 'Premium' END"
        )
    e, m = default["economy_cap"], default["mid_cap"]
    lines.append(
        f"            ELSE\n"
        f"                CASE WHEN {mrp_col} <= {e} THEN 'Economy' "
        f"WHEN {mrp_col} <= {m} THEN 'Mid' ELSE 'Premium' END"
    )
    lines.append("        END")
    return "\n".join(lines)


def _build_eda_sql(breaks: dict = None) -> str:
    """Inject the priceband CASE expression into the EDA SQL template."""
    if not breaks:
        breaks = {"_default": {"economy_cap": 2000, "mid_cap": 3000}}
    case_sql = _build_priceband_case(
        "UPPER(LTRIM(RTRIM(f.CATEGORY)))", "f.UNITMRP", breaks
    )
    return _EDA_SQL_TEMPLATE.replace("<<PRICEBAND_CASE>>", case_sql)


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


def fetch_mrp_distribution() -> pd.DataFrame:
    """
    Fetch MRP percentile distribution per category from the Fabric warehouse.
    Used to compute data-driven priceband break points via compute_priceband_breaks().
    """
    conn = connect()
    try:
        print("Fetching MRP distribution per category...")
        df = pd.read_sql(_MRP_DIST_SQL, conn)
        print(f"Done — {len(df):,} categories fetched.")
        return df
    finally:
        conn.close()


def fetch_eda_dataset(breaks: dict = None) -> pd.DataFrame:
    """
    Run the EDA SQL query against the Fabric warehouse and return a DataFrame.

    Parameters
    ----------
    breaks : dict, optional
        Per-category priceband breaks from compute_priceband_breaks().
        When None, uses uniform fallback (Economy <2000, Mid <3000, Premium ≥3000).

    The result has one row per store × bucket (Category × Priceband) covering
    the last 4 weeks, with revenue metrics, SOH metrics, revenue_rate,
    sell_through_pct, signal_preview, solver_readiness, and data_quality_flag.
    """
    conn = connect()
    sql = _build_eda_sql(breaks)
    try:
        print("Fetching EDA dataset from Fabric...")
        df = pd.read_sql(sql, conn)
        print(f"Done — {len(df):,} rows fetched.")
        return df
    finally:
        conn.close()


if __name__ == "__main__":
    """
    Generate the EDA dataset from the Fabric warehouse and save to disk.

    Usage:
        python src/data_pipeline/fabric_connector.py

    Output:
        data/processed/eda_data_YYYY-MM-DD.csv

    The Streamlit app reads this file automatically on next load.
    Authentication: opens a browser AAD login on first run; token is cached
    by azure-identity in ~/.azure/ for subsequent runs.
    """
    import argparse
    from pathlib import Path
    from datetime import date

    parser = argparse.ArgumentParser(
        description="Fetch Arrow EDA dataset from Fabric warehouse"
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).parents[2] / "data" / "processed"),
        help="Directory to write eda_data_YYYY-MM-DD.csv (default: data/processed/)",
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

    # ── Step 1: MRP distribution → data-driven priceband breaks ──────────
    print("Step 1/2  MRP price distribution per category...")
    mrp_df   = fetch_mrp_distribution()
    mrp_path = out_dir / f"mrp_distribution_{today}.csv"
    mrp_df.to_csv(mrp_path, index=False)
    print(f"  Saved: {mrp_path.name}")

    breaks = compute_priceband_breaks(mrp_df)
    config = {"generated_on": today, "breaks": breaks}
    config_path = out_dir / "priceband_config.json"
    with open(config_path, "w") as fh:
        json.dump(config, fh, indent=2)
    print(f"  Priceband config saved: {config_path.name}")
    print(f"  {'Category':<22} {'Economy cap':>12}  {'Mid cap':>10}")
    print(f"  {'-'*48}")
    for cat, b in sorted((k, v) for k, v in breaks.items() if k != "_default"):
        print(f"  {cat:<22} ≤ ₹{b['economy_cap']:>8,}  ≤ ₹{b['mid_cap']:>7,}")
    print(f"  {'_default (fallback)':<22} ≤ ₹{breaks['_default']['economy_cap']:>8,}  ≤ ₹{breaks['_default']['mid_cap']:>7,}")

    # ── Step 2: EDA dataset with data-driven pricebands ───────────────────
    print(f"\nStep 2/2  EDA dataset with data-driven pricebands...")
    df = fetch_eda_dataset(breaks)

    out_path = out_dir / f"eda_data_{today}.csv"
    df.to_csv(out_path, index=False)

    print(f"\nRows       : {len(df):,}")
    print(f"Stores     : {df['store_id'].nunique():,}")
    print(f"Buckets    : {len(df):,}")
    print(f"Saved      : {out_path}")
    print("\nOpen the Streamlit app and navigate to EDA Explorer → Price Bands to review.")
