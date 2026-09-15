"""Compute member_metrics from DB1 raw tables and DB2 work_analysis."""
import datetime
from typing import Dict, List, Any, Optional
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


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n == 1:
        return float(s[0])
    k = (n - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, n - 1)
    if f == c:
        return float(s[f])
    return float(s[f] * (c - k) + s[c] * (k - f))


async def _fetch_members(p1: asyncpg.Pool) -> List[Dict[str, Any]]:
    async with p1.acquire() as conn:
        await conn.execute("SET statement_timeout = '300000'")
        mps = await conn.fetch("""
            SELECT mp_id AS member_id, 'MP'::text AS member_type, mp_name AS member_name,
                   c.state_id, m.constituency_id, house_name, tenure, tenure_start_date, tenure_end_date
            FROM mps m
            LEFT JOIN constituencies c ON c.constituency_id = m.constituency_id
        """)
        mlas = await conn.fetch("""
            SELECT mla_id AS member_id, 'MLA'::text AS member_type, mla_name AS member_name,
                   c.state_id, m.constituency_id, house_name, tenure, tenure_start_date, tenure_end_date
            FROM mlas m
            LEFT JOIN constituencies c ON c.constituency_id = m.constituency_id
        """)
        return [dict(r) for r in mps] + [dict(r) for r in mlas]


async def _fetch_allocations(p1: asyncpg.Pool) -> Dict[int, Dict[str, Any]]:
    async with p1.acquire() as conn:
        mp_rows = await conn.fetch("""
            SELECT mp_id AS member_id, SUM(allocated_amount) AS allocated_amount
            FROM mp_allocations
            GROUP BY mp_id
        """)
        mla_rows = await conn.fetch("""
            SELECT mla_id AS member_id, SUM(allocated_amount) AS allocated_amount
            FROM mla_allocations
            GROUP BY mla_id
        """)
        result = {}
        for r in mp_rows:
            result[_safe_int(r["member_id"])] = {
                "allocated_amount": _safe_float(r["allocated_amount"]),
                "allocated_source": "ALLOCATION_TABLE",
                "allocated_confidence": "HIGH"
            }
        for r in mla_rows:
            result[_safe_int(r["member_id"])] = {
                "allocated_amount": _safe_float(r["allocated_amount"]),
                "allocated_source": "ALLOCATION_TABLE",
                "allocated_confidence": "HIGH"
            }
        return result


async def _fetch_work_analysis(p2: asyncpg.Pool, member_type: str) -> Dict[int, List[asyncpg.Record]]:
    table = "mla_work_analysis" if member_type == "MLA" else "work_analysis"
    async with p2.acquire() as conn:
        rows = await conn.fetch(f"SELECT * FROM {table}")
        result = {}
        for r in rows:
            mid = _safe_int(r["member_id"])
            result.setdefault(mid, []).append(r)
        return result


