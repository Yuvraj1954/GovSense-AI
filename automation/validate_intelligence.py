#!/usr/bin/env python3
"""
GovSense intelligence validation.

Validates persisted intelligence tables in DB2.
Does NOT regenerate scores — it checks that the stored values are internally
consistent and pipeline-maintained.
"""

import asyncio
import asyncpg
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

P = lambda *a, **k: print(*a, **k, flush=True)


def threshold_label(score):
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


async def main():
    P("=" * 70)
    P("GOVSENSE INTELLIGENCE VALIDATION")
    P("=" * 70)
    P(f"Started: {datetime.now(timezone.utc).isoformat()}")

    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=30)

    checks = []

    # 1. Coverage
    row = await db2.fetchrow("SELECT COUNT(*) as c FROM public.member_intelligence")
    member_count = row["c"]
    row = await db2.fetchrow("SELECT COUNT(*) as c FROM public.member_metrics")
    checks.append(("member_intelligence coverage", member_count == row["c"], f"{member_count}/{row['c']}"))

    row = await db2.fetchrow("SELECT COUNT(*) as c FROM public.state_intelligence")
    state_count = row["c"]
    row = await db2.fetchrow("SELECT COUNT(*) as c FROM public.state_metrics")
    checks.append(("state_intelligence coverage", state_count == row["c"], f"{state_count}/{row['c']}"))

    # 2. Score bounds
    row = await db2.fetchrow("""
        SELECT MIN(performance_score_100) as mn, MAX(performance_score_100) as mx,
               COUNT(*) FILTER (WHERE performance_score_100 < 0 OR performance_score_100 > 100) as bad
        FROM public.member_intelligence
    """)
    checks.append(("member score bounds", row["mn"] is None or (row["mn"] >= 0 and row["mx"] <= 100 and row["bad"] == 0),
                   f"min={row['mn']}, max={row['mx']}, out_of_range={row['bad']}"))

    row = await db2.fetchrow("""
        SELECT MIN(performance_score_100) as mn, MAX(performance_score_100) as mx,
               COUNT(*) FILTER (WHERE performance_score_100 < 0 OR performance_score_100 > 100) as bad
        FROM public.state_intelligence
    """)
    checks.append(("state score bounds", row["mn"] is None or (row["mn"] >= 0 and row["mx"] <= 100 and row["bad"] == 0),
                   f"min={row['mn']}, max={row['mx']}, out_of_range={row['bad']}"))

    # 3. Label consistency
    bad_labels = await db2.fetch("""
        SELECT member_id, member_type, performance_score_100, performance_label
        FROM public.member_intelligence
        WHERE performance_score_100 IS NOT NULL
    """)
    label_errors = [r for r in bad_labels if threshold_label(r["performance_score_100"]) != r["performance_label"]]
    checks.append(("member label consistency", len(label_errors) == 0, f"errors={len(label_errors)}"))

    bad_state_labels = await db2.fetch("""
        SELECT state_id, performance_score_100, performance_label
        FROM public.state_intelligence
        WHERE performance_score_100 IS NOT NULL
    """)
    state_label_errors = [r for r in bad_state_labels if threshold_label(r["performance_score_100"]) != r["performance_label"]]
    checks.append(("state label consistency", len(state_label_errors) == 0, f"errors={len(state_label_errors)}"))

    # 4. Rank inversions
    inv = await db2.fetchval("""
        SELECT COUNT(*) FROM (
            SELECT a.performance_score_100, a.national_rank,
                   b.performance_score_100 as b_score, b.national_rank as b_rank
            FROM public.member_intelligence a
            JOIN public.member_intelligence b ON a.performance_score_100 < b.performance_score_100
            WHERE a.national_rank < b.national_rank
              AND a.performance_score_100 IS NOT NULL AND b.performance_score_100 IS NOT NULL
        ) t
    """)
    checks.append(("member national_rank inversions", inv == 0, f"inversions={inv}"))

    inv = await db2.fetchval("""
        SELECT COUNT(*) FROM (
            SELECT a.member_type, a.performance_score_100, a.peer_rank,
                   b.performance_score_100 as b_score, b.peer_rank as b_rank
            FROM public.member_intelligence a
            JOIN public.member_intelligence b ON a.member_type = b.member_type AND a.performance_score_100 < b.performance_score_100
            WHERE a.peer_rank < b.peer_rank
              AND a.performance_score_100 IS NOT NULL AND b.performance_score_100 IS NOT NULL
        ) t
    """)
    checks.append(("member peer_rank inversions", inv == 0, f"inversions={inv}"))

    inv = await db2.fetchval("""
        SELECT COUNT(*) FROM (
            SELECT a.performance_score_100, a.rank,
                   b.performance_score_100 as b_score, b.rank as b_rank
            FROM public.state_intelligence a
            JOIN public.state_intelligence b ON a.performance_score_100 < b.performance_score_100
            WHERE a.rank < b.rank
              AND a.performance_score_100 IS NOT NULL AND b.performance_score_100 IS NOT NULL
        ) t
    """)
    checks.append(("state rank inversions", inv == 0, f"inversions={inv}"))

    # 5. Allocation coverage
    row = await db2.fetchrow("""
        SELECT COUNT(*) as total,
               COUNT(*) FILTER (WHERE allocated_amount IS NOT NULL) as with_alloc,
               COUNT(*) FILTER (WHERE allocated_amount > 0) as positive
        FROM public.member_metrics
    """)
    checks.append(("allocation coverage", row["total"] == row["with_alloc"],
                   f"total={row['total']}, with_alloc={row['with_alloc']}, positive={row['positive']}"))

    # 6. Null authoritative scores where they should exist
    null_scores = await db2.fetchval("""
        SELECT COUNT(*) FROM public.member_intelligence
        WHERE performance_score_100 IS NULL AND performance_label NOT IN ('NO_DATA', 'INSUFFICIENT_DATA')
    """)
    checks.append(("null authoritative scores", null_scores == 0, f"bad={null_scores}"))

    await db2.close()

    P("\n--- Validation Results ---")
    all_pass = True
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        P(f"  [{status}] {name}: {detail}")

    P(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    P("=" * 70)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    asyncio.run(main())
