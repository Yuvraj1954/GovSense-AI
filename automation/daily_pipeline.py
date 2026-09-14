#!/usr/bin/env python3
"""
GovSense daily production pipeline.

Entry point: python automation/daily_pipeline.py

This pipeline runs the analytics maintenance steps that are present in the
repository.  It is intentionally fail-safe: an error in a downstream step does
not corrupt DB1 raw ingestion.

Steps:
  1. Entity classification (DB2, 200-point system)
  2. Allocation matching reconciliation
  3. Intelligence rank / label reconciliation
  4. Update data_updated timestamp

IMPORTANT: The full ML intelligence backfill (Wilson/Bayesian performance
scoring, K-Means profiling, Isolation Forest, XGBoost delay model) is stored
as persisted results in DB2 but its generation code is not part of this
repository.  When that code is re-integrated, insert it as Step 9 here and
expose --skip-intelligence support.
"""

import argparse
import asyncio
import asyncpg
import os
import sys
import time
import traceback
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

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


async def step_classification(db2, results):
    P("\n[Step 1] Entity classification (200-point)")
    result = await run_classification(Conn(db2))
    results["classification"] = result
    P(f"  MPs:    {result['mp_classified']}/{result['total_mp']}")
    P(f"  MLAs:   {result['mla_classified']}/{result['total_mla']}")
    P(f"  States: {result['state_classified']}/{result['total_states']}")


async def step_allocations(results):
    P("\n[Step 2] Allocation matching reconciliation")
    from scripts.fix_allocations import main as run_alloc_fix
    # Capture stdout by redirecting
    import io
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        await run_alloc_fix()
    finally:
        sys.stdout = old_stdout
    output = buffer.getvalue()
    results["allocations"] = {"output_lines": output.splitlines()[-30:]}
    for line in output.splitlines()[-20:]:
        P(f"  {line}")


async def step_ranks(results):
    P("\n[Step 3] Intelligence rank / label reconciliation")
    from scripts.fix_ranks import main as run_rank_fix
    import io
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()
    try:
        await run_rank_fix()
    finally:
        sys.stdout = old_stdout
    output = buffer.getvalue()
    results["ranks"] = {"output_lines": output.splitlines()[-30:]}
    for line in output.splitlines()[-20:]:
        P(f"  {line}")


async def step_data_updated(db1, results):
    P("\n[Step 4] Update data_updated timestamp")
    now = datetime.now(timezone.utc)
    await db1.execute(
        """INSERT INTO public.data_updated (id, completed_at, status, updated_at)
           VALUES (1, $1, 'complete', $2)
           ON CONFLICT (id) DO UPDATE SET
             completed_at = EXCLUDED.completed_at,
             status = EXCLUDED.status,
             updated_at = EXCLUDED.updated_at""",
        now, now,
    )
    results["data_updated"] = {"completed_at": now.isoformat()}
    P(f"  data_updated set to {now.isoformat()}")


async def run_pipeline(skip_intelligence: bool = False):
    start = time.time()
    P("=" * 70)
    P("GOVSENSE DAILY PIPELINE")
    P("=" * 70)
    P(f"Started: {datetime.now(timezone.utc).isoformat()}")
    P(f"skip_intelligence={skip_intelligence}")

    db1 = await asyncpg.connect(dsn=settings.DATABASE_URL, timeout=30)
    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=30)
    P("Databases connected.")

    results = {"start_time": datetime.now(timezone.utc).isoformat()}

    try:
        await step_classification(db2, results)
        await step_allocations(results)
        await step_ranks(results)
        await step_data_updated(db1, results)
    except Exception as e:
        P(f"\nPIPELINE ERROR: {e}")
        traceback.print_exc()
        results["error"] = str(e)
        raise
    finally:
        await db1.close()
        await db2.close()
        elapsed = time.time() - start
        results["elapsed_seconds"] = elapsed
        results["end_time"] = datetime.now(timezone.utc).isoformat()
        P(f"\nPipeline elapsed: {elapsed:.1f}s")
        P("=" * 70)

    return results


async def main():
    parser = argparse.ArgumentParser(description="GovSense daily production pipeline")
    parser.add_argument("--skip-intelligence", action="store_true",
                        help="Skip intelligence-dependent steps (currently no-op because generation code is external)")
    args = parser.parse_args()

    await run_pipeline(skip_intelligence=args.skip_intelligence)


if __name__ == "__main__":
    asyncio.run(main())
