"""
run_solver.py
-------------
Batch runner — solves the IP model for all stores and writes output.
Runs every Sunday night before Monday rearrangement.

Usage:
    python src/solver/run_solver.py --store all
    python src/solver/run_solver.py --store 8194

Requires:
    data/processed/eda_data_YYYY-MM-DD.csv
    Generate with: python src/data_pipeline/fabric_connector.py
"""

import argparse
import json
import sys
import pandas as pd
from datetime import date
from pathlib import Path

# Ensure project root is on sys.path so `src.*` imports work when running
# directly as `python src/solver/run_solver.py` (without PYTHONPATH=.)
sys.path.insert(0, str(Path(__file__).parents[2]))

from src.solver.ip_model import solve_store, format_output_table, SolverConfig


DATA_DIR    = Path(__file__).parents[2] / "data"
OUTPUT_DIR  = DATA_DIR / "processed"


def run_all_stores(
    rates_df: pd.DataFrame,
    capacity_df: pd.DataFrame,
    store_filter: str = "all",
    config: SolverConfig = None,
) -> list:
    """Run solver across all stores and return list of results."""
    if config is None:
        config = SolverConfig()

    results = []
    store_ids = rates_df["store_id"].unique()

    if store_filter != "all":
        store_ids = [int(store_filter)]

    for store_id in store_ids:
        # Get display capacity for this store
        cap_row = capacity_df[capacity_df["STORE_CODE"] == store_id]
        if cap_row.empty:
            print(f"  ⚠  Store {store_id}: no capacity data — skipping")
            continue

        display_capacity = int(cap_row["MIN_OPTION_COUNT"].values[0])

        # Get buckets for this store with positive revenue rates
        store_rates = rates_df[
            (rates_df["store_id"] == store_id) &
            (rates_df["revenue_rate"] > 0)
        ].copy()

        if store_rates.empty:
            print(f"  ⚠  Store {store_id}: no revenue rate data — skipping")
            continue

        # C6: only existing buckets (already enforced by filtering revenue_rate > 0)
        # Pass style_count_in_bucket and avg_sizes_per_style for C7 hanger cap
        bucket_cols = ["bucket_key", "revenue_rate"]
        if "style_count_in_bucket" in store_rates.columns:
            bucket_cols.append("style_count_in_bucket")
        if "avg_sizes_per_style" in store_rates.columns:
            bucket_cols.append("avg_sizes_per_style")

        result = solve_store(
            store_id=store_id,
            buckets=store_rates[bucket_cols],
            display_capacity=display_capacity,
            config=config,
        )

        status_icon = "✓" if result["status"] == "OPTIMAL" else "✗"
        print(
            f"  {status_icon}  Store {store_id:>5} | "
            f"{len(store_rates):>2} buckets | "
            f"capacity {display_capacity:>3} styles (~{display_capacity * 5} hangers) | "
            f"status: {result['status']}"
        )

        results.append(result)

    return results


