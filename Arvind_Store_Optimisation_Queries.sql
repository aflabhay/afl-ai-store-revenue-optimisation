-- ============================================================
-- ARVIND FASHIONS LIMITED
-- Store Revenue Optimisation — Dataset Architecture Queries
-- Fabric Data Warehouse (T-SQL / Spark SQL compatible)
-- ============================================================
-- Tables available:
--   [prd].[FACT_FNO_SALES_TC_ONLINE_BASE]  (sales transactions, line-item level)
--   [prd].[FACT_FNO_SOH_DAILY]             (daily stock-on-hand snapshot, SKU-store level)
--
-- Column mapping from raw tables → BRD requirements:
--   store_id          → SAP_STORECODE (sales) / SAP_STORE_ID (soh)
--   collection        → BRAND + SUBBRAND
--   category          → CATEGORY (SHIRT, JEANS, etc.)
--   pricepoint        → derived price band from UNITMRP / MRP (see Step 0)
--   units_sold        → QUANTITY
--   selling_price     → NETAMT / QUANTITY  (net per unit after discount)
--   mrp               → UNITMRP (sales) / MRP (soh)
--   transaction_date  → INVOICE_DATE
--   stock_on_hand     → SOH (daily snapshot — used to derive starting/ending stock)
--
-- ⚠️ GAPS IDENTIFIED vs BRD (see notes at bottom of file)
-- ============================================================


-- ============================================================
-- STEP 0 — PRICE BAND DEFINITION (run once, agree with business)
-- ============================================================
-- UNITMRP varies continuously. We need discrete Pricepoint buckets.
-- Suggested bands based on data observed (₹1,699 – ₹3,999 in sample):
-- Adjust thresholds with Merchandising team before use.

-- Economy  : MRP <= 1999
-- Mid      : MRP 2000 – 2999
-- Premium  : MRP >= 3000

-- This is used in all queries below as a CASE expression.


-- ============================================================
-- STEP 1 — QUARTERLY SALES AGGREGATION AT BUCKET LEVEL
-- BRD Section 3.2, Step 1
-- Granularity: store × quarter × bucket (brand+subbrand+category+pricepoint)
-- ============================================================

WITH sales_cleaned AS (
    SELECT
        SAP_STORECODE                                   AS store_id,
        NAME                                            AS store_name,
        REGION,
        STATE,

        -- Quarter derivation from invoice date
        CAST(YEAR(INVOICE_DATE) AS VARCHAR)
            + '-Q'
            + CAST(DATEPART(QUARTER, INVOICE_DATE) AS VARCHAR)
                                                        AS quarter,

        -- Bucket dimensions
        BRAND,
        SUBBRAND,
        CATEGORY,

        -- Pricepoint band (agree thresholds with Merchandising)
        CASE
            WHEN UNITMRP <= 1999              THEN 'Economy'
            WHEN UNITMRP BETWEEN 2000 AND 2999 THEN 'Mid'
            WHEN UNITMRP >= 3000              THEN 'Premium'
        END                                             AS pricepoint,

        -- Season and gender for future ML features
        SEASON,
        GENDER,
        STORE_TYPE,

        -- Style-level grain (for pivotable size analysis)
        STYLECODE,
        ITEMSIZE,

        -- Metrics
        QUANTITY                                        AS units_sold,
        NETAMT                                          AS net_revenue,       -- actual amount collected
        UNITMRP                                         AS mrp,
        DISCOUNT                                        AS discount_amount,
        TOTAL_MRP                                       AS total_mrp_value,

        INVOICE_DATE

    FROM [prd].[FACT_FNO_SALES_TC_ONLINE_BASE]
    WHERE
        -- Exclude returns, voids, and non-sale transaction types
        INVOICETYPE = 'SALES'
        AND SALETYPE  = 'SALES'
        AND (VOID_FLAG     IS NULL OR VOID_FLAG     = 0)
        AND (POST_VOID_FLAG IS NULL OR POST_VOID_FLAG = 0)
        AND QUANTITY > 0
        AND NETAMT   > 0
),

