#!/usr/bin/env python3
r"""
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
  - Compares source DB1 table row counts + max primary keys against the previous
    successful pipeline run stored in DB2.public.pipeline_metadata.
  - If no change is detected, intelligence generation is skipped.
  - Use --full to force a complete rebuild (e.g., after code/schema changes).
  - Use --dry-run to print the execution plan without modifying any data.

Nightly cron usage:
    0 2 * * * cd /path/to/repo && back\ end/.venv/bin/python automation/daily_pipeline.py

The pipeline saves metadata only after ALL steps succeed, so a failed run does
not mark the data as up-to-date.
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


async def _ensure_metadata_table(db2):
    await db2.execute("""
        CREATE TABLE IF NOT EXISTS public.pipeline_metadata (
            key TEXT PRIMARY KEY,
            metadata_value JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def _get_source_fingerprint(db1):
    """Build a lightweight fingerprint of source DB1 tables.

    Uses row count + max id column where available. This is safe for the
    append-only government data ingestion pattern.
    """
    fingerprint = {}
    for tbl in SOURCE_COUNT_TABLES:
        row = await db1.fetchrow(f"SELECT COUNT(*) AS c FROM public.{tbl}")
        fingerprint[tbl] = {"count": row["c"]}
        # Add max primary key where we can guess it
        id_col = None
        if "works" in tbl and not tbl.endswith("_works"):
            id_col = "work_id"
        elif tbl == "mla_works":
            id_col = "work_id"
        elif "recommendations" in tbl:
            id_col = "recommendation_id"
        elif "sanctions" in tbl:
            id_col = "sanction_id"
        elif "expenditures" in tbl:
            id_col = "expenditure_id"
        elif "completions" in tbl:
            id_col = "completion_id"
        if id_col:
            try:
                mrow = await db1.fetchrow(f"SELECT MAX({id_col}) AS m FROM public.{tbl}")
                fingerprint[tbl]["max_id"] = mrow["m"]
            except Exception:
                pass
    return fingerprint


async def _get_last_fingerprint(db2):
    try:
        row = await db2.fetchrow(
            "SELECT metadata_value FROM public.pipeline_metadata WHERE key = 'source_fingerprint'"
        )
        if row and row["metadata_value"]:
            return row["metadata_value"]
    except asyncpg.exceptions.UndefinedTableError:
        pass
    return None


async def _source_changed(db1, db2):
    current = await _get_source_fingerprint(db1)
    last = await _get_last_fingerprint(db2)
    if last is None:
        P("  no previous fingerprint found; will rebuild intelligence")
        return True, current

    # Also force rebuild if DB2 work_analysis is empty (first deploy / truncated)
    wa_count = await db2.fetchval("SELECT COUNT(*) FROM public.work_analysis")
    mwa_count = await db2.fetchval("SELECT COUNT(*) FROM public.mla_work_analysis")
    if (wa_count or 0) == 0 and (mwa_count or 0) == 0:
        P("  DB2 work_analysis tables are empty; will rebuild intelligence")
        return True, current

    if current != last:
        P("  source fingerprint changed; will rebuild intelligence")
        for tbl in SOURCE_COUNT_TABLES:
            if current.get(tbl) != last.get(tbl):
                P(f"    {tbl}: {last.get(tbl)} -> {current.get(tbl)}")
        return True, current

    P("  source fingerprint unchanged; intelligence rebuild can be skipped")
    return False, current


async def _save_pipeline_success(db2, fingerprint):
    import json
    now = datetime.now(timezone.utc)
    await _ensure_metadata_table(db2)
    await db2.execute("""
        INSERT INTO public.pipeline_metadata (key, metadata_value, updated_at)
        VALUES ('source_fingerprint', $1, $2)
        ON CONFLICT (key) DO UPDATE SET
            metadata_value = EXCLUDED.metadata_value,
            updated_at = EXCLUDED.updated_at
    """, json.dumps(fingerprint), now)
    await db2.execute("""
        INSERT INTO public.pipeline_metadata (key, metadata_value, updated_at)
        VALUES ('last_run_at', $1::jsonb, $2)
        ON CONFLICT (key) DO UPDATE SET
            metadata_value = EXCLUDED.metadata_value,
            updated_at = EXCLUDED.updated_at
    """, json.dumps(now.isoformat()), now)


async def step_intelligence(results, skip: bool = False, full: bool = False, dry_run: bool = False, db1=None, db2=None):
    P("\n[Step 1] DB2 intelligence generation")
    if skip:
        P("  skipped (--skip-intelligence)")
        results["intelligence"] = {"skipped": True}
        return None

    from automation.intelligence.backfill import backfill_all

    if not full and db1 and db2:
        changed, fingerprint = await _source_changed(db1, db2)
        if not changed:
            P("  skipping intelligence rebuild (use --full to force)")
            results["intelligence"] = {"skipped": True, "reason": "source_fingerprint_unchanged"}
            return None
    else:
        fingerprint = await _get_source_fingerprint(db1) if db1 else None

    if dry_run:
        P("  DRY RUN: would execute full intelligence backfill")
        results["intelligence"] = {"dry_run": True, "would_run": True}
        return fingerprint

    result = await backfill_all(intelligence=True)
    results["intelligence"] = result
    P(f"  work_analysis: {result.get('work_analysis', {})}")
    P(f"  member_metrics: {result.get('member_metrics', 0)}")
    P(f"  state_metrics: {result.get('state_metrics', 0)}")
    P(f"  model statuses: isolation_forest={result.get('anomaly', {}).get('isolation_forest', {}).get('status')}, project_delay_xgb={result.get('delay_xgb', {}).get('status')}")
    P(f"  duration: {result.get('duration_seconds', 0):.1f}s")
    return fingerprint


async def step_classification(db2, results, dry_run: bool = False):
    P("\n[Step 2] Entity classification (200-point)")
    if dry_run:
        P("  DRY RUN: would run classification")
        results["classification"] = {"dry_run": True}
        return
    result = await run_classification(Conn(db2))
    results["classification"] = result
    P(f"  MPs:    {result['mp_classified']}/{result['total_mp']}")
    P(f"  MLAs:   {result['mla_classified']}/{result['total_mla']}")
    P(f"  States: {result['state_classified']}/{result['total_states']}")


async def step_allocations(results, dry_run: bool = False):
    P("\n[Step 3] Allocation matching reconciliation")
    if dry_run:
        P("  DRY RUN: would run allocation reconciliation")
        results["allocations"] = {"dry_run": True}
        return
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


async def step_ranks(results, dry_run: bool = False):
    P("\n[Step 4] Intelligence rank / label reconciliation")
    if dry_run:
        P("  DRY RUN: would run rank/label reconciliation")
        results["ranks"] = {"dry_run": True}
        return
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


async def step_data_updated(db1, results, dry_run: bool = False):
    P("\n[Step 5] Update data_updated timestamp")
    if dry_run:
        P("  DRY RUN: would update data_updated")
        results["data_updated"] = {"dry_run": True}
        return
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


async def run_pipeline(skip_intelligence: bool = False, full: bool = False, dry_run: bool = False):
    start = time.time()
    P("=" * 70)
    P("GOVSENSE DAILY PIPELINE")
    P("=" * 70)
    P(f"Started: {datetime.now(timezone.utc).isoformat()}")
    P(f"skip_intelligence={skip_intelligence}, full={full}, dry_run={dry_run}")

    db1 = await asyncpg.connect(dsn=settings.DATABASE_URL, timeout=30, command_timeout=600)
    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=30, command_timeout=600)
    await db1.execute("SET statement_timeout = '600000'")
    await db2.execute("SET statement_timeout = '600000'")
    if not dry_run:
        await _ensure_metadata_table(db2)
    P("Databases connected.")

    results = {"start_time": datetime.now(timezone.utc).isoformat(), "dry_run": dry_run}
    fingerprint = None

    try:
        fingerprint = await step_intelligence(results, skip=skip_intelligence, full=full, dry_run=dry_run, db1=db1, db2=db2)
        await step_classification(db2, results, dry_run=dry_run)
        await step_allocations(results, dry_run=dry_run)
        await step_ranks(results, dry_run=dry_run)
        await step_data_updated(db1, results, dry_run=dry_run)

        if not dry_run and fingerprint is not None:
            await _save_pipeline_success(db2, fingerprint)
            P("\nPipeline metadata saved (source fingerprint + last_run_at).")

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
                        help="Force full intelligence rebuild regardless of source fingerprint")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print execution plan without modifying any data")
    args = parser.parse_args()

    await run_pipeline(skip_intelligence=args.skip_intelligence, full=args.full, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
