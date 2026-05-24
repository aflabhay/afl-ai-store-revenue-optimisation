"""
ip_model.py
-----------
Core Integer Programming model for store display allocation.

Objective:  Maximise  SUM [ display_share[bucket] × revenue_rate[bucket] ]
Constraints C1–C6 as defined in BRD v2.0.

Uses PuLP as the solver backend (open source, no licence required).
Each store is solved independently — parallelisable across 1,000+ stores.

Dynamic Floor Logic
-------------------
Pure linear objectives produce "bang-bang" allocations: the solver pushes all
free budget to the highest-rate bucket first (up to the 45% cap), then the
next, regardless of how close the rates are.

floor_weight controls how proportional the minimum floors are:
  0.0  → uniform 1% floor for all buckets  (previous behaviour, bang-bang)
  0.5  → each bucket guaranteed ≥50% of its proportional fair share
  1.0  → fully proportional (no free optimisation budget)

With floor_weight=0.50 the solver still maximises revenue with the remaining
~50% of budget, but the base allocation is proportional to revenue rates.
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd
import pulp


# ── Model configuration ─────────────────────────────────────────────────────

@dataclass
class SolverConfig:
    min_share: int = 1          # C4 — absolute floor (%)
    max_share: int = 45         # C3 — absolute cap (%)
    total_share: int = 100      # C1 — must sum to exactly this
    solver_timeout: int = 60    # seconds before solver gives up
    floor_weight: float = 0.50  # 0 = uniform 1% floor, 1 = fully proportional
    cap_multiplier: float = 1.5 # each bucket capped at this × its proportional share
    #
    # floor_weight and cap_multiplier work as a band around each bucket's fair share:
    #   floor = proportional_share × floor_weight   (guaranteed minimum)
    #   cap   = proportional_share × cap_multiplier (maximum allowed)
    #
    # Example with proportional_share=20%, floor_weight=0.5, cap_multiplier=1.5:
    #   floor = 10%,  cap = 30%
    # The solver allocates the free budget within [10%, 30%] for each bucket,
    # forcing it to spread across multiple buckets rather than pile into the top one.


# ── Main solver function ─────────────────────────────────────────────────────

def solve_store(
    store_id: int,
    buckets: pd.DataFrame,
    display_capacity: int,
    config: SolverConfig = None,
) -> dict:
    """
    Solve the display allocation IP for a single store.

    Parameters
    ----------
    store_id : int
        SAP store code.
    buckets : pd.DataFrame
        One row per active bucket. Required columns:
            bucket_key (str), revenue_rate (float)
        Optional column:
            style_count_in_bucket (int) — distinct styles with SOH in this bucket.
            When present, the solver caps each bucket's style slots at available
            SOH styles so recommendations are physically fulfillable.
    display_capacity : int
        MIN_OPTION_COUNT for this store — from store capacity Excel.
    config : SolverConfig
        Solver parameters. Uses defaults if not provided.

    Returns
    -------
    dict with keys:
        store_id, status, buckets (list of dicts with display_share),
        total_expected_revenue_index, style_slots_used, message
    """
    if config is None:
        config = SolverConfig()

    n_buckets = len(buckets)

    # ── Guard: bucket count meaningfulness check ─────────────────────────
    # If n_buckets × min_floor = 100 the solver has no room to differentiate.
    if n_buckets * config.min_share >= config.total_share:
        return {
            "store_id": store_id,
            "status": "INFEASIBLE_FLOOR_BINDS",
            "buckets": [],
            "total_expected_revenue_index": 0,
            "style_slots_used": 0,
            "message": (
                f"Store {store_id} has {n_buckets} active buckets. "
                f"Floor constraint ({config.min_share}% × {n_buckets} = "
                f"{config.min_share * n_buckets}%) consumes all available share. "
                f"Coarsen bucket definition (drop Priceband, use Category only)."
            ),
        }

    bucket_keys  = buckets["bucket_key"].tolist()
    rates        = dict(zip(buckets["bucket_key"], buckets["revenue_rate"]))

    # C7 — SOH style cap: max style slots this bucket can physically fill.
    # style_count_in_bucket = count of styles with Opening_SOH > 0 (from FACT_FNO_BASE_SOH).
    # Only styles with actual stock can occupy display slots — zero-SOH styles excluded.
    # cap_pct = style_count / display_capacity * 100, floored at 1%.
    # Falls back to global max_share when column is absent (no SOH data).
    if "style_count_in_bucket" in buckets.columns:
        soh_style_cap_pct = {
            row.bucket_key: max(
                1,  # always allow at least 1%
                int(row.style_count_in_bucket / display_capacity * 100),
            )
            for row in buckets.itertuples()
        }
    else:
        soh_style_cap_pct = {b: config.max_share for b in bucket_keys}

    # ── Dynamic proportional floors ──────────────────────────────────────
    # Each bucket is guaranteed at least (floor_weight × its proportional
    # fair share) of total display. The remaining free budget is allocated
    # by the optimiser. This prevents bang-bang concentration when rates
    # are close to each other.
    total_rate = sum(rates.values())
    if total_rate > 0 and config.floor_weight > 0:
        dynamic_floors = {
            b: max(
                config.min_share,
                round(rates[b] / total_rate * config.total_share * config.floor_weight),
            )
            for b in bucket_keys
        }
    else:
        dynamic_floors = {b: config.min_share for b in bucket_keys}

    # If dynamic floors consume all available share (edge case with many
    # buckets and high floor_weight) fall back to uniform floor.
    if sum(dynamic_floors.values()) >= config.total_share:
        dynamic_floors = {b: config.min_share for b in bucket_keys}

    # ── Dynamic proportional caps ─────────────────────────────────────────
    # Each bucket is capped at (cap_multiplier × its proportional fair share).
    # This prevents all free budget piling into the top 1-2 buckets:
    # once a top bucket hits its cap the solver is forced to spread remaining
    # free budget to the next-highest-rate bucket, and so on.
    #
    # Example: proportional_share=20%, cap_multiplier=1.5 → cap=30%
    # The solver can give this bucket at most 30%, not 45%, so more budget
    # flows to buckets 3, 4, 5 which may have similar revenue rates.
    if total_rate > 0 and config.cap_multiplier > 0:
        dynamic_caps = {
            b: min(
                config.max_share,
                soh_style_cap_pct[b],   # C7: never exceed available SOH styles
                max(
                    dynamic_floors[b],  # cap must always be ≥ floor
                    round(rates[b] / total_rate * config.total_share * config.cap_multiplier),
                ),
            )
            for b in bucket_keys
        }
    else:
        dynamic_caps = {b: min(config.max_share, soh_style_cap_pct[b]) for b in bucket_keys}

    # Guard: total cap must cover total_share or the LP is infeasible.
    if sum(dynamic_caps.values()) < config.total_share:
        dynamic_caps = {b: config.max_share for b in bucket_keys}

    # ── Build the LP problem ─────────────────────────────────────────────
    prob = pulp.LpProblem(f"store_{store_id}_allocation", pulp.LpMaximize)

    # Decision variables: per-bucket bounds — floor from proportional floors,
    # cap from proportional caps. Both computed above.
    x = {
        b: pulp.LpVariable(
            f"ds_{idx}",
            lowBound=dynamic_floors[b],  # C4 — proportional floor
            upBound=dynamic_caps[b],     # C3 — proportional cap (replaces global 45%)
            cat="Integer",               # C2
        )
        for idx, b in enumerate(bucket_keys)
    }

    # ── Objective function ───────────────────────────────────────────────
    # Maximise: SUM [ display_share[b] × revenue_rate[b] ]
    # Note: display_capacity is a constant per store — excluded from objective
    # as it does not affect which allocation the solver picks (see BRD §2.2)
    prob += pulp.lpSum([x[b] * rates[b] for b in bucket_keys]), "total_revenue_index"

    # ── C1: Display shares must sum to exactly 100% ──────────────────────
    prob += pulp.lpSum([x[b] for b in bucket_keys]) == config.total_share, "C1_sum_to_100"

    # ── C5: Style count must not exceed display capacity ─────────────────
    # ROUND(display_share/100 × display_capacity) ≤ display_capacity
    # Approximated as a linear constraint (rounding handled in output):
    prob += (
        pulp.lpSum([x[b] for b in bucket_keys]) / 100.0 * display_capacity
        <= display_capacity
    ), "C5_display_capacity"
    # Note: C5 is always satisfied given C1 (shares = 100%), but included
    # explicitly for future per-bucket capacity extension (Phase 1.5)

    # ── C6: Only existing buckets (enforced by input — no zero-rate buckets)
    # Buckets with no sales history are excluded from the buckets DataFrame
    # before calling this function (handled in run_solver.py)

    # ── Solve ────────────────────────────────────────────────────────────
    # Prefer HiGHS (arm64-native, works on Mac Apple Silicon + Ubuntu).
    # Fall back to bundled CBC (works on Ubuntu x86_64 and any platform
    # where the bundled binary matches the OS architecture).
    available = pulp.listSolvers(onlyAvailable=True)
    if "HiGHS" in available:
        solver = pulp.HiGHS(msg=0, timeLimit=config.solver_timeout)
    elif "HiGHS_CMD" in available:
        solver = pulp.HiGHS_CMD(msg=0, timeLimit=config.solver_timeout)
    else:
        solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=config.solver_timeout)
    prob.solve(solver)

    status = pulp.LpStatus[prob.status]

    if prob.status != 1:  # 1 = Optimal
        return {
            "store_id": store_id,
            "status": status,
            "buckets": [],
            "total_expected_revenue_index": 0,
            "style_slots_used": 0,
            "message": f"Solver did not find optimal solution. Status: {status}",
        }

    # ── Extract results ──────────────────────────────────────────────────
    results = []
    total_rev_index = 0

    for b in bucket_keys:
        share = int(round(pulp.value(x[b])))
        rate  = rates[b]
        floor = dynamic_floors[b]
        style_slots = int(share / 100 * display_capacity)  # floor to never exceed capacity
        rev_index   = share * rate

        cap = dynamic_caps[b]
        results.append({
            "bucket_key":          b,
            "display_share_pct":   share,
            "revenue_rate":        round(rate, 2),
            "floor_share":         floor,  # proportional floor (guaranteed minimum)
            "cap_share":           cap,    # proportional cap (maximum allowed)
            "style_slots":         style_slots,
            "expected_rev_index":  round(rev_index, 2),
            # INCREASE = hit its proportional cap (solver maxed this bucket out)
            # HOLD     = above floor, below cap (partial free budget allocated)
            # REDUCE   = at its proportional floor (no free budget allocated)
            "signal": (
                "INCREASE" if share >= cap else
                "REDUCE"   if share <= floor else
                "HOLD"
            ),
        })
        total_rev_index += rev_index

    style_slots_used = sum(r["style_slots"] for r in results)

    # Validation assertions — should never fail
    assert sum(r["display_share_pct"] for r in results) == config.total_share, "C1 violated"
    assert all(
        config.min_share <= r["display_share_pct"] <= r["cap_share"]
        for r in results
    ), "C3/C4 violated"
    assert style_slots_used <= display_capacity, "C5 violated"

    return {
        "store_id":                    store_id,
        "status":                      "OPTIMAL",
        "buckets":                     results,
        "total_expected_revenue_index": round(total_rev_index, 2),
        "style_slots_used":            style_slots_used,
        "display_capacity":            display_capacity,
        "message":                     "OK",
    }


def format_output_table(solver_result: dict) -> pd.DataFrame:
    """Convert solver result dict to a flat DataFrame for Streamlit / export."""
    if not solver_result["buckets"]:
        return pd.DataFrame()

    rows = []
    for b in solver_result["buckets"]:
        rows.append({
            "store_id":           solver_result["store_id"],
            "bucket_key":         b["bucket_key"],
            "display_share_pct":  b["display_share_pct"],
            "floor_share":        b["floor_share"],
            "cap_share":          b["cap_share"],
            "revenue_rate":       b["revenue_rate"],
            "style_slots":        b["style_slots"],
            "expected_rev_index": b["expected_rev_index"],
            "signal":             b["signal"],
        })

    return pd.DataFrame(rows).sort_values("display_share_pct", ascending=False)