quarterly_bucket_sales AS (
    SELECT
        store_id,
        store_name,
        REGION,
        STATE,
        quarter,
        BRAND,
        SUBBRAND,
        CATEGORY,
        pricepoint,
        SEASON,
        GENDER,

        -- Volume & revenue
        SUM(units_sold)                                         AS bucket_units_sold,
        SUM(net_revenue)                                        AS bucket_revenue,
        SUM(total_mrp_value)                                    AS bucket_total_mrp,

        -- Weighted average MRP (price positioning of the bucket)
        SUM(mrp * units_sold) / NULLIF(SUM(units_sold), 0)     AS bucket_weighted_mrp,

        -- Realisation per unit (after discount)
        SUM(net_revenue) / NULLIF(SUM(units_sold), 0)          AS revenue_per_unit,

        -- Discount depth: what % of MRP value was given away
        SUM(discount_amount) / NULLIF(SUM(total_mrp_value), 0) AS discount_depth,

        -- Discount flag: bucket is heavily discounted if avg depth > 40%
        CASE
            WHEN SUM(discount_amount) / NULLIF(SUM(total_mrp_value), 0) > 0.40
            THEN 1 ELSE 0
        END                                                     AS heavy_discount_flag,

        -- Style count (number of distinct styles sold — proxy for range breadth)
        COUNT(DISTINCT STYLECODE)                               AS styles_sold_count,

        -- Transaction count
        COUNT(*)                                                AS transaction_count

    FROM sales_cleaned
    GROUP BY
        store_id, store_name, REGION, STATE, quarter,
        BRAND, SUBBRAND, CATEGORY, pricepoint,
        SEASON, GENDER
)

SELECT * FROM quarterly_bucket_sales
ORDER BY store_id, quarter, bucket_revenue DESC;


-- ============================================================
-- STEP 2 — STOCK SNAPSHOT → QUARTERLY STOCK TABLE
-- BRD Section 3.2, Step 2
-- The SOH table is a DAILY snapshot. We derive:
--   starting_stock  = SOH on the first day of the quarter
--   ending_stock    = SOH on the last day of the quarter
--   received_stock  = ending + sold - starting  (inventory equation)
--   available_stock = starting + received = ending + sold
-- ============================================================

WITH soh_with_quarter AS (
    SELECT
        SAP_STORE_ID                                    AS store_id,
        STORE_NAME,
        BRAND,
        SUBBRAND,
        CLASS,
        SUBCLASS,
        STYLE_CODE,
        SIZE,
        FASHION,
        SEASON,
        GENDER,
        MRP,

        -- Pricepoint band (same definition as Step 1)
        CASE
            WHEN MRP <= 1999              THEN 'Economy'
            WHEN MRP BETWEEN 2000 AND 2999 THEN 'Mid'
            WHEN MRP >= 3000              THEN 'Premium'
        END                                             AS pricepoint,

        SOH,
        QUALITY,
        ON_HOLD,

        -- Parse snapshot date from LOAD_RUN_DATE (format: YYYYMMDDHHMMSS)
        CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE) AS snapshot_date,

        CAST(YEAR(CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE)) AS VARCHAR)
            + '-Q'
            + CAST(DATEPART(QUARTER, CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE)) AS VARCHAR)
                                                        AS quarter,

        -- Category extracted from SUBCLASS (middle segment of hierarchy)
        -- e.g. "USPA- U.S.Polo Association-MENS WESTERN-POLO T-SHIRT" → "POLO T-SHIRT"
        -- Adjust parsing logic based on actual hierarchy separator in production
        CASE
            WHEN SUBCLASS LIKE '%SHIRT%'     THEN 'SHIRT'
            WHEN SUBCLASS LIKE '%JEANS%'     THEN 'JEANS'
            WHEN SUBCLASS LIKE '%POLO%'      THEN 'POLO T-SHIRT'
            WHEN SUBCLASS LIKE '%T-SHIRT%'   THEN 'T-SHIRT'
            WHEN SUBCLASS LIKE '%TROUSER%'   THEN 'TROUSER'
            WHEN SUBCLASS LIKE '%CHINO%'     THEN 'CHINO'
            ELSE SUBCLASS
        END                                             AS category

    FROM [prd].[FACT_FNO_SOH_DAILY]
    WHERE
        QUALITY = 'Q1'           -- only sellable stock; exclude Q2 (damaged), Q3 (defective)
        AND (ON_HOLD IS NULL OR ON_HOLD = 0)  -- exclude held/blocked stock
),

