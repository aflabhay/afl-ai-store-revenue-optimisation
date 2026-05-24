"""
size_break_monitor.py
---------------------
Daily job — monitors CORE style SOH across all Arrow stores.
Flags any style-size combination where SOH <= 2 units (size-break risk).
Triggers next-day warehouse replenishment request.

Runs daily (not just on Monday) — size breaks happen any day of the week.
Independent of the weekly IP solver cycle.

CORE styles are the pivotable sizes — the best-selling sizes in each category.
If these sell out, customers leave empty-handed.

NOTE: When implementing the Fabric version of this job, use FACT_FNO_BASE_SOH
(Opening_SOH, INVENTORY_DATE, STORE_CODE, STYLECODE, SIZE columns) instead of
the legacy FACT_FNO_SOH_DAILY table which has only 1 day of data.
"""

import pandas as pd
from datetime import date
from pathlib import Path

SIZE_BREAK_THRESHOLD = 2  # units — below this triggers replenishment


def check_size_breaks(
    soh_df: pd.DataFrame,
    snapshot_date: date = None,
    threshold: int = SIZE_BREAK_THRESHOLD,
) -> pd.DataFrame:
    """
    Identify CORE styles at size-break risk.

    Parameters
    ----------
    soh_df : pd.DataFrame
        Daily SOH data from FACT_FNO_SOH_DAILY
    snapshot_date : date
        Date to check. Defaults to today.
    threshold : int
        SOH units at or below which a size-break risk is flagged.

    Returns
    -------
    pd.DataFrame of flagged style-sizes with replenishment priority.
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    soh = soh_df.copy()
    soh["LOAD_RUN_DATE"] = pd.to_datetime(soh["LOAD_RUN_DATE"]).dt.date

    # Filter to today's snapshot, CORE styles, Q1 only, no holds
    today_soh = soh[
        (soh["LOAD_RUN_DATE"] == snapshot_date)
        & (soh["FASHION"] == "CORE")
        & (soh["QUALITY"] == "Q1")
        & (soh["ON_HOLD"].fillna(0) == 0)
    ].copy()

    if today_soh.empty:
        # Fallback: use most recent available date
        latest = soh[soh["FASHION"] == "CORE"]["LOAD_RUN_DATE"].max()
        today_soh = soh[
            (soh["LOAD_RUN_DATE"] == latest)
            & (soh["FASHION"] == "CORE")
            & (soh["QUALITY"] == "Q1")
            & (soh["ON_HOLD"].fillna(0) == 0)
        ].copy()

    flagged = today_soh[today_soh["SOH"] <= threshold].copy()

    flagged["replenishment_priority"] = flagged["SOH"].apply(
        lambda s: "URGENT — zero stock, replenish today" if s == 0
        else "HIGH — replenish next day"
    )

    flagged["snapshot_date"] = snapshot_date.isoformat()

    return flagged[[
        "SAP_STORE_ID", "STORE_NAME", "STYLE_CODE", "CLASS",
        "SIZE", "COLOR_DESCRIPTION", "SEASON", "SOH",
        "replenishment_priority", "snapshot_date",
    ]].rename(columns={
        "SAP_STORE_ID": "store_id",
        "STORE_NAME":   "store_name",
        "STYLE_CODE":   "style_code",
        "CLASS":        "category",
        "SIZE":         "size",
        "COLOR_DESCRIPTION": "colour",
    }).sort_values(["store_id", "replenishment_priority", "SOH"])


if __name__ == "__main__":
    data_dir = Path(__file__).parents[2] / "data" / "raw"
    soh_df   = pd.read_csv(data_dir / "soh_sample.csv")

    flags = check_size_breaks(soh_df)

    if flags.empty:
        print("No size-break risks detected today.")
    else:
        print(f"\n⚠  {len(flags)} size-break risks detected:\n")
        print(flags.to_string(index=False))

        out = Path(__file__).parents[2] / "data" / "processed" / f"size_breaks_{date.today()}.csv"
        flags.to_csv(out, index=False)
        print(f"\nSaved to: {out}")
