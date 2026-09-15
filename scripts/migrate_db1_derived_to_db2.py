"""Migrate DB1 derived/analytical tables to DB2.

This script copies data only. It does NOT drop or truncate DB1 sources.
It is safe to run and re-run because archive tables use IF NOT EXISTS.

Tables migrated:
  - phase_a_evidence      -> DB2.phase_a_evidence_archive
  - phase_a_member_metrics -> DB2.phase_a_member_metrics_archive
  - phase_a_state_metrics -> DB2.phase_a_state_metrics_archive
  - phase_a_statistics    -> DB2.phase_a_statistics_archive
  - phase_a_trends        -> DB2.phase_a_trends_archive

The following are generated directly in DB2 by the intelligence backfill and
are NOT copied from DB1:
  - work_analysis, mla_work_analysis, ml_work_anomaly
  - category_metrics, fy_metrics, trends
"""
import asyncio
import asyncpg
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

ARCHIVE_TABLES = {
    "phase_a_evidence": "phase_a_evidence_archive",
    "phase_a_member_metrics": "phase_a_member_metrics_archive",
    "phase_a_state_metrics": "phase_a_state_metrics_archive",
    "phase_a_statistics": "phase_a_statistics_archive",
    "phase_a_trends": "phase_a_trends_archive",
}

P = lambda *a, **k: print(*a, **k, flush=True)


def _columns_sql(cols):
    return ", ".join(f'"{c}"' for c in cols)


async def main():
    P("=" * 70)
    P("GOVSENSE AI — DB1 -> DB2 DERIVED DATA MIGRATION (PHASE 5)")
    P("=" * 70)
    P(f"Started: {datetime.now(timezone.utc).isoformat()}")
    P("Connecting to DB1 and DB2...")

    db1 = await asyncpg.connect(dsn=os.environ["DATABASE_URL"], command_timeout=600)
    db2 = await asyncpg.connect(dsn=os.environ["DB2_DATABASE_URL"], command_timeout=600)
    await db1.execute("SET statement_timeout = '600000'")
    await db2.execute("SET statement_timeout = '600000'")
    P("Connected.")

    try:
        migrated = 0
        for source, dest in ARCHIVE_TABLES.items():
            P(f"\n[{source}] -> [{dest}]")

            cols = await db1.fetch("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=$1
                ORDER BY ordinal_position
            """, source)
            if not cols:
                P(f"  SOURCE TABLE NOT FOUND, skipping")
                continue

            col_defs = ", ".join(f'"{c["column_name"]}" {c["data_type"]}' for c in cols)
            col_names = [c["column_name"] for c in cols]

            P(f"  Creating destination table if not exists...")
            await db2.execute(f"""
                CREATE TABLE IF NOT EXISTS public.{dest} (
                    {col_defs}
                )
            """)

            source_count = await db1.fetchrow(f'SELECT COUNT(*) FROM public.{source}')
            before_count = await db2.fetchrow(f'SELECT COUNT(*) FROM public.{dest}')
            P(f"  Source rows: {source_count['count']}")
            P(f"  Destination rows before: {before_count['count']}")

            P(f"  Reading source data...")
            rows = await db1.fetch(f"SELECT {_columns_sql(col_names)} FROM public.{source}")
            P(f"  Read {len(rows)} rows")

            if rows:
                P(f"  Truncating destination and copying...")
                await db2.execute(f"TRUNCATE TABLE public.{dest}")
                batch_size = 1000
                copied = 0
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    await db2.copy_records_to_table(
                        dest,
                        records=[tuple(r[c] for c in col_names) for r in batch],
                        columns=col_names,
                    )
                    copied += len(batch)
                    P(f"    copied {copied}/{len(rows)}")

            after_count = await db2.fetchrow(f'SELECT COUNT(*) FROM public.{dest}')
            P(f"  Destination rows after: {after_count['count']}")
            if after_count["count"] != source_count["count"]:
                raise RuntimeError(f"Row count mismatch for {source}: {after_count['count']} != {source_count['count']}")
            P(f"  OK")
            migrated += 1

        P(f"\nMigrated {migrated} table(s). DB1 source tables were NOT modified.")
    finally:
        await db1.close()
        await db2.close()


if __name__ == "__main__":
    asyncio.run(main())