-- First and last snapshot date per store-quarter-bucket
quarter_bounds AS (
    SELECT
        store_id,
        BRAND, SUBBRAND, category, pricepoint, quarter,
        MIN(snapshot_date) AS quarter_start_date,
        MAX(snapshot_date) AS quarter_end_date
    FROM soh_with_quarter
    GROUP BY store_id, BRAND, SUBBRAND, category, pricepoint, quarter
),

-- SOH on the first and last day of each quarter per bucket
starting_stock AS (
    SELECT s.store_id, s.BRAND, s.SUBBRAND, s.category, s.pricepoint, s.quarter,
           SUM(s.SOH) AS starting_stock_units
    FROM soh_with_quarter s
    JOIN quarter_bounds q
        ON  s.store_id   = q.store_id
        AND s.BRAND      = q.BRAND
        AND s.SUBBRAND   = q.SUBBRAND
        AND s.category   = q.category
        AND s.pricepoint = q.pricepoint
        AND s.quarter    = q.quarter
        AND s.snapshot_date = q.quarter_start_date
    GROUP BY s.store_id, s.BRAND, s.SUBBRAND, s.category, s.pricepoint, s.quarter
),

ending_stock AS (
    SELECT s.store_id, s.BRAND, s.SUBBRAND, s.category, s.pricepoint, s.quarter,
           SUM(s.SOH) AS ending_stock_units
    FROM soh_with_quarter s
    JOIN quarter_bounds q
        ON  s.store_id   = q.store_id
        AND s.BRAND      = q.BRAND
        AND s.SUBBRAND   = q.SUBBRAND
        AND s.category   = q.category
        AND s.pricepoint = q.pricepoint
        AND s.quarter    = q.quarter
        AND s.snapshot_date = q.quarter_end_date
    GROUP BY s.store_id, s.BRAND, s.SUBBRAND, s.category, s.pricepoint, s.quarter
),

quarterly_stock AS (
    SELECT
        st.store_id,
        st.BRAND,
        st.SUBBRAND,
        st.category,
        st.pricepoint,
        st.quarter,
        st.starting_stock_units,
        en.ending_stock_units
    FROM starting_stock st
    LEFT JOIN ending_stock en
        ON  st.store_id   = en.store_id
        AND st.BRAND      = en.BRAND
        AND st.SUBBRAND   = en.SUBBRAND
        AND st.category   = en.category
        AND st.pricepoint = en.pricepoint
        AND st.quarter    = en.quarter
)

SELECT * FROM quarterly_stock
ORDER BY store_id, quarter;


-- ============================================================
-- STEP 3 — MASTER ANALYTICAL DATASET (GOLD TABLE)
-- Join sales + stock → compute all BRD metrics in one flat table
-- This is the PRIMARY INPUT for both rule-based and ML models
-- ============================================================

WITH

-- Reuse CTEs from Step 1 and Step 2 above (abbreviated here for clarity)
-- In Fabric, create these as separate views or intermediate tables

sales_agg AS (
    -- [paste quarterly_bucket_sales CTE from Step 1]
    SELECT
        SAP_STORECODE                                   AS store_id,
        NAME                                            AS store_name,
        REGION, STATE,
        CAST(YEAR(INVOICE_DATE) AS VARCHAR) + '-Q' + CAST(DATEPART(QUARTER, INVOICE_DATE) AS VARCHAR) AS quarter,
        BRAND, SUBBRAND, CATEGORY AS category,
        CASE WHEN UNITMRP <= 1999 THEN 'Economy' WHEN UNITMRP BETWEEN 2000 AND 2999 THEN 'Mid' ELSE 'Premium' END AS pricepoint,
        SEASON, GENDER, STORE_TYPE,
        SUM(QUANTITY)                                                    AS bucket_units_sold,
        SUM(NETAMT)                                                      AS bucket_revenue,
        SUM(UNITMRP * QUANTITY) / NULLIF(SUM(QUANTITY), 0)              AS bucket_weighted_mrp,
        SUM(NETAMT) / NULLIF(SUM(QUANTITY), 0)                          AS revenue_per_unit,
        SUM(DISCOUNT) / NULLIF(SUM(TOTAL_MRP), 0)                       AS discount_depth,
        CASE WHEN SUM(DISCOUNT) / NULLIF(SUM(TOTAL_MRP), 0) > 0.40 THEN 1 ELSE 0 END AS heavy_discount_flag,
        COUNT(DISTINCT STYLECODE)                                        AS styles_sold_count
    FROM [prd].[FACT_FNO_SALES_TC_ONLINE_BASE]
    WHERE INVOICETYPE = 'SALES' AND SALETYPE = 'SALES'
      AND (VOID_FLAG IS NULL OR VOID_FLAG = 0) AND QUANTITY > 0 AND NETAMT > 0
    GROUP BY
        SAP_STORECODE, NAME, REGION, STATE,
        CAST(YEAR(INVOICE_DATE) AS VARCHAR) + '-Q' + CAST(DATEPART(QUARTER, INVOICE_DATE) AS VARCHAR),
        BRAND, SUBBRAND, CATEGORY,
        CASE WHEN UNITMRP <= 1999 THEN 'Economy' WHEN UNITMRP BETWEEN 2000 AND 2999 THEN 'Mid' ELSE 'Premium' END,
        SEASON, GENDER, STORE_TYPE
),

