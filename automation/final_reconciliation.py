#!/usr/bin/env python3
"""
GovSense final reconciliation report.

Produces one authoritative table of counts reconciling members, states,
works, scores, labels, ranks, ML models, allocations, etc.
"""

import asyncio
import asyncpg
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

P = lambda *a, **k: print(*a, **k, flush=True)


async def main():
    P("=" * 70)
    P("FINAL RECONCILIATION")
    P("=" * 70)
    P(f"Generated: {datetime.now(timezone.utc).isoformat()}")

    db1 = await asyncpg.connect(dsn=settings.DATABASE_URL, timeout=30)
    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=30)

    def q(pool, sql, *args):
        return pool.fetchval(sql, *args)

    P("\n{:<45} {:>12}".format("ITEM", "COUNT"))
    P("-" * 58)

    members_total = await q(db2, "SELECT COUNT(*) FROM public.member_metrics")
    P("{:<45} {:>12}".format("member_metrics", members_total))

    mi_total = await q(db2, "SELECT COUNT(*) FROM public.member_intelligence")
    P("{:<45} {:>12}".format("member_intelligence", mi_total))
    P("{:<45} {:>12}".format("  == member_intelligence = member_metrics", "PASS" if mi_total == members_total else "FAIL"))

    mp_count = await q(db2, "SELECT COUNT(*) FROM public.member_metrics WHERE member_type='MP'")
    mla_count = await q(db2, "SELECT COUNT(*) FROM public.member_metrics WHERE member_type='MLA'")
    P("{:<45} {:>12}".format("  MPs", mp_count))
    P("{:<45} {:>12}".format("  MLAs", mla_count))

    states_total = await q(db2, "SELECT COUNT(*) FROM public.state_metrics")
    si_total = await q(db2, "SELECT COUNT(*) FROM public.state_intelligence")
    P("{:<45} {:>12}".format("state_metrics", states_total))
    P("{:<45} {:>12}".format("state_intelligence", si_total))
    P("{:<45} {:>12}".format("  == state_intelligence = state_metrics", "PASS" if si_total == states_total else "FAIL"))

    works_total = await q(db2, "SELECT COUNT(*) FROM public.work_analysis") + await q(db2, "SELECT COUNT(*) FROM public.mla_work_analysis")
    P("{:<45} {:>12}".format("works (work_analysis + mla_work_analysis)", works_total))

    scored = await q(db2, "SELECT COUNT(*) FROM public.member_intelligence WHERE performance_score_100 IS NOT NULL")
    P("{:<45} {:>12}".format("scored members", scored))

    ranked = await q(db2, "SELECT COUNT(*) FROM public.member_intelligence WHERE national_rank IS NOT NULL")
    P("{:<45} {:>12}".format("national-ranked members", ranked))
    P("{:<45} {:>12}".format("  == ranked = scored", "PASS" if ranked == scored else "FAIL"))

    peer_ranked = await q(db2, "SELECT COUNT(*) FROM public.member_intelligence WHERE peer_rank IS NOT NULL")
    P("{:<45} {:>12}".format("peer-ranked members", peer_ranked))

    state_ranked = await q(db2, "SELECT COUNT(*) FROM public.state_intelligence WHERE rank IS NOT NULL")
    P("{:<45} {:>12}".format("state-ranked states", state_ranked))
    P("{:<45} {:>12}".format("  == state ranked = state total", "PASS" if state_ranked == states_total else "FAIL"))

    risk_members = await q(db2, "SELECT COUNT(*) FROM public.member_intelligence WHERE risk_level IS NOT NULL")
    risk_states = await q(db2, "SELECT COUNT(*) FROM public.state_intelligence WHERE risk_level IS NOT NULL")
    P("{:<45} {:>12}".format("members with risk", risk_members))
    P("{:<45} {:>12}".format("states with risk", risk_states))

    allocated = await q(db2, "SELECT COUNT(*) FROM public.member_metrics WHERE allocated_amount IS NOT NULL")
    positive_alloc = await q(db2, "SELECT COUNT(*) FROM public.member_metrics WHERE allocated_amount > 0")
    P("{:<45} {:>12}".format("members with allocated_amount", allocated))
    P("{:<45} {:>12}".format("members with positive allocated_amount", positive_alloc))

    # Labels
    P("\n--- Member label distribution ---")
    rows = await db2.fetch("""
        SELECT performance_label, COUNT(*) as c
        FROM public.member_intelligence
        GROUP BY performance_label
        ORDER BY c DESC
    """)
    for r in rows:
        P("{:<45} {:>12}".format(r['performance_label'], r['c']))

    P("\n--- State label distribution ---")
    rows = await db2.fetch("""
        SELECT performance_label, COUNT(*) as c
        FROM public.state_intelligence
        GROUP BY performance_label
        ORDER BY c DESC
    """)
    for r in rows:
        P("{:<45} {:>12}".format(r['performance_label'], r['c']))

    # ML models
    P("\n--- ML models ---")
    rows = await db2.fetch("SELECT model_name, status FROM public.model_registry ORDER BY model_name")
    for r in rows:
        P("{:<45} {:>12}".format(r['model_name'], r['status']))

    # Categories
    cat_count = await q(db2, "SELECT COUNT(*) FROM public.category_metrics")
    P("\n{:<45} {:>12}".format("category_metrics rows", cat_count))

    # FY / trends
    fy_count = await q(db2, "SELECT COUNT(*) FROM public.fy_metrics")
    trend_count = await q(db2, "SELECT COUNT(*) FROM public.trends")
    P("{:<45} {:>12}".format("fy_metrics rows", fy_count))
    P("{:<45} {:>12}".format("trends rows", trend_count))

    await db1.close()
    await db2.close()

    P("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
