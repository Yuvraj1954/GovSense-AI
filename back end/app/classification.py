"""
Deterministic entity performance classification for MPLADS.

200-point performance matrix:
  performance_score = completion_rate_pct + fund_utilization_pct
  Max score = 200.

Classification bands:
  160–200    → PERFORMER
  120–159.99 → AVERAGE
  80–119.99  → NEEDS_ATTENTION
  0–79.99    → UNDERPERFORMER

Data quality labels:
  NO_DATA            → zero works or zero_work_member flag
  INSUFFICIENT_DATA  → low_sample_member flag or total_works < 5

Reads from DB2 (member_metrics, state_metrics).
Writes to DB2 (same tables).
"""

import asyncpg


# ── Thresholds ──────────────────────────────────────────────────────────────
PERFORMER_MIN = 160.0
AVERAGE_MIN = 120.0
NEEDS_ATTENTION_MIN = 80.0
MIN_WORKS_FOR_CLASSIFICATION = 5

# Allowed classification labels (no UNCLASSIFIED)
VALID_LABELS = {
    "PERFORMER",
    "AVERAGE",
    "NEEDS_ATTENTION",
    "UNDERPERFORMER",
    "NO_DATA",
    "INSUFFICIENT_DATA",
}


# ── Classification logic ────────────────────────────────────────────────────

def compute_score(completion_rate_pct, fund_utilization_pct):
    """Compute 200-point performance score."""
    comp = float(completion_rate_pct) if completion_rate_pct is not None else 0.0
    util = float(fund_utilization_pct) if fund_utilization_pct is not None else 0.0
    return round(comp + util, 2)


def classify_from_score(score):
    """Classify based on 200-point score. Returns one of the 4 performance labels."""
    if score >= PERFORMER_MIN:
        return "PERFORMER"
    if score >= AVERAGE_MIN:
        return "AVERAGE"
    if score >= NEEDS_ATTENTION_MIN:
        return "NEEDS_ATTENTION"
    return "UNDERPERFORMER"


def classify_member(row: asyncpg.Record) -> tuple[str, float]:
    """
    Classify a single member from DB2 member_metrics row.
    Returns (classification, performance_score).
    """
    total = row["total_works"] or 0
    zero_work = row.get("zero_work_member", False) or False
    low_sample = row.get("low_sample_member", False) or False
    completion = row["completion_rate_pct"]
    utilization = row["fund_utilization_pct"]

    # Data quality checks
    if zero_work or total == 0:
        return ("NO_DATA", 0.0)
    if low_sample or total < MIN_WORKS_FOR_CLASSIFICATION:
        return ("INSUFFICIENT_DATA", 0.0)

    score = compute_score(completion, utilization)
    label = classify_from_score(score)
    return (label, score)


def classify_state(row: asyncpg.Record) -> tuple[str, float]:
    """
    Classify a single state from DB2 state_metrics row.
    Returns (classification, performance_score).
    """
    total = row["total_works"] or 0
    completion = row["completion_rate_pct"]
    utilization = row["fund_utilization_pct"]

    if total == 0:
        return ("NO_DATA", 0.0)

    score = compute_score(completion, utilization)
    label = classify_from_score(score)
    return (label, score)


# ── DB operations (DB2-only) ────────────────────────────────────────────────

async def run_classification(db2_pool: asyncpg.Pool) -> dict:
    """
    Full classification pipeline — reads from DB2, writes back to DB2.
    Uses the canonical completion_rate_pct and fund_utilization_pct.
    Returns distribution summary dict.
    """
    # Read from DB2
    mp_rows = await db2_pool.fetch(
        "SELECT * FROM public.member_metrics WHERE member_type = 'MP'"
    )
    mla_rows = await db2_pool.fetch(
        "SELECT * FROM public.member_metrics WHERE member_type = 'MLA'"
    )
    state_rows = await db2_pool.fetch("SELECT * FROM public.state_metrics")

    # Classify MPs
    mp_results = {}
    for row in mp_rows:
        label, score = classify_member(row)
        mp_results[row["member_id"]] = (label, score)

    # Classify MLAs
    mla_results = {}
    for row in mla_rows:
        label, score = classify_member(row)
        mla_results[row["member_id"]] = (label, score)

    # Classify states
    state_results = {}
    for row in state_rows:
        label, score = classify_state(row)
        state_results[row["state_id"]] = (label, score)

    # Write to DB2 — members
    mp_updated = 0
    for member_id, (label, score) in mp_results.items():
        result = await db2_pool.execute(
            "UPDATE public.member_metrics SET performance_classification = $1, performance_score = $2 WHERE member_id = $3 AND member_type = 'MP'",
            label, score, member_id,
        )
        if result.endswith("1"):
            mp_updated += 1

    mla_updated = 0
    for member_id, (label, score) in mla_results.items():
        result = await db2_pool.execute(
            "UPDATE public.member_metrics SET performance_classification = $1, performance_score = $2 WHERE member_id = $3 AND member_type = 'MLA'",
            label, score, member_id,
        )
        if result.endswith("1"):
            mla_updated += 1

    # Write to DB2 — states
    state_updated = 0
    for state_id, (label, score) in state_results.items():
        result = await db2_pool.execute(
            "UPDATE public.state_metrics SET performance_classification = $1, performance_score = $2 WHERE state_id = $3",
            label, score, state_id,
        )
        if result.endswith("1"):
            state_updated += 1

    # Compute distributions
    all_labels = [v[0] for v in mp_results.values()] + [v[0] for v in mla_results.values()]
    member_dist = {}
    for label in all_labels:
        member_dist[label] = member_dist.get(label, 0) + 1

    state_dist = {}
    for label in [v[0] for v in state_results.values()]:
        state_dist[label] = state_dist.get(label, 0) + 1

    return {
        "member_distribution": member_dist,
        "state_distribution": state_dist,
        "mp_classified": mp_updated,
        "mla_classified": mla_updated,
        "state_classified": state_updated,
        "total_mp": len(mp_results),
        "total_mla": len(mla_results),
        "total_states": len(state_results),
    }