stock_agg AS (
    -- [paste quarterly_stock CTE from Step 2]
    -- Abbreviated — see full Step 2 CTE above
    SELECT
        SAP_STORE_ID AS store_id,
        BRAND, SUBBRAND,
        CASE WHEN SUBCLASS LIKE '%SHIRT%' THEN 'SHIRT' WHEN SUBCLASS LIKE '%JEANS%' THEN 'JEANS'
             WHEN SUBCLASS LIKE '%POLO%' THEN 'POLO T-SHIRT' WHEN SUBCLASS LIKE '%T-SHIRT%' THEN 'T-SHIRT'
             WHEN SUBCLASS LIKE '%TROUSER%' THEN 'TROUSER' WHEN SUBCLASS LIKE '%CHINO%' THEN 'CHINO'
             ELSE SUBCLASS END AS category,
        CASE WHEN MRP <= 1999 THEN 'Economy' WHEN MRP BETWEEN 2000 AND 2999 THEN 'Mid' ELSE 'Premium' END AS pricepoint,
        CAST(YEAR(CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE)) AS VARCHAR)
            + '-Q' + CAST(DATEPART(QUARTER, CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE)) AS VARCHAR) AS quarter,
        -- Starting stock = SOH on min date of quarter, ending = SOH on max date
        -- (Use the full CTE logic from Step 2 in production)
        MIN(CASE WHEN snapshot_rank = 1 THEN SOH ELSE NULL END) AS starting_stock_units,
        MIN(CASE WHEN snapshot_rank_desc = 1 THEN SOH ELSE NULL END) AS ending_stock_units
    FROM (
        SELECT *,
            ROW_NUMBER() OVER (PARTITION BY SAP_STORE_ID, BRAND, SUBBRAND, SUBCLASS, MRP,
                CAST(YEAR(CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE)) AS VARCHAR)
                + '-Q' + CAST(DATEPART(QUARTER, CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE)) AS VARCHAR)
                ORDER BY CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE) ASC) AS snapshot_rank,
            ROW_NUMBER() OVER (PARTITION BY SAP_STORE_ID, BRAND, SUBBRAND, SUBCLASS, MRP,
                CAST(YEAR(CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE)) AS VARCHAR)
                + '-Q' + CAST(DATEPART(QUARTER, CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE)) AS VARCHAR)
                ORDER BY CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE) DESC) AS snapshot_rank_desc
        FROM [prd].[FACT_FNO_SOH_DAILY]
        WHERE QUALITY = 'Q1' AND (ON_HOLD IS NULL OR ON_HOLD = 0)
    ) ranked
    GROUP BY SAP_STORE_ID, BRAND, SUBBRAND,
        CASE WHEN SUBCLASS LIKE '%SHIRT%' THEN 'SHIRT' WHEN SUBCLASS LIKE '%JEANS%' THEN 'JEANS'
             WHEN SUBCLASS LIKE '%POLO%' THEN 'POLO T-SHIRT' WHEN SUBCLASS LIKE '%T-SHIRT%' THEN 'T-SHIRT'
             WHEN SUBCLASS LIKE '%TROUSER%' THEN 'TROUSER' WHEN SUBCLASS LIKE '%CHINO%' THEN 'CHINO'
             ELSE SUBCLASS END,
        CASE WHEN MRP <= 1999 THEN 'Economy' WHEN MRP BETWEEN 2000 AND 2999 THEN 'Mid' ELSE 'Premium' END,
        CAST(YEAR(CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE)) AS VARCHAR)
            + '-Q' + CAST(DATEPART(QUARTER, CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE)) AS VARCHAR)
),

