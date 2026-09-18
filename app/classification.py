"""
Deterministic entity performance classification for MPLADS.

Uses the authoritative 0-100 weighted score:
  performance_score_weighted = 0.40*completion_rate_pct + 0.40*fund_utilization_pct + 0.20*scale_score

Classification bands (0-100):
  85-100   → EXCEPTIONAL
  70-84.99 → PERFORMER
  50-69.99 → STABLE
  35-49.99 → NEEDS_ATTENTION
  0-34.99  → UNDERPERFORMER

Data quality labels:
  NO_DATA            → zero works or zero_work_member flag
  INSUFFICIENT_DATA  → low_sample_member flag or total_works < 5

Reads from DB2 (member_metrics, state_metrics).
Writes to DB2 (same tables).
"""

import asyncpg


MIN_WORKS_FOR_CLASSIFICATION = 5


def classify_from_weighted_score(score):
    """Classify based on 0-100 weighted score. Returns one of the 5 performance labels."""
    if score is None:
        return "NO_DATA"
    if score >= 85:
        return "EXCEPTIONAL"
    if score >= 70:
        return "PERFORMER"
    if score >= 50:
        return "STABLE"
    if score >= 35:
        return "NEEDS_ATTENTION"
    return "UNDERPERFORMER"


def classify_member(row: asyncpg.Record) -> tuple:
    """
    Classify a single member from DB2 member_metrics row.
    Uses performance_score_weighted (0-100) as the authoritative score.
    Returns (classification, performance_score).
    """
    total = row["total_works"] or 0
    zero_work = row.get("zero_work_member", False) or False
    low_sample = row.get("low_sample_member", False) or False

    if zero_work or total == 0:
        return ("NO_DATA", 0.0)
    if low_sample or total < MIN_WORKS_FOR_CLASSIFICATION:
        return ("INSUFFICIENT_DATA", 0.0)

    score = float(row["performance_score_weighted"] or 0)
    label = classify_from_weighted_score(score)
    return (label, score)


def classify_state(row: asyncpg.Record) -> tuple:
    """
    Classify a single state from DB2 state_metrics row.
    Returns (classification, performance_score).
    """
    total = row["total_works"] or 0
    if total == 0:
        return ("NO_DATA", 0.0)

    score = float(row["performance_score_weighted"] or 0)
    label = classify_from_weighted_score(score)
    return (label, score)


async def run_classification(db2_pool: asyncpg.Pool) -> dict:
    """
    Full classification pipeline — reads from DB2, writes back to DB2.
    Uses performance_score_weighted (0-100) as the authoritative score.
    Returns distribution summary dict.
    """
    mp_rows = await db2_pool.fetch(
        "SELECT * FROM public.member_metrics WHERE member_type = 'MP'"
    )
    mla_rows = await db2_pool.fetch(
        "SELECT * FROM public.member_metrics WHERE member_type = 'MLA'"
    )
    state_rows = await db2_pool.fetch("SELECT * FROM public.state_metrics")

    mp_results = {}
    for row in mp_rows:
        label, score = classify_member(row)
        mp_results[row["member_id"]] = (label, score)

    mla_results = {}
    for row in mla_rows:
        label, score = classify_member(row)
        mla_results[row["member_id"]] = (label, score)

    state_results = {}
    for row in state_rows:
        label, score = classify_state(row)
        state_results[row["state_id"]] = (label, score)

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

    state_updated = 0
    for state_id, (label, score) in state_results.items():
        result = await db2_pool.execute(
            "UPDATE public.state_metrics SET performance_classification = $1, performance_score = $2 WHERE state_id = $3",
            label, score, state_id,
        )
        if result.endswith("1"):
            state_updated += 1

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
