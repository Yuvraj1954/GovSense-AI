"""Deterministic performance scoring for members and states.

Authoritative formula:
  performance_score_weighted =
      0.40 * completion_rate_pct
    + 0.40 * fund_utilization_pct
    + 0.20 * scale_score

Where scale_score = percentile rank (midrank) of total_works across
the ranking-qualified population (0-100).
"""
import math
from typing import List, Dict, Any
import asyncpg
from automation.intelligence.database import db2_pool


def _percentile_rank(values, target):
    """Midrank percentile: (count_below + 0.5 * count_equal) / n * 100."""
    n = len(values)
    if n == 0:
        return 0.0
    below = sum(1 for v in values if v < target)
    at = sum(1 for v in values if v == target)
    return round((below + 0.5 * at) / n * 100.0, 2)


def performance_label(score, sample_size, zero_work=False):
    if zero_work or sample_size == 0 or score is None:
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


def performance_confidence(sample_size):
    if sample_size == 0:
        return "NONE"
    if sample_size < 5:
        return "LOW"
    if sample_size < 15:
        return "MEDIUM"
    return "HIGH"


async def compute_member_performance() -> int:
    """Compute deterministic performance scores for all members.

    Uses the authoritative 0-100 weighted formula:
      performance_score_weighted = 0.40 * comp + 0.40 * util + 0.20 * scale_score

    Writes to member_metrics: performance_score, performance_score_weighted,
    performance_classification.
    """
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM member_metrics")
            if not rows:
                return 0

            # Compute percentile rank of total_works for scale_score
            qualified_total_works = [
                int(r["total_works"] or 0)
                for r in rows
                if not r["zero_work_member"] and (r["total_works"] or 0) >= 5
            ]

            updates = []
            for r in rows:
                if r["zero_work_member"] or (r["total_works"] or 0) == 0:
                    score = 0.0
                    weighted = 0.0
                else:
                    comp = float(r["completion_rate_pct"] or 0)
                    util = min(100.0, max(0.0, float(r["fund_utilization_pct"] or 0)))
                    total_works = int(r["total_works"] or 0)
                    scale = _percentile_rank(qualified_total_works, total_works) if total_works >= 5 else 0.0
                    weighted = round(comp * 0.40 + util * 0.40 + scale * 0.20, 2)
                    score = weighted

                updates.append({
                    "member_id": r["member_id"],
                    "member_type": r["member_type"],
                    "performance_score": score,
                    "performance_score_weighted": weighted,
                    "total_works": r["total_works"],
                })

            await conn.executemany("""
                UPDATE member_metrics
                SET performance_score = $3,
                    performance_score_weighted = $4,
                    performance_classification = $5
                WHERE member_id = $1 AND member_type = $2
            """, [(
                u["member_id"], u["member_type"], u["performance_score"], u["performance_score_weighted"],
                performance_label(u["performance_score"], u["total_works"], zero_work=(u["total_works"] == 0))
            ) for u in updates])
            return len(updates)
    finally:
        await p2.close()


async def compute_state_performance() -> int:
    """Compute deterministic performance scores for all states.

    Uses the authoritative 0-100 weighted formula.
    """
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM state_metrics")
            if not rows:
                return 0

            # Compute percentile rank of total_works for scale_score
            qualified_total_works = [
                int(r["total_works"] or 0)
                for r in rows
                if (r["total_works"] or 0) > 0
            ]

            updates = []
            for r in rows:
                if (r["total_works"] or 0) == 0:
                    score = 0.0
                    weighted = 0.0
                else:
                    comp = float(r["completion_rate_pct"] or 0)
                    util = min(100.0, max(0.0, float(r["fund_utilization_pct"] or 0)))
                    total_works = int(r["total_works"] or 0)
                    scale = _percentile_rank(qualified_total_works, total_works)
                    weighted = round(comp * 0.40 + util * 0.40 + scale * 0.20, 2)
                    score = weighted

                updates.append({
                    "state_id": r["state_id"],
                    "performance_score": score,
                    "performance_score_weighted": weighted,
                    "total_works": r["total_works"],
                })

            await conn.executemany("""
                UPDATE state_metrics
                SET performance_score = $2,
                    performance_score_weighted = $3,
                    performance_classification = $4
                WHERE state_id = $1
            """, [(
                u["state_id"], u["performance_score"], u["performance_score_weighted"],
                performance_label(u["performance_score"], u["total_works"], zero_work=(u["total_works"] == 0))
            ) for u in updates])
            return len(updates)
    finally:
        await p2.close()


async def compute_all_performance() -> Dict[str, int]:
    m = await compute_member_performance()
    s = await compute_state_performance()
    return {"member_performance": m, "state_performance": s}