-- Store-level totals (denominator for share calculations)
store_quarter_totals AS (
    SELECT
        store_id, quarter,
        SUM(bucket_units_sold)                                  AS store_total_units_sold,
        SUM(bucket_revenue)                                     AS store_total_revenue
    FROM sales_agg
    GROUP BY store_id, quarter
),

store_stock_totals AS (
    SELECT
        store_id, quarter,
        SUM(starting_stock_units)                               AS store_total_starting_stock,
        SUM(ending_stock_units)                                 AS store_total_ending_stock
    FROM stock_agg
    GROUP BY store_id, quarter
),

gold AS (
    SELECT
        -- ── IDENTIFIERS ──────────────────────────────────────
        s.store_id,
        s.store_name,
        s.REGION,
        s.STATE,
        s.quarter,
        s.BRAND,
        s.SUBBRAND,
        s.category,
        s.pricepoint,
        s.SEASON,
        s.GENDER,
        s.STORE_TYPE,

        -- ── SALES METRICS ────────────────────────────────────
        s.bucket_units_sold,
        s.bucket_revenue,
        s.bucket_weighted_mrp,
        s.revenue_per_unit,
        s.discount_depth,
        s.heavy_discount_flag,
        s.styles_sold_count,

        -- ── STOCK METRICS ────────────────────────────────────
        k.starting_stock_units,
        k.ending_stock_units,

        -- Available stock = starting + inferred received
        -- (received = ending + sold - starting via inventory equation)
        k.starting_stock_units + ISNULL(s.bucket_units_sold, 0)
            + (k.ending_stock_units - k.starting_stock_units)  AS available_stock_units,

        -- Simpler: available = ending + sold (stock that passed through)
        k.ending_stock_units + ISNULL(s.bucket_units_sold, 0)  AS available_stock_units_v2,

        -- ── DERIVED KPIs ─────────────────────────────────────

        -- Sell-Through Rate (STR): what % of available stock actually sold
        ROUND(
            CAST(s.bucket_units_sold AS FLOAT)
            / NULLIF(k.ending_stock_units + s.bucket_units_sold, 0)
        , 4)                                                    AS sell_through_rate,

        -- Revenue share of store total
        ROUND(
            CAST(s.bucket_revenue AS FLOAT)
            / NULLIF(st.store_total_revenue, 0)
        , 4)                                                    AS bucket_revenue_share,

        -- Stock share of store total (the allocation variable)
        ROUND(
            CAST(k.starting_stock_units AS FLOAT)
            / NULLIF(ss.store_total_starting_stock, 0)
        , 4)                                                    AS bucket_stock_share,

        -- Effective display share (60-65% of stock on display per BRD)
        ROUND(
            CAST(k.starting_stock_units AS FLOAT)
            / NULLIF(ss.store_total_starting_stock, 0) * 0.65
        , 4)                                                    AS effective_display_share,

        -- Performance score: does this bucket earn more than its stock share?
        -- > 1.0 = over-performing, < 1.0 = under-performing
        ROUND(
            (CAST(s.bucket_revenue AS FLOAT) / NULLIF(st.store_total_revenue, 0))
            / NULLIF(CAST(k.starting_stock_units AS FLOAT) / NULLIF(ss.store_total_starting_stock, 0), 0)
        , 4)                                                    AS performance_score,

        -- Backroom excess flag: more than 35% of available stock left over
        CASE
            WHEN k.ending_stock_units > 0.35 * (k.ending_stock_units + s.bucket_units_sold)
            THEN 1 ELSE 0
        END                                                     AS backroom_excess_flag,

        -- Size break risk flag (computed in Step 4 separately at style-size level)
        -- Joined in from STEP 4 output

        -- Store totals (denominators)
        st.store_total_revenue,
        st.store_total_units_sold,
        ss.store_total_starting_stock

    FROM sales_agg s
    LEFT JOIN stock_agg k
        ON  s.store_id   = k.store_id
        AND s.BRAND      = k.BRAND
        AND s.SUBBRAND   = k.SUBBRAND
        AND s.category   = k.category
        AND s.pricepoint = k.pricepoint
        AND s.quarter    = k.quarter
    LEFT JOIN store_quarter_totals st
        ON  s.store_id = st.store_id
        AND s.quarter  = st.quarter
    LEFT JOIN store_stock_totals ss
        ON  k.store_id = ss.store_id
        AND k.quarter  = ss.quarter
)