def _compute_member_metrics(member: asyncpg.Record, works: List[asyncpg.Record], alloc: Dict[str, Any]) -> Dict[str, Any]:
    total = len(works)
    recommended = sum(1 for w in works if w["recommendation_date"] is not None)
    sanctioned = sum(1 for w in works if w["sanction_date"] is not None)
    completed = sum(1 for w in works if w["status"] == "COMPLETED")
    ongoing = sum(1 for w in works if w["status"] == "ONGOING")
    pending = total - recommended

    rec_amts = [_safe_float(w["recommended_amount"]) for w in works]
    sanc_amts = [_safe_float(w["sanction_amount"]) for w in works]
    exp_amts = [_safe_float(w["expenditure_amount"]) for w in works]
    comp_amts = [_safe_float(w["completion_amount"]) for w in works]

    rec_total = sum(rec_amts)
    sanc_total = sum(sanc_amts)
    exp_total = sum(exp_amts)
    comp_total = sum(comp_amts)

    completion_rate = min(100.0, (completed / recommended * 100.0) if recommended > 0 else 0.0)
    sanction_rate = min(100.0, (sanctioned / recommended * 100.0) if recommended > 0 else 0.0)
    sanction_conversion = min(100.0, (completed / sanctioned * 100.0) if sanctioned > 0 else 0.0)

    allocated = _safe_float(alloc.get("allocated_amount"))
    allocated_source = alloc.get("allocated_source", "DERIVED")
    allocated_confidence = alloc.get("allocated_confidence", "MEDIUM")

    unspent = max(0.0, allocated - exp_total)
    fund_util = min(100.0, (exp_total / allocated * 100.0) if allocated > 0 else 0.0)
    exp_rate = min(100.0, (exp_total / sanc_total * 100.0) if sanc_total > 0 else 0.0)

    sanc_delays = [w["sanction_delay_days"] for w in works if w["sanction_delay_days"] is not None and w["sanction_delay_days"] >= 0]
    exec_days = [w["execution_days"] for w in works if w["execution_days"] is not None and w["execution_days"] >= 0]
    project_ages = [w["project_age_days"] for w in works if w["project_age_days"] is not None and w["project_age_days"] >= 0]
    max_age = max(project_ages) if project_ages else None

    overdue_1y = sum(1 for w in works if w["status"] == "ONGOING" and w["project_age_days"] and w["project_age_days"] > 365)
    overdue_2y = sum(1 for w in works if w["status"] == "ONGOING" and w["project_age_days"] and w["project_age_days"] > 730)

    flagged = sum(1 for w in works if w["risk_level"] in ("LOW", "MEDIUM", "HIGH"))
    high_risk = sum(1 for w in works if w["risk_level"] == "HIGH")
    medium_risk = sum(1 for w in works if w["risk_level"] == "MEDIUM")
    flagged_rate = (flagged / total * 100.0) if total > 0 else 0.0
    high_risk_rate = (high_risk / total * 100.0) if total > 0 else 0.0

    cost_anomaly = sum(1 for w in works if w["cost_status"] in ("HIGH", "VERY_HIGH"))
    duration_anomaly = sum(1 for w in works if w["duration_status"] in ("HIGH", "VERY_HIGH"))

    zero_work = total == 0
    low_sample = 0 < total < 5
    ranking_qualified = total >= 5 and not zero_work

    performance_classification = "INSUFFICIENT_DATA" if zero_work else ("LOW_SAMPLE" if low_sample else "STANDARD")

    # Initial scale score based on portfolio financial volume relative to allocation
    scale_score = 0.0
    if allocated > 0:
        scale_score = min(100.0, (sanc_total / allocated) * 100.0)

    return {
        "member_id": _safe_int(member["member_id"]),
        "member_type": member["member_type"],
        "member_name": member["member_name"],
        "state_id": _safe_int(member["state_id"]),
        "state_name": None,  # filled below
        "constituency_id": _safe_int(member["constituency_id"]),
        "house_name": member["house_name"],
                "tenure": member["tenure"],
                "tenure_start_date": str(member["tenure_start_date"]) if member["tenure_start_date"] else None,
                "tenure_end_date": str(member["tenure_end_date"]) if member["tenure_end_date"] else None,
        "total_works": total,
        "recommended_works": recommended,
        "sanctioned_works": sanctioned,
        "completed_works": completed,
        "ongoing_works": ongoing,
        "pending_works": pending,
        "completion_rate_pct": completion_rate,
        "sanction_rate_pct": sanction_rate,
        "sanction_conversion_pct": sanction_conversion,
        "allocated_amount": allocated,
        "recommended_amount": rec_total,
        "sanctioned_amount": sanc_total,
        "expenditure_amount": exp_total,
        "completion_amount": comp_total,
        "unspent_amount": unspent,
        "fund_utilization_pct": fund_util,
        "expenditure_rate_pct": exp_rate,
        "avg_work_cost": (sanc_total / total) if total > 0 else None,
        "median_work_cost": _median(sanc_amts),
        "avg_sanction_delay_days": (sum(sanc_delays) / len(sanc_delays)) if sanc_delays else None,
        "median_sanction_delay_days": _median(sanc_delays),
        "avg_execution_days": (sum(exec_days) / len(exec_days)) if exec_days else None,
        "median_execution_days": _median(exec_days),
        "avg_project_age_days": (sum(project_ages) / len(project_ages)) if project_ages else None,
        "max_project_age_days": max_age,
        "overdue_over_1_year": overdue_1y,
        "overdue_over_2_years": overdue_2y,
        "flagged_works": flagged,
        "high_risk_works": high_risk,
        "medium_risk_works": medium_risk,
        "flagged_rate_pct": flagged_rate,
        "high_risk_rate_pct": high_risk_rate,
        "cost_anomaly_works": cost_anomaly,
        "duration_anomaly_works": duration_anomaly,
        "anomaly_score": None,
        "anomaly_level": None,
        "confidence_level": None,
        "zero_work_member": zero_work,
        "low_sample_member": low_sample,
        "ranking_qualified": ranking_qualified,
        "performance_classification": performance_classification,
        "rank": None,
        "calculated_at": datetime.datetime.now(datetime.timezone.utc),
        "performance_score": None,
        "scale_score": scale_score,
        "performance_score_weighted": None,
        "allocated_source": allocated_source,
        "allocated_confidence": allocated_confidence,
    }


