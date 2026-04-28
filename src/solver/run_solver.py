"""
run_solver.py
-------------
Batch runner — solves the IP model for all stores and writes output.
Runs every Sunday night before Monday rearrangement.

Usage:
    python src/solver/run_solver.py --data dummy --store all
    python src/solver/run_solver.py --data dummy --store 8194
    python src/solver/run_solver.py --data fabric --store all   # requires .env
"""

import argparse
import json
import pandas as pd
from datetime import date
from pathlib import Path

from src.data_pipeline.revenue_rate_builder import load_dummy_data, compute_revenue_rates
from src.solver.ip_model import solve_store, format_output_table, SolverConfig


DATA_DIR    = Path(__file__).parents[2] / "data"
OUTPUT_DIR  = DATA_DIR / "processed"


def load_store_capacity(data_dir: Path) -> pd.DataFrame:
    return pd.read_csv(data_dir / "raw" / "store_capacity.csv")


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
        result = solve_store(
            store_id=store_id,
            buckets=store_rates[["bucket_key", "revenue_rate"]],
            display_capacity=display_capacity,
            config=config,
        )

        status_icon = "✓" if result["status"] == "OPTIMAL" else "✗"
        print(
            f"  {status_icon}  Store {store_id:>5} | "
            f"{len(store_rates):>2} buckets | "
            f"capacity {display_capacity:>3} styles | "
            f"status: {result['status']}"
        )

        results.append(result)

    return results


def main():
    parser = argparse.ArgumentParser(description="Run IP solver for store allocation")
    parser.add_argument("--data",  default="dummy", choices=["dummy", "fabric"])
    parser.add_argument("--store", default="all", help="Store code or 'all'")
    parser.add_argument("--date",  default=None,  help="YYYY-MM-DD (defaults to today)")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.date) if args.date else date.today()

    print(f"\n{'='*60}")
    print(f"  Arvind Fashions — Store Allocation Solver")
    print(f"  As-of date : {as_of}")
    print(f"  Data source: {args.data}")
    print(f"  Store filter: {args.store}")
    print(f"{'='*60}\n")

    # ── Load data ────────────────────────────────────────────────────────
    if args.data == "dummy":
        print("Loading dummy data...")
        sales_df, soh_df = load_dummy_data(DATA_DIR / "raw")
    else:
        raise NotImplementedError(
            "Fabric connector not configured. Add FABRIC_CONNECTION_STRING to .env"
        )

    # ── Compute revenue rates ─────────────────────────────────────────────
    print("Computing rolling 4-week revenue rates...")
    rates_df = compute_revenue_rates(sales_df, soh_df, as_of_date=as_of)
    print(f"  {len(rates_df)} store-bucket rates computed\n")

    # ── Load store capacity ───────────────────────────────────────────────
    capacity_df = load_store_capacity(DATA_DIR)

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