def main():
    _DEFAULT_OPTION_COUNT = 400   # fallback for stores not yet in store_capacity_real.csv

    parser = argparse.ArgumentParser(description="Run IP solver for store allocation")
    parser.add_argument("--store", default="all", help="Store code or 'all'")
    parser.add_argument("--date",  default=None,  help="YYYY-MM-DD (defaults to today)")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.date) if args.date else date.today()

    print(f"\n{'='*60}")
    print(f"  Arvind Fashions — Store Allocation Solver")
    print(f"  As-of date  : {as_of}")
    print(f"  Store filter: {args.store}")
    print(f"{'='*60}\n")

    # ── Load EDA dataset ─────────────────────────────────────────────────
    eda_files = sorted(OUTPUT_DIR.glob("eda_data_*.csv"), reverse=True)
    if not eda_files:
        raise FileNotFoundError(
            "No eda_data_*.csv found in data/processed/.\n"
            "Run first: python src/data_pipeline/fabric_connector.py"
        )
    print(f"Loading EDA dataset: {eda_files[0].name}")
    eda_df = pd.read_csv(eda_files[0])

    valid_mask = eda_df["revenue_rate"].notna() & (eda_df["revenue_rate"] > 0)
    print(f"  Revenue rate coverage: {valid_mask.sum()} valid / {len(eda_df)} total buckets")
    print(f"  Stores with >=1 valid rate: {eda_df[valid_mask]['store_id'].nunique()}\n")

    rate_cols = ["store_id", "bucket_key", "revenue_rate"]
    if "style_count_in_bucket" in eda_df.columns:
        rate_cols.append("style_count_in_bucket")
    if "avg_sizes_per_style" in eda_df.columns:
        rate_cols.append("avg_sizes_per_style")

    rates_df = (
        eda_df[rate_cols]
        .dropna(subset=["revenue_rate"])
        .drop_duplicates()
    )
    print(f"  {len(rates_df)} store-bucket rates loaded\n")

    if rates_df.empty:
        raise ValueError(
            "All revenue_rate values are NULL in the EDA file.\n"
            "Re-run: python src/data_pipeline/fabric_connector.py"
        )

    # ── Build store capacity ──────────────────────────────────────────────
    # Use existing store_capacity_real.csv for MIN_OPTION_COUNT if available,
    # otherwise default to _DEFAULT_OPTION_COUNT for all stores.
    real_cap_path = OUTPUT_DIR / "store_capacity_real.csv"
    eda_store_cols = ["store_id", "store_name"] + (
        ["REGION"] if "REGION" in eda_df.columns else []
    )
    eda_stores = eda_df[eda_store_cols].drop_duplicates()

    if real_cap_path.exists():
        existing_cap = pd.read_csv(real_cap_path)[["STORE_CODE", "MIN_OPTION_COUNT"]]
        capacity_df = pd.merge(
            eda_stores,
            existing_cap,
            left_on="store_id", right_on="STORE_CODE", how="left",
        )
    else:
        capacity_df = eda_stores.copy()
        capacity_df["STORE_CODE"] = capacity_df["store_id"]
        capacity_df["MIN_OPTION_COUNT"] = float("nan")

    capacity_df["MIN_OPTION_COUNT"] = (
        capacity_df["MIN_OPTION_COUNT"].fillna(_DEFAULT_OPTION_COUNT).astype(int)
    )
    capacity_df["STORE_CODE"] = capacity_df["store_id"]
    capacity_df["STORE_NAME"] = capacity_df["store_name"]

    # Persist so Streamlit app reads it automatically
    cap_out_cols = ["STORE_CODE", "STORE_NAME", "MIN_OPTION_COUNT"] + (
        ["REGION"] if "REGION" in capacity_df.columns else []
    )
    capacity_df[cap_out_cols].to_csv(real_cap_path, index=False)
    print(f"  Store capacity saved: {real_cap_path}\n")

    # ── Run solver ────────────────────────────────────────────────────────
    print("Running IP solver...\n")
    config = SolverConfig()
    results = run_all_stores(rates_df, capacity_df, args.store, config)

    # ── Save outputs ─────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Flat table for Streamlit / export
    flat_rows = []
    for r in results:
        if r["status"] == "OPTIMAL":
            df = format_output_table(r)
            flat_rows.append(df)

    if flat_rows:
        output_df = pd.concat(flat_rows, ignore_index=True)
        out_path = OUTPUT_DIR / f"recommendations_{as_of.isoformat()}.csv"
        output_df.to_csv(out_path, index=False)
        print(f"\nRecommendations saved to: {out_path}")
        print(f"Total store-bucket recommendations: {len(output_df)}")

    # JSON for full result with metadata
    json_path = OUTPUT_DIR / f"solver_results_{as_of.isoformat()}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=lambda o: int(o) if hasattr(o, 'item') else str(o))
    print(f"Full solver results saved to: {json_path}")

    # Summary
    optimal = sum(1 for r in results if r["status"] == "OPTIMAL")
    issues  = sum(1 for r in results if r["status"] != "OPTIMAL")
    print(f"\nSummary: {optimal} stores solved optimally, {issues} issues")


if __name__ == "__main__":
    main()
