#!/usr/bin/env python3
r"""
GovSense daily production pipeline.

Entry point: python automation/daily_pipeline.py

This pipeline is intentionally fail-safe: an error in a downstream step does
not corrupt DB1 raw ingestion.

Steps:
  1. DB2 intelligence generation (work_analysis, metrics, ML, risk)
  2. Entity classification (DB2, 200-point system)
  3. Allocation matching reconciliation
  4. Intelligence rank / label reconciliation
  5. Update data_updated timestamp

Change-detection mode (NOT true member-level incremental processing):
  - Compares a lightweight fingerprint of source DB1 tables against the previous
    successful pipeline run stored in DB2.public.pipeline_metadata.
  - Fingerprint includes row count, max primary key, and max(updated_at) or
    max(created_at) where available.
  - If the fingerprint is unchanged, the full intelligence rebuild is skipped.
  - If the fingerprint changed, ALL derived intelligence is regenerated from
    DB1. This is a "change-triggered full rebuild", not "process only changed
    members/records".
  - Use --full to force a complete rebuild (e.g., after code/schema changes).
  - Use --dry-run to print the execution plan without modifying any data.

Fail-safe partial-run handling:
  - The pipeline writes a "RUNNING" status before intelligence generation.
  - It only writes "SUCCESS" after ALL steps complete.
  - If a previous run crashed or failed, the next normal run sees the RUNNING
    status and forces a rebuild, so DB2 can never be falsely marked current
    while containing partial intelligence.

Nightly cron usage:
    0 2 * * * cd "/path/to/repo" && "back end/.venv/bin/python" automation/daily_pipeline.py

IMPORTANT — architecture invariant:
  DB1 contains raw government data + required ingestion operational state.
  DB2 contains ALL derived analytics, ML, intelligence, risk, and AI data.
  No newly generated derived table should be recreated in DB1.
"""

import argparse
import asyncio
import asyncpg
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

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


# Tables that drive work_analysis / metrics.
# The fingerprint covers count + max(pk) + max(timestamp) to detect appends,
# row updates (when updated_at exists), and most deletions.
SOURCE_FINGERPRINT_TABLES = [
    "works", "work_recommendations", "work_sanctions", "work_expenditures", "work_completions",
    "mla_works", "mla_work_recommendations", "mla_work_sanctions", "mla_work_expenditures", "mla_work_completions",
]

# Derived tables that must be non-empty for DB2 to be considered current.
# If any are empty, the pipeline forces a rebuild regardless of fingerprint.
REQUIRED_DERIVED_TABLES = [
    "work_analysis",
    "mla_work_analysis",
    "member_metrics",
    "state_metrics",
    "member_intelligence",
    "state_intelligence",
    "national_statistics",
    "overall_metrics",
    "trends",
    "category_metrics",
    "fy_metrics",
    "model_registry",
]


def _guess_primary_key(table: str) -> Optional[str]:
    """Return the likely synthetic primary key column for a source table."""
    if table == "works" or table == "mla_works":
        return "work_id"
    if table.endswith("_recommendations"):
        return "recommendation_id"
    if table.endswith("_sanctions"):
        return "sanction_id"
    if table.endswith("_expenditures"):
        return "expenditure_id"
    if table.endswith("_completions"):
        return "completion_id"
    return None


def _guess_change_timestamp(table: str) -> Optional[str]:
    """Return the best available change-tracking timestamp column."""
    # works / mla_works are the only tables with a real updated_at column.
    if table in ("works", "mla_works"):
        return "updated_at"
    # For child tables, created_at at least detects late-arriving rows that
    # might share a primary key space with existing rows.
    if table in (
        "work_expenditures", "work_completions",
        "mla_work_expenditures", "mla_work_completions",
    ):
        return "created_at"
    return None


