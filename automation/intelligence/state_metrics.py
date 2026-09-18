"""Compute state_metrics from DB2 member_metrics and work_analysis."""
import datetime
from typing import Dict, List, Any
import asyncpg
from automation.intelligence.database import db1_pool, db2_pool


def _safe_int(val) -> int:
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def _safe_float(val) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _median(values: List[float]) -> Any:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


async def _fetch_states(p1: asyncpg.Pool) -> List[asyncpg.Record]:
    async with p1.acquire() as conn:
        return list(await conn.fetch("SELECT state_id, state_name FROM states"))


async def build_state_metrics() -> int:
    p1 = await db1_pool()
    p2 = await db2_pool()
    try:
        states = await _fetch_states(p1)
        async with p2.acquire() as conn:
            members = await conn.fetch("SELECT * FROM member_metrics")
            mp_works = await conn.fetch("SELECT * FROM work_analysis")
            mla_works = await conn.fetch("SELECT * FROM mla_work_analysis")

        member_by_state: Dict[int, List[asyncpg.Record]] = {}
        for m in members:
            sid = _safe_int(m["state_id"])
            member_by_state.setdefault(sid, []).append(m)

        works_by_state: Dict[int, List[asyncpg.Record]] = {}
        for w in list(mp_works) + list(mla_works):
            sid = _safe_int(w["state_id"])
            works_by_state.setdefault(sid, []).append(w)

        rows = []
        for s in states:
            sid = _safe_int(s["state_id"])
            ms = member_by_state.get(sid, [])
            ws = works_by_state.get(sid, [])

            mp_count = sum(1 for m in ms if m["member_type"] == "MP")
            mla_count = sum(1 for m in ms if m["member_type"] == "MLA")
            active = sum(1 for m in ms if m["total_works"] > 0)

            total = len(ws)
            rec = sum(1 for w in ws if w["recommendation_date"] is not None)
            sanc = sum(1 for w in ws if w["sanction_date"] is not None)
            comp = sum(1 for w in ws if w["status"] == "COMPLETED")
            ongoing = sum(1 for w in ws if w["status"] == "ONGOING")
            pending = total - rec

            rec_amt = sum(_safe_float(w["recommended_amount"]) for w in ws)
            sanc_amt = sum(_safe_float(w["sanction_amount"]) for w in ws)
            exp_amt = sum(_safe_float(w["expenditure_amount"]) for w in ws)
            comp_amt = sum(_safe_float(w["completion_amount"]) for w in ws)

            allocated = sum(_safe_float(m["allocated_amount"]) for m in ms)
            unspent = max(0.0, allocated - exp_amt)

            sanc_amts = [_safe_float(w["sanction_amount"]) for w in ws]
            sanc_delays = [w["sanction_delay_days"] for w in ws if w["sanction_delay_days"] is not None and w["sanction_delay_days"] >= 0]
            exec_days = [w["execution_days"] for w in ws if w["execution_days"] is not None and w["execution_days"] >= 0]
            project_ages = [w["project_age_days"] for w in ws if w["project_age_days"] is not None and w["project_age_days"] >= 0]

            overdue_1y = sum(1 for w in ws if w["status"] == "ONGOING" and w["project_age_days"] and w["project_age_days"] > 365)
            overdue_2y = sum(1 for w in ws if w["status"] == "ONGOING" and w["project_age_days"] and w["project_age_days"] > 730)

            flagged = sum(1 for w in ws if w["risk_level"] in ("LOW", "MEDIUM", "HIGH"))
            high_risk = sum(1 for w in ws if w["risk_level"] == "HIGH")
            risk_rate = (flagged / total * 100.0) if total > 0 else 0.0
            cost_anomaly = sum(1 for w in ws if w["cost_status"] in ("HIGH", "VERY_HIGH"))
            duration_anomaly = sum(1 for w in ws if w["duration_status"] in ("HIGH", "VERY_HIGH"))

            # scale_score is computed by performance.py as percentile rank of total_works
            scale_score = None

            rows.append({
                "state_id": sid,
                "state_name": s["state_name"],
                "total_members": len(ms),
                "mp_count": mp_count,
                "mla_count": mla_count,
                "active_members": active,
                "total_works": total,
                "recommended_works": rec,
                "sanctioned_works": sanc,
                "completed_works": comp,
                "ongoing_works": ongoing,
                "pending_works": pending,
                "completion_rate_pct": min(100.0, (comp / rec * 100.0) if rec > 0 else 0.0),
                "sanction_rate_pct": min(100.0, (sanc / rec * 100.0) if rec > 0 else 0.0),
                "allocated_amount": allocated,
                "recommended_amount": rec_amt,
                "sanctioned_amount": sanc_amt,
                "expenditure_amount": exp_amt,
                "completion_amount": comp_amt,
                "unspent_amount": unspent,
                "fund_utilization_pct": min(100.0, (exp_amt / allocated * 100.0) if allocated > 0 else 0.0),
                "expenditure_rate_pct": min(100.0, (exp_amt / sanc_amt * 100.0) if sanc_amt > 0 else 0.0),
                "avg_work_cost": (sanc_amt / total) if total > 0 else None,
                "median_work_cost": _median(sanc_amts),
                "avg_sanction_delay_days": (sum(sanc_delays) / len(sanc_delays)) if sanc_delays else None,
                "median_sanction_delay_days": _median(sanc_delays),
                "avg_execution_days": (sum(exec_days) / len(exec_days)) if exec_days else None,
                "median_execution_days": _median(exec_days),
                "avg_project_age_days": (sum(project_ages) / len(project_ages)) if project_ages else None,
                "overdue_over_1_year": overdue_1y,
                "overdue_over_2_years": overdue_2y,
                "flagged_works": flagged,
                "high_risk_works": high_risk,
                "risk_rate_pct": risk_rate,
                "cost_anomaly_works": cost_anomaly,
                "duration_anomaly_works": duration_anomaly,
                "anomaly_score": None,
                "anomaly_level": None,
                "confidence_level": None,
                "performance_classification": "STANDARD" if len(ms) > 0 else "INSUFFICIENT_DATA",
                "rank": None,
                "calculated_at": datetime.datetime.now(datetime.timezone.utc),
                "performance_score": None,
                "scale_score": scale_score,
                "performance_score_weighted": None,
                "allocated_source": "AGGREGATED",
                "allocated_confidence": "HIGH",
            })

        columns = [
            "state_id", "state_name", "total_members", "mp_count", "mla_count", "active_members",
            "total_works", "recommended_works", "sanctioned_works", "completed_works", "ongoing_works",
            "pending_works", "completion_rate_pct", "sanction_rate_pct", "allocated_amount",
            "recommended_amount", "sanctioned_amount", "expenditure_amount", "completion_amount",
            "unspent_amount", "fund_utilization_pct", "expenditure_rate_pct", "avg_work_cost",
            "median_work_cost", "avg_sanction_delay_days", "median_sanction_delay_days", "avg_execution_days",
            "median_execution_days", "avg_project_age_days", "overdue_over_1_year", "overdue_over_2_years",
            "flagged_works", "high_risk_works", "risk_rate_pct", "cost_anomaly_works", "duration_anomaly_works",
            "anomaly_score", "anomaly_level", "confidence_level", "performance_classification", "rank",
            "calculated_at", "performance_score", "scale_score", "performance_score_weighted", "allocated_source",
            "allocated_confidence"
        ]

        async with p2.acquire() as conn:
            await conn.execute("TRUNCATE TABLE state_metrics RESTART IDENTITY CASCADE")
            if rows:
                values = [tuple(r.get(c) for c in columns) for r in rows]
                batch_size = 500
                inserted = 0
                for i in range(0, len(values), batch_size):
                    batch = values[i:i + batch_size]
                    await conn.copy_records_to_table("state_metrics", records=batch, columns=columns)
                    inserted += len(batch)
        return len(rows)
    finally:
        await p1.close()
        await p2.close()