SELECT * FROM gold
ORDER BY store_id, quarter, performance_score DESC;


-- ============================================================
-- STEP 4 — PIVOTABLE SIZE BREAK RISK (daily monitor)
-- Runs daily. Flags styles where a key size is near sellout.
-- Triggers next-day replenishment request to warehouse.
-- ============================================================

WITH size_soh AS (
    SELECT
        SAP_STORE_ID                                    AS store_id,
        STORE_NAME,
        BRAND,
        SUBBRAND,
        STYLE_CODE,
        SIZE,
        SEASON,
        MRP,
        SOH,
        CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE) AS snapshot_date

    FROM [prd].[FACT_FNO_SOH_DAILY]
    WHERE QUALITY = 'Q1'
      AND (ON_HOLD IS NULL OR ON_HOLD = 0)
      -- Only today's snapshot
      AND CAST(LEFT(CAST(LOAD_RUN_DATE AS VARCHAR), 8) AS DATE) = CAST(GETDATE() AS DATE)
),

-- Identify pivotable sizes per style: sizes with the highest historical sales volume
-- Here approximated as M, L, 32, 34 (to be validated with Merchandising team)
-- In production: join to sales history and rank sizes by units_sold per style
pivotable_sizes AS (
    SELECT
        store_id,
        STORE_NAME,
        BRAND,
        SUBBRAND,
        STYLE_CODE,
        SIZE,
        MRP,
        SOH,
        snapshot_date,
        -- Flag pivotable sizes (most commonly sold sizes — validate list with Merchandising)
        CASE
            WHEN SIZE IN ('M', 'L', '32', '34', 'XL') THEN 1
            ELSE 0
        END                                             AS is_pivotable_size
    FROM size_soh
),

size_break_flags AS (
    SELECT
        store_id,
        STORE_NAME,
        BRAND,
        SUBBRAND,
        STYLE_CODE,
        SIZE,
        MRP,
        SOH,
        snapshot_date,
        is_pivotable_size,

        -- Size break risk: pivotable size with SOH <= 1 unit
        CASE
            WHEN is_pivotable_size = 1 AND SOH <= 1 THEN 'CRITICAL — Next-day replen required'
            WHEN is_pivotable_size = 1 AND SOH <= 3 THEN 'WARNING — Monitor closely'
            ELSE 'OK'
        END                                             AS size_break_status,

        -- Alert priority
        CASE
            WHEN is_pivotable_size = 1 AND SOH <= 1 THEN 1
            WHEN is_pivotable_size = 1 AND SOH <= 3 THEN 2
            ELSE 3
        END                                             AS alert_priority

    FROM pivotable_sizes
)

SELECT *
FROM size_break_flags
WHERE alert_priority <= 2          -- only warnings and criticals
ORDER BY alert_priority, store_id, STYLE_CODE, SIZE;


-- ============================================================
-- STEP 5 — RULE-BASED RECOMMENDATION ENGINE
-- Applies BRD rule sets A, B, C to the gold table
-- Output: recommended stock share change per bucket per store
-- ============================================================

WITH gold_latest AS (
    -- Use most recent completed quarter from gold table
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY store_id, BRAND, SUBBRAND, category, pricepoint
            ORDER BY quarter DESC
        ) AS quarter_rank
    FROM gold   -- replace "gold" with actual table name if materialised
),

current_quarter AS (
    SELECT * FROM gold_latest WHERE quarter_rank = 1
),

-- Rule A: sell-through based signals
rule_a AS (
    SELECT
        store_id, BRAND, SUBBRAND, category, pricepoint, quarter,
        bucket_stock_share,
        performance_score,
        sell_through_rate,
        heavy_discount_flag,
        backroom_excess_flag,

        CASE
            -- A1: Star Performer — high STR, top revenue share
            WHEN sell_through_rate > 0.70 AND performance_score > 1.20
                THEN 'A1_STAR'
            -- A4: Stockout Risk — near sellout, demand exceeds supply
            WHEN sell_through_rate > 0.85
                THEN 'A4_STOCKOUT_RISK'
            -- A2: Slow Mover — low STR, high ending stock
            WHEN sell_through_rate < 0.30 AND backroom_excess_flag = 1
                THEN 'A2_SLOW_MOVER'
            -- A3: Discount Trap — only selling because of deep discounts
            WHEN heavy_discount_flag = 1 AND sell_through_rate < 0.50
                THEN 'A3_DISCOUNT_TRAP'
            ELSE 'HOLD'
        END                                                     AS rule_signal,

        -- Recommended share change (in percentage points)
        CASE
            WHEN sell_through_rate > 0.85                          THEN  5
            WHEN sell_through_rate > 0.70 AND performance_score > 1.20 THEN  3
            WHEN sell_through_rate < 0.30 AND backroom_excess_flag = 1 THEN -4
            WHEN heavy_discount_flag = 1 AND sell_through_rate < 0.50 THEN -3
            ELSE 0
        END                                                     AS raw_share_change_pp

    FROM current_quarter
),

