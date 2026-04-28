# Data Directory

All files in `raw/` are **dummy/sample data** for local development. They simulate the schema of the Microsoft Fabric Data Warehouse tables without containing any real Arvind Fashions data.

---

## raw/sales_sample.csv
Simulates `[prd].[FACT_FNO_SALES_TC_ONLINE_BASE]`

| Column | Type | Description |
|---|---|---|
| SAP_STORECODE | int | Store identifier — matches store_capacity.csv |
| NAME | str | Store display name (e.g. "MG Road\|BLR") |
| REGION | str | Region code (KAR, TN, MH, NCR, MUM) |
| STATE | str | State |
| BRAND | str | Always "Arrow" in Phase 1 |
| SUBBRAND | str | Arrow sub-brand |
| CATEGORY | str | Product category (FORMAL SHIRTS, CHINOS, etc.) |
| SUBCLASS | str | Sub-category detail |
| STYLECODE | str | Unique style identifier |
| ITEM_ID | str | SKU identifier (style + size + colour) |
| ITEMSIZE | str | Size (S, M, L, XL, XXL, 28, 30, 32 etc.) |
| COLOR | str | Colour description |
| SEASON | str | Season code (AW24, SS25 etc.) |
| GENDER | str | M / F / U |
| QUALITY | str | Q1 (first quality), Q2 (seconds) |
| INVOICE_DATE | date | Transaction date |
| QUANTITY | int | Units sold (positive = sale, negative = return) |
| UNITMRP | float | MRP per unit in ₹ |
| NETAMT | float | Net selling price after discount |
| DISCOUNT | float | Discount amount in ₹ |
| TOTAL_MRP | float | QUANTITY × UNITMRP |
| INVOICETYPE | str | SALES / RETURN / EXCHANGE |
| FASHION | str | CORE / FASHION (CORE = pivotable sizes) |

**Priceband derivation (applied in code, not stored):**
- Economy: UNITMRP ≤ ₹1,999
- Mid: ₹2,000 – ₹2,999
- Premium: ₹3,000+

---

## raw/soh_sample.csv
Simulates `[prd].[FACT_FNO_SOH_DAILY]`

| Column | Type | Description |
|---|---|---|
| SAP_STORE_ID | int | Store identifier |
| STORE_NAME | str | Store display name |
| BRAND | str | Always "Arrow" in Phase 1 |
| SUBBRAND | str | Arrow sub-brand |
| CLASS | str | Product class |
| SUBCLASS | str | Sub-category |
| STYLE_CODE | str | Unique style identifier |
| ITEM_ID | str | SKU identifier |
| SIZE | str | Size |
| FASHION | str | CORE / FASHION |
| COLOR_DESCRIPTION | str | Colour |
| SEASON | str | Season code |
| GENDER | str | M / F / U |
| MRP | float | MRP per unit in ₹ |
| SOH | int | Stock on hand units at snapshot date |
| ON_HOLD | int | Units on hold (not available for sale) |
| QUALITY | str | Q1 / Q2 |
| LOAD_RUN_DATE | date | Snapshot date — filter to Monday for model input |

**Key Monday SOH query:**
```sql
SELECT SAP_STORE_ID, STYLE_CODE, ITEM_ID, SIZE, FASHION, SOH
FROM [prd].[FACT_FNO_SOH_DAILY]
WHERE LOAD_RUN_DATE = CAST(GETDATE() AS DATE)  -- Monday morning
  AND BRAND LIKE 'Arrow%'
  AND QUALITY = 'Q1'
  AND ISNULL(ON_HOLD, 0) = 0
```

---

## raw/store_capacity.csv
Store display capacity from VM team Excel (Min Option Count)

| Column | Type | Description |
|---|---|---|
| STORE_CODE | int | SAP store code — joins to SAP_STORECODE in sales table |
| REGION | str | Region code |
| STORE_NAME | str | Store display name |
| SALES_AREA | int | Store floor area in sq ft |
| MIN_OPTION_COUNT | int | **display_capacity[store]** — Monday display target (~65% scenario) |
| MAX_OPTION_COUNT | int | All-inventory-out scenario — NOT used in the model |

**Note:** Only `MIN_OPTION_COUNT` is used in the IP model (constraint C5). `MAX_OPTION_COUNT` represents the 100% inventory-out scenario and is excluded.

---

## processed/revenue_rates_sample.csv
Pre-computed rolling 4-week revenue rates — output of `src/data_pipeline/revenue_rate_builder.py`

| Column | Type | Description |
|---|---|---|
| store_id | int | SAP store code |
| category | str | Product category |
| priceband | str | Economy / Mid / Premium |
| bucket_key | str | CATEGORY \| priceband |
| bucket_revenue_4w | float | Total revenue ₹ last 4 weeks |
| bucket_inventory_4w | float | Average weekly SOH last 4 weeks |
| revenue_rate | float | bucket_revenue_4w / bucket_inventory_4w |
| weeks_of_data | int | Actual weeks with sales data (may be < 4 for new arrivals) |
| is_seeded | bool | True if rate seeded from category average (< 2 weeks data) |
| computed_date | date | Date rate was computed (should be Sunday) |
