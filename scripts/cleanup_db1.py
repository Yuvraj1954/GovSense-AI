"""DB1 cleanup after DB2 migration.

This script removes stale derived analytical tables from DB1 after they have
been safely migrated/regenerated to DB2.

SAFETY:
  - Run only after Phase 5 migration is verified.
  - By default prints the planned actions. Use --execute to apply.
  - Renames tables to z_deprecated_* before dropping (two-step safety).
  - Duplicate indexes are dropped only if they are confirmed redundant.
"""
import argparse
import asyncio
import asyncpg
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DERIVED_TABLES = [
    "work_analysis",
    "mla_work_analysis",
    "ml_work_anomaly",
    "phase_a_evidence",
    "phase_a_member_metrics",
    "phase_a_state_metrics",
    "phase_a_statistics",
    "phase_a_trends",
    "category_metrics",
    "fy_metrics",
]

DUPLICATE_INDEXES = [
    ("idx_work_expenditures_work_id", "redundant with composite idx_work_expenditures_work_id_amount"),
    ("idx_work_sanctions_work_id", "redundant with composite idx_work_sanctions_work_id_amount"),
    ("idx_work_recommendations_work_id", "redundant with composite idx_work_recommendations_work_id_amount"),
    ("idx_works_constituency", "redundant with idx_works_state_constituency"),
]

P = lambda *a, **k: print(*a, **k, flush=True)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Actually apply changes")
    parser.add_argument("--drop-deprecated", action="store_true", help="Drop already-renamed z_deprecated_* tables")
    parser.add_argument("--vacuum", action="store_true", help="Run VACUUM FULL after cleanup")
    args = parser.parse_args()

    P("=" * 70)
    P("GOVSENSE AI — DB1 CLEANUP (PHASE 6)")
    P("=" * 70)
    P(f"Started: {datetime.now(timezone.utc).isoformat()}")
    P(f"Mode: execute={args.execute}, drop_deprecated={args.drop_deprecated}, vacuum={args.vacuum}")
    P("Connecting to DB1...")

    db1 = await asyncpg.connect(dsn=os.environ["DATABASE_URL"], command_timeout=600)
    await db1.execute("SET statement_timeout = '600000'")
    P("Connected.")

    try:
        # Step 1: rename derived tables
        P("\n--- Derived table rename plan ---")
        renamed = 0
        for tbl in DERIVED_TABLES:
            deprecated = f"z_deprecated_{tbl}"
            exists = await db1.fetchrow(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=$1", tbl
            )
            if not exists:
                P(f"  {tbl}: not found, skip")
                continue
            dep_exists = await db1.fetchrow(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=$1", deprecated
            )
            if dep_exists:
                P(f"  {tbl}: already renamed to {deprecated}")
                if args.drop_deprecated and args.execute:
                    P(f"    -> DROPPING {deprecated}")
                    await db1.execute(f'DROP TABLE public."{deprecated}" CASCADE')
                    P(f"    -> DROPPED")
                continue
            P(f"  {tbl}: RENAME TO {deprecated}")
            if args.execute:
                P(f"    -> executing rename...")
                await db1.execute(f'ALTER TABLE public."{tbl}" RENAME TO "{deprecated}"')
                P(f"    -> renamed")
            renamed += 1

        # Step 2: drop duplicate indexes
        P("\n--- Duplicate index drop plan ---")
        dropped = 0
        for idx, reason in DUPLICATE_INDEXES:
            exists = await db1.fetchrow(
                "SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=$1", idx
            )
            if not exists:
                P(f"  {idx}: not found, skip")
                continue
            P(f"  {idx}: DROP ({reason})")
            if args.execute:
                P(f"    -> executing drop...")
                await db1.execute(f'DROP INDEX IF EXISTS public."{idx}"')
                P(f"    -> dropped")
            dropped += 1

        # Step 3: vacuum
        if args.vacuum:
            P("\n--- VACUUM FULL ---")
            if args.execute:
                P("  Running VACUUM FULL...")
                await db1.execute("VACUUM FULL")
                P("  VACUUM FULL completed")
            else:
                P("  would run VACUUM FULL")

        # Final size
        row = await db1.fetchrow("SELECT pg_size_pretty(pg_database_size(current_database())) as sz")
        P(f"\nDB1 final size: {row['sz']}")
        P(f"Tables renamed: {renamed}, Indexes dropped: {dropped}")

        if not args.execute:
            P("\nThis was a dry run. Use --execute to apply changes.")
        else:
            P("\nCleanup applied.")
    finally:
        await db1.close()


if __name__ == "__main__":
    asyncio.run(main())