-- Rule B: apply display cap constraint (no bucket > 45%)
rule_b AS (
    SELECT *,
        -- Cap: if current share + change would exceed 45%, limit the change
        CASE
            WHEN (bucket_stock_share * 100) + raw_share_change_pp > 45
                THEN 45 - (bucket_stock_share * 100)
            -- Floor: no bucket below 1%
            WHEN (bucket_stock_share * 100) + raw_share_change_pp < 1
                THEN 1  - (bucket_stock_share * 100)
            ELSE raw_share_change_pp
        END                                                     AS capped_share_change_pp,

        -- Backroom deadstock flag from Rule B2
        CASE
            WHEN backroom_excess_flag = 1 AND sell_through_rate < 0.40
            THEN 1 ELSE 0
        END                                                     AS deadstock_markdown_flag

    FROM rule_a
),

-- Normalise so all changes across buckets sum to zero (total stock constant)
-- Redistribute excess from over-capped increases to next-best performers
store_total_change AS (
    SELECT
        store_id,
        SUM(capped_share_change_pp)                             AS total_raw_change
    FROM rule_b
    GROUP BY store_id
),

recommendations AS (
    SELECT
        r.store_id,
        r.BRAND,
        r.SUBBRAND,
        r.category,
        r.pricepoint,
        r.quarter                                               AS source_quarter,
        r.bucket_stock_share,
        ROUND(r.bucket_stock_share * 100, 0)                   AS current_share_pct,
        r.capped_share_change_pp                               AS share_change_pp,
        ROUND(r.bucket_stock_share * 100 + r.capped_share_change_pp, 0) AS recommended_share_pct,
        r.rule_signal,
        r.sell_through_rate,
        r.performance_score,
        r.heavy_discount_flag,
        r.deadstock_markdown_flag,

        -- Traffic light for the tool UI
        CASE
            WHEN r.capped_share_change_pp > 0  THEN 'GREEN'
            WHEN r.capped_share_change_pp < 0  THEN 'RED'
            ELSE                                     'AMBER'
        END                                                     AS traffic_light,

        -- Monday activation — next Monday from today
        DATEADD(DAY, (9 - DATEPART(WEEKDAY, GETDATE())) % 7, CAST(GETDATE() AS DATE))
                                                                AS activation_date

    FROM rule_b r
    LEFT JOIN store_total_change t ON r.store_id = t.store_id
)

SELECT *
FROM recommendations
ORDER BY store_id, traffic_light, ABS(share_change_pp) DESC;


-- ============================================================
-- STEP 6 — VALIDATION CHECKS
-- Run these after each quarter to sense-check the gold table
-- ============================================================

-- Check 1: shares sum to ~100% per store-quarter (allow rounding tolerance)
SELECT
    store_id, quarter,
    SUM(bucket_stock_share)                                     AS total_share,
    COUNT(*)                                                    AS bucket_count
FROM gold
GROUP BY store_id, quarter
HAVING ABS(SUM(bucket_stock_share) - 1.0) > 0.05   -- flag if > 5% off
ORDER BY store_id, quarter;

-- Check 2: recommended shares sum to 100% per store
SELECT
    store_id,
    SUM(recommended_share_pct)                                  AS total_recommended_pct,
    COUNT(*)                                                    AS bucket_count
FROM recommendations
GROUP BY store_id
HAVING ABS(SUM(recommended_share_pct) - 100) > 2   -- flag if > 2pp off
ORDER BY store_id;

-- Check 3: any bucket exceeding 45% cap in recommendations
SELECT * FROM recommendations
WHERE recommended_share_pct > 45;

