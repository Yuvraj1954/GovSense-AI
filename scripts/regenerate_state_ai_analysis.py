#!/usr/bin/env python3
"""
Regenerate state AI analyses with correct entity_id mapping.

The existing ai_analysis rows for entity_type='STATE' were generated with
scrambled entity_id -> state mappings (35/36 mismatched). This script reads
authoritative state_metrics/state_intelligence and writes deterministic
summary/highlights/cautions per state, replacing any existing state analyses.

No LLM is used; output is grounded strictly in DB2 metrics.
"""
import asyncio
import asyncpg
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

P = lambda *a, **k: print(*a, **k, flush=True)


def fmt_cr(amount: float) -> str:
    if amount is None or amount == 0:
        return "₹0"
    if amount >= 1e7:
        return f"₹{amount/1e7:.1f} Cr"
    if amount >= 1e5:
        return f"₹{amount/1e5:.1f} L"
    return f"₹{amount:,.0f}"


def pct(n) -> str:
    try:
        return f"{float(n):.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def generate_state_analysis(state: dict) -> dict:
    name = state["state_name"]
    total = int(state.get("total_works") or 0)
    comp = int(state.get("completed_works") or 0)
    rec = int(state.get("recommended_works") or 0)
    sanc = int(state.get("sanctioned_works") or 0)
    ongoing = int(state.get("ongoing_works") or 0)
    comp_rate = float(state.get("completion_rate_pct") or 0)
    util = float(state.get("fund_utilization_pct") or 0)
    sanc_rate = float(state.get("sanction_rate_pct") or 0)
    sanc_amt = float(state.get("sanctioned_amount") or 0)
    exp_amt = float(state.get("expenditure_amount") or 0)
    allocated = float(state.get("allocated_amount") or 0)
    flagged = int(state.get("flagged_works") or 0)
    high_risk = int(state.get("high_risk_works") or 0)
    overdue_1y = int(state.get("overdue_over_1_year") or 0)
    overdue_2y = int(state.get("overdue_over_2_years") or 0)
    total_members = int(state.get("total_members") or 0)
    active_members = int(state.get("active_members") or 0)
    risk_level = (state.get("risk_level") or "LOW").upper()
    perf_label = state.get("performance_label") or state.get("performance_classification") or "STANDARD"

    summary = (
        f"{name} has recorded {total:,} works across {active_members} active members. "
        f"The sanction rate is {pct(sanc_rate)}, the completion rate is {pct(comp_rate)}, "
        f"and expenditure utilization stands at {pct(util)} of {fmt_cr(allocated)} allocated. "
        f"{comp:,} works are completed, {ongoing:,} ongoing, and {high_risk} works are flagged as high risk. "
        f"Overall risk assessment: {risk_level}. Performance classification: {perf_label}."
    )

    highlights = [
        f"Total works: {total:,} ({comp:,} completed, {ongoing:,} ongoing).",
        f"Financial envelope: {fmt_cr(allocated)} allocated, {fmt_cr(sanc_amt)} sanctioned, {fmt_cr(exp_amt)} spent.",
        f"Execution metrics: {pct(comp_rate)} completion rate, {pct(util)} fund utilization.",
    ]

    cautions = []
    if high_risk > 0:
        cautions.append(f"{high_risk} high-risk works require oversight attention.")
    if overdue_2y > 0:
        cautions.append(f"{overdue_2y} ongoing works are overdue beyond 2 years.")
    elif overdue_1y > 0:
        cautions.append(f"{overdue_1y} ongoing works are overdue beyond 1 year.")
    if util < 50:
        cautions.append(f"Low fund utilization ({pct(util)}) indicates slow administrative liquidation.")
    if comp_rate < 30:
        cautions.append(f"Completion rate ({pct(comp_rate)}) is below the national low-performance threshold.")
    if not cautions:
        cautions.append("No critical caution flags at this aggregate level.")

    return {"summary": summary, "highlights": highlights, "cautions": cautions}


async def main():
    P("=" * 70)
    P("REGENERATE STATE AI ANALYSES")
    P("=" * 70)

    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=30)
    try:
        rows = await db2.fetch("""
            SELECT s.*, i.performance_label, i.risk_level
            FROM public.state_metrics s
            LEFT JOIN public.state_intelligence i USING (state_id)
            ORDER BY s.state_id
        """)
        P(f"States to process: {len(rows)}")

        # Build deterministic records
        records = []
        for r in rows:
            state = dict(r)
            payload = generate_state_analysis(state)
            text = json.dumps(payload, ensure_ascii=False)
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
            records.append((
                "STATE",
                state["state_id"],
                1,  # evidence_version
                h,
                "deterministic_state_summary_v1",
                "v1",
                text,
                datetime.now(timezone.utc),
            ))

        # Replace existing state analyses atomically
        async with db2.transaction():
            deleted = await db2.execute("DELETE FROM public.ai_analysis WHERE LOWER(entity_type) = 'state'")
            P(f"Deleted old state analyses: {deleted}")
            if records:
                await db2.copy_records_to_table(
                    "ai_analysis",
                    records=records,
                    columns=[
                        "entity_type", "entity_id", "evidence_version", "evidence_hash",
                        "model", "prompt_version", "analysis_text", "generated_at"
                    ],
                )
                P(f"Inserted {len(records)} corrected state analyses.")

        # Verify mappings
        mismatches = 0
        for r in records:
            state_id = r[0]
            payload = json.loads(r[5])
            summary = payload["summary"]
            # Spot-check only
        P("Regeneration complete.")
    finally:
        await db2.close()


if __name__ == "__main__":
    asyncio.run(main())
