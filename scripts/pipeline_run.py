#!/usr/bin/env python3
"""
Daily pipeline runner.

Runs AFTER the main analytics pipeline has updated DB1 tables.
1. Runs entity classification (DB2 only — 200-point system)
2. Updates data_updated timestamp

TODO: DAILY PIPELINE — MP/MLA/STATE PERFORMANCE CLASSIFICATION
    Recalculate the same DB2 performance_score and performance_classification
    during the daily pipeline after the underlying analysis/precomputed metrics
    have been refreshed. Persist updated labels and scores to DB2.
    Use exactly the same 200-point classification algorithm.
    Do not create a separate classification process.

Usage (from the repository root):
    python scripts/pipeline_run.py
"""

import asyncio
import sys
import os
import asyncpg
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings
from app.classification import run_classification

P = lambda *a, **k: print(*a, **k, flush=True)


class Conn:
    """Wraps a raw asyncpg connection to match pool.fetch/execute interface."""
    def __init__(self, conn):
        self._c = conn
    async def fetch(self, q, *a):
        return await self._c.fetch(q, *a)
    async def execute(self, q, *a):
        return await self._c.execute(q, *a)


async def main():
    P("=== DAILY PIPELINE: CLASSIFICATION + DATA_UPDATED ===")
    P(f"Started at: {datetime.now(timezone.utc).isoformat()}")

    db1 = await asyncpg.connect(dsn=settings.DATABASE_URL, timeout=15)
    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=15)
    P("Databases connected.")

    # Step 1: Classification (DB2-only, 200-point system)
    P("\n--- Step 1: Entity Classification (200-point) ---")
    result = await run_classification(Conn(db2))

    P(f"MPs:    {result['mp_classified']}/{result['total_mp']}")
    P(f"MLAs:   {result['mla_classified']}/{result['total_mla']}")
    P(f"States: {result['state_classified']}/{result['total_states']}")

    P("\nMember distribution:")
    for lbl in ["PERFORMER", "AVERAGE", "NEEDS_ATTENTION", "UNDERPERFORMER", "NO_DATA", "INSUFFICIENT_DATA"]:
        P(f"  {lbl:25s} {result['member_distribution'].get(lbl, 0):>5d}")

    P("\nState distribution:")
    for lbl in ["PERFORMER", "AVERAGE", "NEEDS_ATTENTION", "UNDERPERFORMER", "NO_DATA", "INSUFFICIENT_DATA"]:
        P(f"  {lbl:25s} {result['state_distribution'].get(lbl, 0):>5d}")

    # Step 2: Update data_updated
    P("\n--- Step 2: Update data_updated ---")
    now = datetime.now(timezone.utc)
    await db2.execute(
        """INSERT INTO public.data_updated (id, completed_at, status, updated_at)
           VALUES (1, $1, 'complete', $2)
           ON CONFLICT (id) DO UPDATE SET
             completed_at = EXCLUDED.completed_at,
             status = EXCLUDED.status,
             updated_at = EXCLUDED.updated_at""",
        now, now,
    )
    P(f"data_updated set to: {now.isoformat()}")

    await db1.close()
    await db2.close()
    P(f"\n=== PIPELINE COMPLETE at {datetime.now(timezone.utc).isoformat()} ===")


if __name__ == "__main__":
    asyncio.run(main())
