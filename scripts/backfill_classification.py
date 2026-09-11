#!/usr/bin/env python3
"""
Standalone backfill: 200-point entity performance classification.

Reads from DB2 (member_metrics, state_metrics).
Writes back to DB2 (performance_score, performance_classification).

No dependency on DB1. Uses canonical DB2 fields:
  completion_rate_pct + fund_utilization_pct = performance_score (max 200)

Classification bands:
  160–200    → PERFORMER
  120–159.99 → AVERAGE
  80–119.99  → NEEDS_ATTENTION
  0–79.99    → UNDERPERFORMER
"""

import asyncio
import sys
import os
import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

P = lambda *a, **k: print(*a, **k, flush=True)


async def main():
    P("=" * 60)
    P("200-POINT CLASSIFICATION BACKFILL")
    P("=" * 60)
    P()

    # Connect to DB2 only
    P("Connecting to DB2...")
    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=15)
    P("Connected.")

    # Step 1: Add performance_score column if it doesn't exist
    P("\n[1/5] Ensuring performance_score column exists...")
    try:
        await db2.execute("ALTER TABLE public.member_metrics ADD COLUMN IF NOT EXISTS performance_score NUMERIC DEFAULT 0")
        P("  member_metrics.performance_score — OK")
    except Exception as e:
        P(f"  member_metrics.performance_score — {e}")

    try:
        await db2.execute("ALTER TABLE public.state_metrics ADD COLUMN IF NOT EXISTS performance_score NUMERIC DEFAULT 0")
        P("  state_metrics.performance_score — OK")
    except Exception as e:
        P(f"  state_metrics.performance_score — {e}")

    # Step 2: Read all data from DB2
    P("\n[2/5] Reading data from DB2...")
    mp_rows = await db2.fetch("SELECT * FROM public.member_metrics WHERE member_type = 'MP'")
    P(f"  MP rows: {len(mp_rows)}")
    mla_rows = await db2.fetch("SELECT * FROM public.member_metrics WHERE member_type = 'MLA'")
    P(f"  MLA rows: {len(mla_rows)}")
    state_rows = await db2.fetch("SELECT * FROM public.state_metrics")
    P(f"  State rows: {len(state_rows)}")

    # Step 3: Classify using 200-point system
    P("\n[3/5] Classifying with 200-point matrix...")
    from app.classification import classify_member, classify_state

    mp_args = []
    for row in mp_rows:
        label, score = classify_member(row)
        mp_args.append((label, score, row["member_id"]))
    P(f"  MPs classified: {len(mp_args)}")

    mla_args = []
    for row in mla_rows:
        label, score = classify_member(row)
        mla_args.append((label, score, row["member_id"]))
    P(f"  MLAs classified: {len(mla_args)}")

    state_args = []
    for row in state_rows:
        label, score = classify_state(row)
        state_args.append((label, score, row["state_id"]))
    P(f"  States classified: {len(state_args)}")

    # Step 4: Write to DB2
    P("\n[4/5] Writing to DB2...")
    await db2.executemany(
        "UPDATE public.member_metrics SET performance_classification = $1, performance_score = $2 WHERE member_id = $3 AND member_type = 'MP'",
        mp_args,
    )
    P(f"  MPs updated: {len(mp_args)}")

    await db2.executemany(
        "UPDATE public.member_metrics SET performance_classification = $1, performance_score = $2 WHERE member_id = $3 AND member_type = 'MLA'",
        mla_args,
    )
    P(f"  MLAs updated: {len(mla_args)}")

    await db2.executemany(
        "UPDATE public.state_metrics SET performance_classification = $1, performance_score = $2 WHERE state_id = $3",
        state_args,
    )
    P(f"  States updated: {len(state_args)}")

    # Step 5: Verify
    P("\n[5/5] Verification...")
    verify_m = await db2.fetch(
        "SELECT performance_classification, count(*) as cnt FROM public.member_metrics GROUP BY performance_classification ORDER BY cnt DESC"
    )
    verify_s = await db2.fetch(
        "SELECT performance_classification, count(*) as cnt FROM public.state_metrics GROUP BY performance_classification ORDER BY cnt DESC"
    )

    P("\n=== MEMBER DISTRIBUTION (from DB2) ===")
    total_members = 0
    for row in verify_m:
        P(f"  {row['performance_classification']:25s} {row['cnt']:>5d}")
        total_members += row["cnt"]
    P(f"  {'TOTAL':25s} {total_members:>5d}")

    P("\n=== STATE DISTRIBUTION (from DB2) ===")
    total_states = 0
    for row in verify_s:
        P(f"  {row['performance_classification']:25s} {row['cnt']:>5d}")
        total_states += row["cnt"]
    P(f"  {'TOTAL':25s} {total_states:>5d}")

    # Check for NULLs and UNCLASSIFIED
    P("\n=== DATA QUALITY CHECKS ===")
    null_cls = await db2.fetchval(
        "SELECT count(*) FROM public.member_metrics WHERE performance_classification IS NULL"
    )
    P(f"  NULL classifications in member_metrics: {null_cls}")

    unclass = await db2.fetchval(
        "SELECT count(*) FROM public.member_metrics WHERE performance_classification = 'UNCLASSIFIED'"
    )
    P(f"  UNCLASSIFIED in member_metrics: {unclass}")

    null_score = await db2.fetchval(
        "SELECT count(*) FROM public.member_metrics WHERE performance_score IS NULL"
    )
    P(f"  NULL scores in member_metrics: {null_score}")

    out_of_range = await db2.fetchval(
        "SELECT count(*) FROM public.member_metrics WHERE performance_score < 0 OR performance_score > 200"
    )
    P(f"  Scores outside 0-200: {out_of_range}")

    # Verify six named members
    P("\n=== NAMED MEMBER VERIFICATION ===")
    named = [
        "Shri Narendra Modi",
        "Utkarsh Verma Madhur",
        "Vinod Kumar Bind",
        "Kiren Rijiju",
        "Smita Uday Wagh",
        "CN Annadurai",
    ]
    for name in named:
        row = await db2.fetchrow(
            "SELECT member_name, completion_rate_pct, fund_utilization_pct, performance_score, performance_classification FROM public.member_metrics WHERE member_name ILIKE $1",
            f"%{name}%",
        )
        if row:
            P(f"  {row['member_name']:30s} | comp={row['completion_rate_pct']:>6.1f}% | util={row['fund_utilization_pct']:>6.1f}% | score={row['performance_score']:>6.1f}/200 | {row['performance_classification']}")
        else:
            P(f"  {name:30s} | NOT FOUND")

    await db2.close()
    P("\n" + "=" * 60)
    P("BACKFILL COMPLETE")
    P("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
