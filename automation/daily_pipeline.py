#!/usr/bin/env python3
"""
GovSense daily production pipeline.

Entry point: python automation/daily_pipeline.py

This pipeline is intentionally fail-safe: an error in a downstream step does
not corrupt DB1 raw ingestion.

Steps:
  1. DB2 intelligence generation (work_analysis, metrics, ML, risk) — incremental by default
  2. Entity classification (DB2, 200-point system)
  3. Allocation matching reconciliation
  4. Intelligence rank / label reconciliation
  5. Update data_updated timestamp

Incremental mode:
  - Compares source DB1 table row counts against the previous pipeline run.
  - If counts are unchanged, intelligence generation is skipped.
  - Use --full to force a complete rebuild (e.g., after code/schema changes).

Use --skip-intelligence to skip intelligence regardless of changes.
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


# Tables that drive work_analysis / metrics. If any count changes, rebuild intelligence.
SOURCE_COUNT_TABLES = [
    "works", "work_recommendations", "work_sanctions", "work_expenditures", "work_completions",
    "mla_works", "mla_work_recommendations", "mla_work_sanctions", "mla_work_expenditures", "mla_work_completions",
]


async def _get_source_counts(db1):
    counts = {}
    for tbl in SOURCE_COUNT_TABLES:
        row = await db1.fetchrow(f"SELECT COUNT(*) AS c FROM public.{tbl}")
        counts[tbl] = row["c"]
    return counts


async def _get_last_source_counts(db2):
    try:
        row = await db2.fetchrow(
            "SELECT metadata_value FROM public.pipeline_metadata WHERE key = 'source_counts'"
        )
        if row and row["metadata_value"]:
            return row["metadata_value"]
    except asyncpg.exceptions.UndefinedTableError:
        pass
    return None


async def _save_source_counts(db2, counts):
    import json
    await db2.execute("""
        CREATE TABLE IF NOT EXISTS public.pipeline_metadata (
            key TEXT PRIMARY KEY,
            metadata_value JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db2.execute("""
        INSERT INTO public.pipeline_metadata (key, metadata_value, updated_at)
        VALUES ('source_counts', $1, $2)
        ON CONFLICT (key) DO UPDATE SET
            metadata_value = EXCLUDED.metadata_value,
            updated_at = EXCLUDED.updated_at
    """, json.dumps(counts), datetime.now(timezone.utc))


async def _source_counts_changed(db1, db2) -> bool:
    current = await _get_source_counts(db1)
    last = await _get_last_source_counts(db2)
    if last is None:
        P("  no previous source counts found; will rebuild intelligence")
        return True
    if current != last:
        P("  source counts changed; will rebuild intelligence")
        for tbl in SOURCE_COUNT_TABLES:
            if current.get(tbl) != last.get(tbl):
                P(f"    {tbl}: {last.get(tbl)} -> {current.get(tbl)}")
        return True
    P("  source counts unchanged; intelligence rebuild can be skipped")
    return False


async def step_intelligence(results, skip: bool = False, full: bool = False, db1=None, db2=None):
    P("\n[Step 1] DB2 intelligence generation")
    if skip:
        P("  skipped (--skip-intelligence)")
        results["intelligence"] = {"skipped": True}
        return

    from automation.intelligence.backfill import backfill_all

    if not full and db1 and db2:
        changed = await _source_counts_changed(db1, db2)
        if not changed:
            P("  skipping intelligence rebuild (use --full to force)")
            results["intelligence"] = {"skipped": True, "reason": "source_counts_unchanged"}
            return

    result = await backfill_all(intelligence=True)
    results["intelligence"] = result
    P(f"  work_analysis: {result.get('work_analysis', {})}")
    P(f"  member_metrics: {result.get('member_metrics', 0)}")
    P(f"  state_metrics: {result.get('state_metrics', 0)}")
    P(f"  model statuses: isolation_forest={result.get('anomaly', {}).get('isolation_forest', {}).get('status')}, project_delay_xgb={result.get('delay_xgb', {}).get('status')}")
    P(f"  duration: {result.get('duration_seconds', 0):.1f}s")

    # Save counts only after successful rebuild
    if db1 and db2:
        counts = await _get_source_counts(db1)
        await _save_source_counts(db2, counts)
        P("  source counts saved for next incremental run")


async def step_classification(db2, results):
    P("\n[Step 2] Entity classification (200-point)")
    result = await run_classification(Conn(db2))
    results["classification"] = result
    P(f"  MPs:    {result['mp_classified']}/{result['total_mp']}")
    P(f"  MLAs:   {result['mla_classified']}/{result['total_mla']}")
    P(f"  States: {result['state_classified']}/{result['total_states']}")


async def step_allocations(results):
    P("\n[Step 3] Allocation matching reconciliation")
    from scripts.fix_allocations import main as run_alloc_fix
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
    P("\n[Step 4] Intelligence rank / label reconciliation")
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
    P("\n[Step 5] Update data_updated timestamp")
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


async def run_pipeline(skip_intelligence: bool = False, full: bool = False):
    start = time.time()
    P("=" * 70)
    P("GOVSENSE DAILY PIPELINE")
    P("=" * 70)
    P(f"Started: {datetime.now(timezone.utc).isoformat()}")
    P(f"skip_intelligence={skip_intelligence}, full={full}")

    db1 = await asyncpg.connect(dsn=settings.DATABASE_URL, timeout=30, command_timeout=600)
    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=30, command_timeout=600)
    await db1.execute("SET statement_timeout = '600000'")
    await db2.execute("SET statement_timeout = '600000'")
    P("Databases connected.")

    results = {"start_time": datetime.now(timezone.utc).isoformat()}

    try:
        await step_intelligence(results, skip=skip_intelligence, full=full, db1=db1, db2=db2)
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
                        help="Skip DB2 intelligence regeneration")
    parser.add_argument("--full", action="store_true",
                        help="Force full intelligence rebuild regardless of source count changes")
    args = parser.parse_args()

    await run_pipeline(skip_intelligence=args.skip_intelligence, full=args.full)


if __name__ == "__main__":
    asyncio.run(main())