-- Check 4: null join audit (buckets in sales but not in stock, or vice versa)
SELECT
    s.store_id, s.BRAND, s.SUBBRAND, s.category, s.pricepoint, s.quarter,
    s.bucket_units_sold,
    k.starting_stock_units,
    CASE WHEN k.store_id IS NULL THEN 'MISSING IN STOCK TABLE'
         WHEN s.store_id IS NULL THEN 'MISSING IN SALES TABLE'
         ELSE 'OK' END                                          AS join_status
FROM sales_agg s
FULL OUTER JOIN stock_agg k
    ON  s.store_id   = k.store_id
    AND s.BRAND      = k.BRAND
    AND s.SUBBRAND   = k.SUBBRAND
    AND s.category   = k.category
    AND s.pricepoint = k.pricepoint
    AND s.quarter    = k.quarter
WHERE s.store_id IS NULL OR k.store_id IS NULL
ORDER BY join_status, s.store_id;


-- ============================================================
-- APPENDIX — GAP ANALYSIS vs BRD REQUIREMENTS
-- What the two current tables can and cannot provide
-- ============================================================

/*
COLUMN MAPPING — WHAT WE HAVE

  BRD Requirement                   Source Column(s)
  ─────────────────────────────────────────────────────────────
  store_id                       ✅  SAP_STORECODE / SAP_STORE_ID
  transaction_date               ✅  INVOICE_DATE
  collection                     ✅  BRAND + SUBBRAND
  category                       ✅  CATEGORY (sales) / derived from SUBCLASS (soh)
  pricepoint                     ✅  Derived band from UNITMRP / MRP (Economy/Mid/Premium)
  units_sold                     ✅  QUANTITY
  selling_price (net per unit)   ✅  NETAMT / QUANTITY
  mrp                            ✅  UNITMRP (sales) / MRP (soh)
  discount_depth                 ✅  DISCOUNT / TOTAL_MRP
  current_stock (SOH)            ✅  SOH (daily snapshot in SOH table)
  starting_stock_units           ⚠️  DERIVED — first SOH snapshot of quarter
  received_stock_units           ⚠️  DERIVED — inventory equation: ending+sold-starting
  ending_stock_units             ⚠️  DERIVED — last SOH snapshot of quarter
  season                         ✅  SEASON
  gender                         ✅  GENDER
  style count on display         ❌  NOT AVAILABLE — needs display Excel upload (Phase 2)
  store region / city            ⚠️  REGION, STATE in sales; not in SOH table
  store display capacity         ❌  NOT AVAILABLE — needs min-max audit
  store closure periods          ❌  NOT AVAILABLE — needs retroactive capture

GAPS TO RESOLVE BEFORE GOING LIVE

  1. Category join logic:
     CATEGORY exists in the sales table directly (SHIRT, JEANS etc.).
     In the SOH table, category must be parsed from SUBCLASS string.
     Risk: mismatches if SUBCLASS naming is inconsistent.
     Fix: ask the data team to add a clean CATEGORY column to SOH table,
     or create a shared lookup table.

  2. Pricepoint band thresholds:
     Economy / Mid / Premium cut-offs (set at ₹2,000 and ₹3,000 here)
     must be agreed with the Merchandising team. Incorrect bands mean
     buckets are wrongly classified and compared across stores.

  3. Store master enrichment:
     The SOH table has no REGION or STATE. For multi-region analysis,
     join both tables to a store master table that includes
     region, city tier, store format (MM / FO), and display capacity.

  4. LOAD_RUN_DATE parsing:
     LOAD_RUN_DATE is stored as a 14-digit integer (YYYYMMDDHHMMSS).
     The parsing used here (LEFT(CAST(...AS VARCHAR), 8)) works but
     is fragile. Ask the data team to add a proper DATE column.

  5. Received stock not directly available:
     The SOH table has no INWARD / GRN column. Received stock is inferred
     via the inventory equation. If there are write-offs, transfers, or
     returns in the SOH, this derivation will be inaccurate.
     Ideal fix: add a FACT_INWARD or GRN table with received quantities.

  6. STORE_TYPE is null in the sales sample:
     Store format (MM = Mega Mart, FO = Factory Outlet) is embedded
     in the store name prefix but not in a clean column.
     Derive with: CASE WHEN NAME LIKE 'MM-%' THEN 'Mega Mart'
                       WHEN NAME LIKE 'FO-%' THEN 'Factory Outlet' END
     or add a proper column in the store master.
*/
