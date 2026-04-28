"""
revenue_rate_builder.py
-----------------------
Computes rolling 4-week revenue rates per store × bucket (Category × Priceband).
This is the primary input to the IP solver.

Runs every Sunday night via a scheduled job (Azure Function or Fabric notebook).
In local/dev mode, reads from dummy CSV files instead of Fabric.
"""

import pandas as pd
import numpy as np
from datetime import date, timedelta
from pathlib import Path

# ── Priceband thresholds (review quarterly with Merchandising) ──────────────
PRICEBAND_THRESHOLDS = {
    "Economy": (0, 1999),
    "Mid":     (2000, 2999),
    "Premium": (3000, float("inf")),
}

def assign_priceband(mrp: float) -> str:
    for band, (low, high) in PRICEBAND_THRESHOLDS.items():
        if low <= mrp <= high:
            return band
    return "Premium"


def compute_revenue_rates(
    sales_df: pd.DataFrame,
    soh_df: pd.DataFrame,
    as_of_date: date = None,
    window_weeks: int = 4,
    min_weeks_threshold: int = 2,
) -> pd.DataFrame:
    """
    Compute revenue_rate[store, bucket] = bucket_revenue / bucket_inventory
    over a rolling window_weeks window ending on as_of_date.

    Parameters
    ----------
    sales_df : pd.DataFrame
        Sales transactions — must contain SAP_STORECODE, CATEGORY, UNITMRP,
        INVOICE_DATE, QUANTITY, NETAMT, INVOICETYPE, QUALITY columns.
    soh_df : pd.DataFrame
        Daily SOH snapshots — must contain SAP_STORE_ID, CLASS (category),
        MRP, SOH, LOAD_RUN_DATE, QUALITY, ON_HOLD columns.
    as_of_date : date
        The Sunday the solver runs. Defaults to today.
    window_weeks : int
        Number of weeks to look back for rate computation. Default 4.
    min_weeks_threshold : int
        If a bucket has fewer weeks of data than this, seed from category average.

    Returns
    -------
    pd.DataFrame with columns:
        store_id, category, priceband, bucket_key,
        bucket_revenue_4w, bucket_inventory_4w, revenue_rate,
        weeks_of_data, is_seeded, computed_date
    """
    if as_of_date is None:
        as_of_date = date.today()

    window_start = as_of_date - timedelta(weeks=window_weeks)

    # ── Sales: filter to window, Arrow only, valid sales ───────────────────
    sales = sales_df.copy()
    sales["INVOICE_DATE"] = pd.to_datetime(sales["INVOICE_DATE"]).dt.date
    sales = sales[
        (sales["INVOICETYPE"] == "SALES")
        & (sales["QUANTITY"] > 0)
        & (sales["NETAMT"] > 0)
        & (sales["QUALITY"] == "Q1")
        & (sales["INVOICE_DATE"] >= window_start)
        & (sales["INVOICE_DATE"] <= as_of_date)
    ].copy()

    sales["priceband"] = sales["UNITMRP"].apply(assign_priceband)
    sales["bucket_key"] = sales["CATEGORY"] + " | " + sales["priceband"]
    sales["week"] = pd.to_datetime(sales["INVOICE_DATE"]).dt.isocalendar().week

    # Aggregate revenue per store-bucket
    bucket_revenue = (
        sales.groupby(["SAP_STORECODE", "CATEGORY", "priceband", "bucket_key"])
        .agg(
            bucket_revenue_4w=("NETAMT", "sum"),
            weeks_of_data=("week", "nunique"),
        )
        .reset_index()
        .rename(columns={"SAP_STORECODE": "store_id"})
    )

    # ── SOH: average weekly SOH per store-bucket in window ─────────────────
    soh = soh_df.copy()
    soh["LOAD_RUN_DATE"] = pd.to_datetime(soh["LOAD_RUN_DATE"]).dt.date
    soh = soh[
        (soh["QUALITY"] == "Q1")
        & (soh["ON_HOLD"].fillna(0) == 0)
        & (soh["LOAD_RUN_DATE"] >= window_start)
        & (soh["LOAD_RUN_DATE"] <= as_of_date)
    ].copy()

    soh["priceband"] = soh["MRP"].apply(assign_priceband)
    soh["bucket_key"] = soh["CLASS"] + " | " + soh["priceband"]

    bucket_inventory = (
        soh.groupby(["SAP_STORE_ID", "CLASS", "priceband", "bucket_key"])
        .agg(bucket_inventory_4w=("SOH", "mean"))
        .reset_index()
        .rename(columns={"SAP_STORE_ID": "store_id", "CLASS": "CATEGORY"})
    )

    # ── Join and compute rate ───────────────────────────────────────────────
    rates = pd.merge(
        bucket_revenue,
        bucket_inventory,
        on=["store_id", "CATEGORY", "priceband", "bucket_key"],
        how="outer",
    ).fillna(0)

    rates["revenue_rate"] = np.where(
        rates["bucket_inventory_4w"] > 0,
        rates["bucket_revenue_4w"] / rates["bucket_inventory_4w"],
        0,
    )

    # ── Seed thin buckets from category average across comparable stores ────
    category_avg = (
        rates[rates["weeks_of_data"] >= min_weeks_threshold]
        .groupby(["CATEGORY", "priceband"])["revenue_rate"]
        .mean()
        .reset_index()
        .rename(columns={"revenue_rate": "category_avg_rate"})
    )

    rates = pd.merge(rates, category_avg, on=["CATEGORY", "priceband"], how="left")
    rates["is_seeded"] = rates["weeks_of_data"] < min_weeks_threshold
    rates["revenue_rate"] = np.where(
        rates["is_seeded"],
        rates["category_avg_rate"].fillna(0),
        rates["revenue_rate"],
    )
    rates["computed_date"] = as_of_date.isoformat()

    return rates[
        [
            "store_id", "CATEGORY", "priceband", "bucket_key",
            "bucket_revenue_4w", "bucket_inventory_4w", "revenue_rate",
            "weeks_of_data", "is_seeded", "computed_date",
        ]
    ].rename(columns={"CATEGORY": "category"})


def load_dummy_data(data_dir: Path = None) -> tuple:
    """Load dummy CSV data for local development."""
    if data_dir is None:
        data_dir = Path(__file__).parents[2] / "data" / "raw"

    sales_df = pd.read_csv(data_dir / "sales_sample.csv")
    soh_df   = pd.read_csv(data_dir / "soh_sample.csv")
    return sales_df, soh_df


if __name__ == "__main__":
    print("Running revenue rate builder on dummy data...")
    sales_df, soh_df = load_dummy_data()
    rates = compute_revenue_rates(sales_df, soh_df, as_of_date=date(2026, 4, 14))

    output_path = Path(__file__).parents[2] / "data" / "processed" / "revenue_rates_sample.csv"
    rates.to_csv(output_path, index=False)

    print(f"\nRevenue rates computed: {len(rates)} store-bucket combinations")
    print(f"Seeded buckets (thin data): {rates['is_seeded'].sum()}")
    print(f"\nSample output:")
    print(rates.head(10).to_string(index=False))
