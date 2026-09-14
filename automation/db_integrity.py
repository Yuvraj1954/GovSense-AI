#!/usr/bin/env python3
"""
GovSense database integrity check.

Verifies DB1/DB2 structural integrity, orphan rows, invalid enums, and
impossible values.
"""

import asyncio
import asyncpg
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

P = lambda *a, **k: print(*a, **k, flush=True)


async def table_sizes(pool, db_name):
    P(f"\n--- {db_name} table sizes ---")
    rows = await pool.fetch("""
        SELECT relname as table_name, pg_size_pretty(pg_total_relation_size(c.oid)) as total_size
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
        ORDER BY pg_total_relation_size(c.oid) DESC
        LIMIT 20
    """)
    for r in rows:
        P(f"  {r['table_name']}: {r['total_size']}")


async def run_check(pool, name, query, expected_zero=True):
    row = await pool.fetchrow(query)
    val = row[0] if row else 0
    ok = (val == 0) if expected_zero else (val > 0)
    status = "PASS" if ok else "FAIL"
    P(f"  [{status}] {name}: {val}")
    return ok


async def main():
    P("=" * 70)
    P("DATABASE INTEGRITY CHECK")
    P("=" * 70)
    P(f"Started: {datetime.now(timezone.utc).isoformat()}")

    db1 = await asyncpg.connect(dsn=settings.DATABASE_URL, timeout=30)
    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=30)

    await table_sizes(db1, "DB1")
    await table_sizes(db2, "DB2")

    P("\n--- Integrity checks ---")
    all_ok = True

    checks_db2 = [
        ("orphan member_intelligence rows", """
            SELECT COUNT(*) FROM public.member_intelligence mi
            LEFT JOIN public.member_metrics mm ON mi.member_id = mm.member_id AND mi.member_type = mm.member_type
            WHERE mm.member_id IS NULL
        """),
        ("orphan state_intelligence rows", """
            SELECT COUNT(*) FROM public.state_intelligence si
            LEFT JOIN public.state_metrics sm ON si.state_id = sm.state_id
            WHERE sm.state_id IS NULL
        """),
        ("duplicate member identities", """
            SELECT COUNT(*) FROM (
                SELECT member_id, member_type FROM public.member_metrics
                GROUP BY member_id, member_type HAVING COUNT(*) > 1
            ) t
        """),
        ("duplicate state identities", """
            SELECT COUNT(*) FROM (
                SELECT state_id FROM public.state_metrics
                GROUP BY state_id HAVING COUNT(*) > 1
            ) t
        """),
        ("NULL authoritative scores", """
            SELECT COUNT(*) FROM public.member_intelligence
            WHERE performance_score_100 IS NULL
              AND performance_label NOT IN ('NO_DATA', 'INSUFFICIENT_DATA')
        """),
        ("invalid member national_rank", "SELECT COUNT(*) FROM public.member_intelligence WHERE national_rank < 1"),
        ("invalid member peer_rank", "SELECT COUNT(*) FROM public.member_intelligence WHERE peer_rank < 1"),
        ("invalid state rank", "SELECT COUNT(*) FROM public.state_intelligence WHERE rank < 1"),
        ("invalid member labels", """
            SELECT COUNT(*) FROM public.member_intelligence
            WHERE performance_label NOT IN (
                'EXCEPTIONAL','PERFORMER','STABLE','NEEDS_ATTENTION','UNDERPERFORMER','NO_DATA','INSUFFICIENT_DATA'
            )
        """),
        ("invalid state labels", """
            SELECT COUNT(*) FROM public.state_intelligence
            WHERE performance_label NOT IN (
                'EXCEPTIONAL','PERFORMER','STABLE','NEEDS_ATTENTION','UNDERPERFORMER'
            )
        """),
        ("invalid member risk levels", """
            SELECT COUNT(*) FROM public.member_intelligence
            WHERE risk_level NOT IN ('LOW','MODERATE','HIGH','CRITICAL')
        """),
        ("invalid state risk levels", """
            SELECT COUNT(*) FROM public.state_intelligence
            WHERE risk_level NOT IN ('LOW','MODERATE','HIGH','CRITICAL')
        """),
        ("impossible percentages", """
            SELECT COUNT(*) FROM public.member_metrics
            WHERE completion_rate_pct < 0 OR completion_rate_pct > 100
               OR fund_utilization_pct < 0 OR fund_utilization_pct > 100
        """),
        ("negative financial values", """
            SELECT COUNT(*) FROM public.member_metrics
            WHERE total_works < 0 OR recommended_works < 0 OR sanctioned_works < 0
               OR completed_works < 0 OR allocated_amount < 0 OR recommended_amount < 0
               OR sanctioned_amount < 0 OR expenditure_amount < 0
        """),
    ]

    for name, query in checks_db2:
        if not await run_check(db2, name, query):
            all_ok = False

    await db1.close()
    await db2.close()

    P(f"\nOverall DB integrity: {'PASS' if all_ok else 'FAIL'}")
    P("=" * 70)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
