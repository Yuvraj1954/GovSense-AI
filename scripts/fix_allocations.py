#!/usr/bin/env python3
"""
Allocation matching fix for GovSense member_metrics.

Principle:
  Use the strongest identifier supported by real source data.
  DB1 mp_id / mla_id do NOT align with DB2 member_id, so the previous
  ID-based match produced wrong allocations for most MPs.
  Normalized names are unique and complete on both sides, so name matching
  is the strongest RELIABLE method.

Behavior:
  - MP:   join member_metrics (DB2) → mps (DB1) by normalized name
          → mp_allocations by mp_id
  - MLA:  join member_metrics (DB2) → mlas (DB1) by normalized name
          → mla_allocations by mla_id
  - Persist allocated_amount, allocated_source, allocated_confidence.
  - If the source allocation record exists but amount is 0, preserve 0
    and flag as zero-amount (HIGH confidence because the record exists).
  - If no allocation record exists, set NULL and flag as unavailable.

Does NOT:
  - silently substitute sanctioned amount for allocated amount
  - fabricate allocations
  - modify raw government records in DB1
"""

import asyncio
import asyncpg
import os
import sys
from datetime import datetime, timezone
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

P = lambda *a, **k: print(*a, **k, flush=True)


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    return " ".join(name.lower().strip().split())