async def _ensure_metadata_table(db2):
    await db2.execute("""
        CREATE TABLE IF NOT EXISTS public.pipeline_metadata (
            key TEXT PRIMARY KEY,
            metadata_value JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def _get_metadata(db2, key: str) -> Optional[Any]:
    try:
        row = await db2.fetchrow(
            "SELECT metadata_value FROM public.pipeline_metadata WHERE key = $1", key
        )
        if row and row["metadata_value"]:
            return row["metadata_value"]
    except asyncpg.exceptions.UndefinedTableError:
        pass
    return None


async def _set_metadata(db2, key: str, value: Any):
    await _ensure_metadata_table(db2)
    now = datetime.now(timezone.utc)
    await db2.execute("""
        INSERT INTO public.pipeline_metadata (key, metadata_value, updated_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (key) DO UPDATE SET
            metadata_value = EXCLUDED.metadata_value,
            updated_at = EXCLUDED.updated_at
    """, key, json.dumps(value), now)


async def _get_source_fingerprint(db1):
    """Build a lightweight fingerprint of source DB1 tables.

    Captures:
      - row count
      - max primary key value (for append detection)
      - max(updated_at) or max(created_at) (for row-update detection)

    Limitations:
      - Updates to child tables without updated_at (recommendations, sanctions)
        are not detected unless they change the row count or max primary key.
      - In-place edits that do not touch the timestamp columns are not detected.
      This is acceptable for the append-heavy government ingestion pattern and
      keeps the nightly fingerprint cheap.
    """
    fingerprint: Dict[str, Dict[str, Any]] = {}
    for tbl in SOURCE_FINGERPRINT_TABLES:
        row = await db1.fetchrow(f"SELECT COUNT(*) AS c FROM public.{tbl}")
        fingerprint[tbl] = {"count": row["c"]}

        pk = _guess_primary_key(tbl)
        if pk:
            try:
                mrow = await db1.fetchrow(f"SELECT MAX({pk}) AS m FROM public.{tbl}")
                fingerprint[tbl]["max_id"] = mrow["m"]
            except asyncpg.exceptions.UndefinedColumnError:
                pass  # guessed column missing; ignore

        ts = _guess_change_timestamp(tbl)
        if ts:
            try:
                trow = await db1.fetchrow(f"SELECT MAX({ts}) AS m FROM public.{tbl}")
                fingerprint[tbl][f"max_{ts}"] = trow["m"].isoformat() if trow["m"] else None
            except asyncpg.exceptions.UndefinedColumnError:
                pass
    return fingerprint


async def _derived_tables_populated(db2) -> bool:
    """Return True if all required derived tables appear to have data."""
    for tbl in REQUIRED_DERIVED_TABLES:
        try:
            cnt = await db2.fetchval(f"SELECT COUNT(*) FROM public.{tbl}")
        except asyncpg.exceptions.UndefinedTableError:
            return False
        if (cnt or 0) == 0:
            return False
    return True


async def _source_changed(db1, db2, current_fingerprint: Optional[Dict] = None) -> Tuple[bool, Dict]:
    current = current_fingerprint or await _get_source_fingerprint(db1)
    last = await _get_metadata(db2, "source_fingerprint")

    # If a previous run started intelligence but never finished, force rebuild.
    status = await _get_metadata(db2, "pipeline_status")
    if status == "RUNNING":
        P("  previous pipeline run did not complete (status=RUNNING); will rebuild intelligence")
        return True, current

    if last is None:
        P("  no previous fingerprint found; will rebuild intelligence")
        return True, current

    # If DB2 derived tables are empty/partial, force rebuild even if fingerprint matches.
    if not await _derived_tables_populated(db2):
        P("  DB2 derived tables are empty or incomplete; will rebuild intelligence")
        return True, current

    if current != last:
        P("  source fingerprint changed; will rebuild intelligence")
        for tbl in SOURCE_FINGERPRINT_TABLES:
            if current.get(tbl) != last.get(tbl):
                P(f"    {tbl}: {last.get(tbl)} -> {current.get(tbl)}")
        return True, current

    P("  source fingerprint unchanged; intelligence rebuild can be skipped")
    return False, current


async def _save_pipeline_success(db2, fingerprint: Dict):
    now = datetime.now(timezone.utc)
    await _ensure_metadata_table(db2)
    await _set_metadata(db2, "source_fingerprint", fingerprint)
    await _set_metadata(db2, "last_run_at", now.isoformat())
    await _set_metadata(db2, "pipeline_status", "SUCCESS")


async def step_intelligence(results, skip: bool = False, full: bool = False, dry_run: bool = False, db1=None, db2=None):
    P("\n[Step 1] DB2 intelligence generation")

    fingerprint = await _get_source_fingerprint(db1) if db1 else None

    if skip:
        P("  skipped (--skip-intelligence)")
        results["intelligence"] = {"skipped": True}
        return fingerprint

    from automation.intelligence.backfill import backfill_all

    if not full and db1 and db2:
        changed, _ = await _source_changed(db1, db2, current_fingerprint=fingerprint)
        if not changed:
            P("  skipping intelligence rebuild (use --full to force)")
            results["intelligence"] = {"skipped": True, "reason": "source_fingerprint_unchanged"}
            return fingerprint

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
    run_intelligence = not skip_intelligence

    try:
        # Mark intelligence as in-progress so a crash cannot leave DB2 falsely current.
        if not dry_run and run_intelligence:
            await _set_metadata(db2, "pipeline_status", "RUNNING")

        fingerprint = await step_intelligence(results, skip=skip_intelligence, full=full, dry_run=dry_run, db1=db1, db2=db2)
        await step_classification(db2, results, dry_run=dry_run)
        await step_allocations(results, dry_run=dry_run)
        await step_ranks(results, dry_run=dry_run)
        await step_data_updated(db1, results, dry_run=dry_run)

        if not dry_run and fingerprint is not None and run_intelligence:
            await _save_pipeline_success(db2, fingerprint)
            P("\nPipeline metadata saved (source fingerprint + last_run_at + SUCCESS).")

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