async def build_member_metrics() -> int:
    p1 = await db1_pool()
    p2 = await db2_pool()
    try:
        members = await _fetch_members(p1)
        allocs = await _fetch_allocations(p1)

        mp_analysis = await _fetch_work_analysis(p2, "MP")
        mla_analysis = await _fetch_work_analysis(p2, "MLA")

        # State names
        async with p1.acquire() as conn:
            states = {r["state_id"]: r["state_name"] for r in await conn.fetch("SELECT state_id, state_name FROM states")}

        rows = []
        for m in members:
            mid = _safe_int(m["member_id"])
            mtype = m["member_type"]
            works = (mp_analysis if mtype == "MP" else mla_analysis).get(mid, [])
            alloc = allocs.get(mid, {"allocated_amount": 0.0, "allocated_source": "DERIVED", "allocated_confidence": "MEDIUM"})
            rec = _compute_member_metrics(m, works, alloc)
            rec["state_name"] = states.get(rec["state_id"])
            rows.append(rec)

        columns = [
            "member_id", "member_type", "member_name", "state_id", "state_name", "constituency_id",
            "house_name", "tenure", "tenure_start_date", "tenure_end_date", "total_works",
            "recommended_works", "sanctioned_works", "completed_works", "ongoing_works", "pending_works",
            "completion_rate_pct", "sanction_rate_pct", "sanction_conversion_pct", "allocated_amount",
            "recommended_amount", "sanctioned_amount", "expenditure_amount", "completion_amount",
            "unspent_amount", "fund_utilization_pct", "expenditure_rate_pct", "avg_work_cost",
            "median_work_cost", "avg_sanction_delay_days", "median_sanction_delay_days", "avg_execution_days",
            "median_execution_days", "avg_project_age_days", "max_project_age_days", "overdue_over_1_year",
            "overdue_over_2_years", "flagged_works", "high_risk_works", "medium_risk_works", "flagged_rate_pct",
            "high_risk_rate_pct", "cost_anomaly_works", "duration_anomaly_works", "anomaly_score", "anomaly_level",
            "confidence_level", "zero_work_member", "low_sample_member", "ranking_qualified",
            "performance_classification", "rank", "calculated_at", "performance_score", "scale_score",
            "performance_score_weighted", "allocated_source", "allocated_confidence"
        ]

        async with p2.acquire() as conn:
            await conn.execute("TRUNCATE TABLE member_metrics RESTART IDENTITY CASCADE")
            if rows:
                values = [tuple(r.get(c) for c in columns) for r in rows]
                batch_size = 500
                inserted = 0
                for i in range(0, len(values), batch_size):
                    batch = values[i:i + batch_size]
                    await conn.copy_records_to_table("member_metrics", records=batch, columns=columns)
                    inserted += len(batch)
        return len(rows)
    finally:
        await p1.close()
        await p2.close()