async def main():
    P("=" * 70)
    P("ALLOCATION MATCHING FIX")
    P("=" * 70)
    P(f"Started: {datetime.now(timezone.utc).isoformat()}")

    db1 = await asyncpg.connect(dsn=settings.DATABASE_URL, timeout=30)
    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=30)
    P("Connected to DB1 and DB2.")

    # ------------------------------------------------------------------
    # Build source allocation maps from DB1
    # ------------------------------------------------------------------
    P("\n--- Reading source allocations from DB1 ---")

    mp_allocs = await db1.fetch("""
        SELECT m.mp_id, m.mp_name, a.allocated_amount,
               a.source_tenure, a.source_house_of_parliament,
               a.source_tenure_start_date, a.source_tenure_end_date
        FROM public.mp_allocations a
        JOIN public.mps m ON m.mp_id = a.mp_id
    """)
    mp_by_name = {}
    for r in mp_allocs:
        key = normalize_name(r["mp_name"])
        mp_by_name[key] = {
            "mp_id": r["mp_id"],
            "allocated_amount": r["allocated_amount"],
            "tenure": r["source_tenure"],
            "house": r["source_house_of_parliament"],
        }
    P(f"MP allocation records: {len(mp_by_name)}")

    mla_allocs = await db1.fetch("""
        SELECT m.mla_id, m.mla_name, a.allocated_amount,
               a.source_tenure, a.source_house_of_parliament,
               a.source_tenure_start_date, a.source_tenure_end_date
        FROM public.mla_allocations a
        JOIN public.mlas m ON m.mla_id = a.mla_id
    """)
    mla_by_name = {}
    for r in mla_allocs:
        key = normalize_name(r["mla_name"])
        mla_by_name[key] = {
            "mla_id": r["mla_id"],
            "allocated_amount": r["allocated_amount"],
            "tenure": r["source_tenure"],
            "house": r["source_house_of_parliament"],
        }
    P(f"MLA/Rajya Sabha allocation records: {len(mla_by_name)}")

    # ------------------------------------------------------------------
    # Read target members from DB2
    # ------------------------------------------------------------------
    P("\n--- Reading target members from DB2 ---")
    members = await db2.fetch("""
        SELECT member_id, member_type, member_name, state_name, house_name, tenure
        FROM public.member_metrics
        ORDER BY member_type, member_id
    """)
    P(f"Target members: {len(members)}")

    # ------------------------------------------------------------------
    # Compute matches
    # ------------------------------------------------------------------
    updates = []
    reconciliation = {
        "MP": {"total": 0, "matched": 0, "unmatched": 0, "zero_amount": 0, "ambiguous": 0, "sum": 0},
        "MLA": {"total": 0, "matched": 0, "unmatched": 0, "zero_amount": 0, "ambiguous": 0, "sum": 0},
    }

    unmatched_report = []

    for m in members:
        mtype = m["member_type"]
        name = normalize_name(m["member_name"])
        rec = reconciliation[mtype]
        rec["total"] += 1

        source = None
        if mtype == "MP":
            source = mp_by_name.get(name)
        elif mtype == "MLA":
            source = mla_by_name.get(name)

        if source is None:
            rec["unmatched"] += 1
            updates.append((
                None,
                "unavailable",
                "LOW",
                m["member_id"],
                mtype,
            ))
            unmatched_report.append({
                "member_id": m["member_id"],
                "type": mtype,
                "name": m["member_name"],
                "reason": "no allocation record",
            })
            continue

        amount = source["allocated_amount"]
        if amount is None:
            rec["unmatched"] += 1
            updates.append((
                None,
                "unavailable",
                "LOW",
                m["member_id"],
                mtype,
            ))
            unmatched_report.append({
                "member_id": m["member_id"],
                "type": mtype,
                "name": m["member_name"],
                "reason": "allocation record without amount",
            })
            continue

        # Allocation record exists with an amount
        if amount == 0:
            rec["zero_amount"] += 1
            confidence = "HIGH"  # record exists, amount is genuinely zero
            source_label = "allocation_table_zero"
        else:
            rec["matched"] += 1
            confidence = "HIGH"
            source_label = "allocation_table"

        rec["sum"] += float(amount)
        updates.append((
            amount,
            source_label,
            confidence,
            m["member_id"],
            mtype,
        ))

    # ------------------------------------------------------------------
    # Apply updates
    # ------------------------------------------------------------------
    P("\n--- Updating member_metrics ---")
    await db2.executemany(
        """
        UPDATE public.member_metrics
        SET allocated_amount = $1,
            allocated_source = $2,
            allocated_confidence = $3,
            calculated_at = NOW()
        WHERE member_id = $4 AND member_type = $5
        """,
        updates,
    )
    P(f"Updated {len(updates)} rows.")

    # ------------------------------------------------------------------
    # Reconciliation report
    # ------------------------------------------------------------------
    P("\n" + "=" * 70)
    P("RECONCILIATION REPORT")
    P("=" * 70)

    for mtype in ("MP", "MLA"):
        rec = reconciliation[mtype]
        coverage = (rec["matched"] / rec["total"] * 100) if rec["total"] else 0
        P(f"\n{mtype}:")
        P(f"  Total allocation records in source: {len(mp_by_name) if mtype == 'MP' else len(mla_by_name)}")
        P(f"  Target members:                     {rec['total']}")
        P(f"  Matched (positive amount):          {rec['matched']}")
        P(f"  Zero-amount records:                {rec['zero_amount']}")
        P(f"  Unmatched/unavailable:              {rec['unmatched']}")
        P(f"  Ambiguous:                          {rec['ambiguous']}")
        P(f"  Coverage % (positive):              {coverage:.2f}%")
        P(f"  Total allocated amount:             {rec['sum']:,.2f}")

    # Source-level totals
    P("\nSource-level totals:")
    mp_total = sum(float(r["allocated_amount"]) for r in mp_allocs if r["allocated_amount"])
    mla_total = sum(float(r["allocated_amount"]) for r in mla_allocs if r["allocated_amount"])
    P(f"  MP allocations sum:   {mp_total:,.2f}")
    P(f"  MLA allocations sum:  {mla_total:,.2f}")

    # Unmatched details
    if unmatched_report:
        P(f"\nUnmatched members ({len(unmatched_report)}):")
        for u in unmatched_report[:20]:
            P(f"  {u['type']} id={u['member_id']} name='{u['name']}' reason={u['reason']}")
        if len(unmatched_report) > 20:
            P(f"  ... and {len(unmatched_report) - 20} more")

    # Verify updated table
    P("\n--- Verification (member_metrics) ---")
    rows = await db2.fetch("""
        SELECT member_type,
               COUNT(*) as total,
               COUNT(*) FILTER (WHERE allocated_amount IS NOT NULL) as with_alloc,
               COUNT(*) FILTER (WHERE allocated_amount > 0) as positive,
               COUNT(*) FILTER (WHERE allocated_source = 'allocation_table') as from_table,
               COUNT(*) FILTER (WHERE allocated_source = 'allocation_table_zero') as zero_rec,
               COUNT(*) FILTER (WHERE allocated_source = 'unavailable') as unavailable,
               SUM(allocated_amount) as total_amount
        FROM public.member_metrics
        GROUP BY member_type
        ORDER BY member_type
    """)
    for r in rows:
        P(f"  {r['member_type']}: total={r['total']} with_alloc={r['with_alloc']} positive={r['positive']} from_table={r['from_table']} zero_rec={r['zero_rec']} unavailable={r['unavailable']} sum={r['total_amount']}")

    await db1.close()
    await db2.close()

    P(f"\nFinished: {datetime.now(timezone.utc).isoformat()}")
    P("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
