"""Deterministic performance scoring for members and states."""
import math
from typing import List, Dict, Any
import asyncpg
from automation.intelligence.database import db2_pool


def _wilson_lower_bound(successes: int, trials: int, confidence: float = 0.95) -> float:
    """Wilson score interval lower bound, scaled 0-100."""
    if trials <= 0:
        return 0.0
    successes = max(0, min(successes, trials))
    z = 1.96 if confidence == 0.95 else 2.576
    p = successes / trials
    n = trials
    z2 = z * z
    denominator = 1 + z2 / n
    centre = p + z2 / (2 * n)
    width = z * math.sqrt((p * (1 - p) / n) + (z2 / (4 * n * n)))
    lower = (centre - width) / denominator
    return max(0.0, min(100.0, lower * 100.0))


def _bayesian_shrinkage(value: float, n: int, prior: float, k: float) -> float:
    """Shrink value toward prior with strength k."""
    if n is None or n <= 0:
        return prior
    return (value * n + prior * k) / (n + k)


def performance_label(score: float, sample_size: int, zero_work: bool = False) -> str:
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


def performance_confidence(sample_size: int) -> str:
    if sample_size == 0:
        return "NONE"
    if sample_size < 5:
        return "LOW"
    if sample_size < 15:
        return "MEDIUM"
    return "HIGH"


async def compute_member_performance() -> int:
    """Compute deterministic performance scores for all members."""
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM member_metrics")
            if not rows:
                return 0

            # Compute raw scores first
            raw_scores: List[float] = []
            valid_n = []
            for r in rows:
                if r["zero_work_member"]:
                    continue
                impl = _wilson_lower_bound(r["completed_works"], r["recommended_works"])
                util = min(100.0, max(0.0, float(r["fund_utilization_pct"] or 0)))
                raw = (impl + util) / 2.0
                raw_scores.append(raw)
                valid_n.append(r["total_works"])

            prior = sum(raw_scores) / len(raw_scores) if raw_scores else 50.0

            updates = []
            for r in rows:
                if r["zero_work_member"] or r["total_works"] == 0:
                    score = 0.0
                    weighted = 0.0
                else:
                    impl = _wilson_lower_bound(r["completed_works"], r["recommended_works"])
                    util = min(100.0, max(0.0, float(r["fund_utilization_pct"] or 0)))
                    raw = (impl + util) / 2.0
                    n = r["total_works"]
                    score = _bayesian_shrinkage(raw, n, prior, k=5.0)
                    weighted = score
                updates.append({
                    "member_id": r["member_id"],
                    "member_type": r["member_type"],
                    "performance_score": score,
                    "performance_score_weighted": weighted,
                })

            await conn.executemany("""
                UPDATE member_metrics
                SET performance_score = $3,
                    performance_score_weighted = $4
                WHERE member_id = $1 AND member_type = $2
            """, [(u["member_id"], u["member_type"], u["performance_score"], u["performance_score_weighted"]) for u in updates])
            return len(updates)
    finally:
        await p2.close()


async def compute_state_performance() -> int:
    """Compute deterministic performance scores for all states."""
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM state_metrics")
            if not rows:
                return 0

            raw_scores = []
            for r in rows:
                if r["total_works"] == 0:
                    continue
                impl = _wilson_lower_bound(r["completed_works"], r["recommended_works"])
                util = min(100.0, max(0.0, float(r["fund_utilization_pct"] or 0)))
                raw = (impl + util) / 2.0
                raw_scores.append(raw)

            prior = sum(raw_scores) / len(raw_scores) if raw_scores else 50.0

            updates = []
            for r in rows:
                if r["total_works"] == 0:
                    score = 0.0
                    weighted = 0.0
                else:
                    impl = _wilson_lower_bound(r["completed_works"], r["recommended_works"])
                    util = min(100.0, max(0.0, float(r["fund_utilization_pct"] or 0)))
                    raw = (impl + util) / 2.0
                    n = r["total_works"]
                    score = _bayesian_shrinkage(raw, n, prior, k=10.0)
                    weighted = score
                updates.append({
                    "state_id": r["state_id"],
                    "performance_score": score,
                    "performance_score_weighted": weighted,
                })

            await conn.executemany("""
                UPDATE state_metrics
                SET performance_score = $2,
                    performance_score_weighted = $3
                WHERE state_id = $1
            """, [(u["state_id"], u["performance_score"], u["performance_score_weighted"]) for u in updates])
            return len(updates)
    finally:
        await p2.close()


async def compute_all_performance() -> Dict[str, int]:
    m = await compute_member_performance()
    s = await compute_state_performance()
    return {"member_performance": m, "state_performance": s}
