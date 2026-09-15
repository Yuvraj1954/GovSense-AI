"""Compute national statistics, overall metrics, trends, category and FY metrics."""
import datetime
from typing import List, Dict, Any
import asyncpg
from automation.intelligence.database import db1_pool, db2_pool


def _safe_float(val) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _safe_int(val) -> int:
    try:
        return int(val) if val is not None else 0
    except (TypeError, ValueError):
        return 0


def _median(values: List[float]) -> Any:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _percentile(values: List[float], p: float) -> Any:
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


def _std(values: List[float]) -> Any:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return var ** 0.5


def _iqr(values: List[float]) -> Any:
    p75 = _percentile(values, 75)
    p25 = _percentile(values, 25)
    if p75 is None or p25 is None:
        return None
    return p75 - p25


async def build_national_statistics() -> int:
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM member_metrics WHERE total_works > 0")

            metrics = {
                "performance_score": [],
                "completion_rate_pct": [],
                "fund_utilization_pct": [],
                "sanction_rate_pct": [],
                "flagged_rate_pct": [],
                "avg_execution_days": [],
                "avg_project_age_days": [],
            }
            for r in rows:
                if r["total_works"] > 0:
                    for k in metrics:
                        v = _safe_float(r[k])
                        metrics[k].append(v)

            records = []
            for metric_name, values in metrics.items():
                if not values:
                    continue
                records.append((
                    metric_name, "national", len(values),
                    sum(values) / len(values), _std(values),
                    min(values), _percentile(values, 25), _median(values),
                    _percentile(values, 75), _percentile(values, 90), _percentile(values, 95),
                    max(values), _iqr(values), datetime.datetime.now(datetime.timezone.utc)
                ))

            await conn.execute("TRUNCATE TABLE national_statistics RESTART IDENTITY CASCADE")
            if records:
                cols = [
                    "metric_name", "scope", "sample_size", "mean", "std_dev", "minimum",
                    "p25", "median", "p75", "p90", "p95", "maximum", "iqr", "calculated_at"
                ]
                batch_size = 500
                for i in range(0, len(records), batch_size):
                    await conn.copy_records_to_table(
                        "national_statistics",
                        records=records[i:i + batch_size],
                        columns=cols,
                    )
            return len(records)
    finally:
        await p2.close()


async def build_overall_metrics() -> int:
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM member_metrics")
            mp_works = await conn.fetch("SELECT * FROM work_analysis")
            mla_works = await conn.fetch("SELECT * FROM mla_work_analysis")
            all_works = list(mp_works) + list(mla_works)

            total_members = len(rows)
            zero_work = sum(1 for r in rows if r["zero_work_member"])
            low_sample = sum(1 for r in rows if r["low_sample_member"])
            work_bearing = total_members - zero_work

            total_works = len(all_works)
            rec = sum(1 for w in all_works if w["recommendation_date"] is not None)
            sanc = sum(1 for w in all_works if w["sanction_date"] is not None)
            comp = sum(1 for w in all_works if w["status"] == "COMPLETED")
            ongoing = sum(1 for w in all_works if w["status"] == "ONGOING")
            pending = total_works - rec

            rec_amt = sum(_safe_float(w["recommended_amount"]) for w in all_works)
            sanc_amt = sum(_safe_float(w["sanction_amount"]) for w in all_works)
            exp_amt = sum(_safe_float(w["expenditure_amount"]) for w in all_works)
            comp_amt = sum(_safe_float(w["completion_amount"]) for w in all_works)

            allocated = sum(_safe_float(r["allocated_amount"]) for r in rows)
            unspent = max(0.0, allocated - exp_amt)

            sanc_amts = [_safe_float(w["sanction_amount"]) for w in all_works]
            sanc_delays = [w["sanction_delay_days"] for w in all_works if w["sanction_delay_days"] is not None and w["sanction_delay_days"] >= 0]
            exec_days = [w["execution_days"] for w in all_works if w["execution_days"] is not None and w["execution_days"] >= 0]
            project_ages = [w["project_age_days"] for w in all_works if w["project_age_days"] is not None and w["project_age_days"] >= 0]

            overdue_1y = sum(1 for w in all_works if w["status"] == "ONGOING" and w["project_age_days"] and w["project_age_days"] > 365)
            overdue_2y = sum(1 for w in all_works if w["status"] == "ONGOING" and w["project_age_days"] and w["project_age_days"] > 730)

            flagged = sum(1 for w in all_works if w["risk_level"] in ("LOW", "MEDIUM", "HIGH"))
            high_risk = sum(1 for w in all_works if w["risk_level"] == "HIGH")
            medium_risk = sum(1 for w in all_works if w["risk_level"] == "MEDIUM")

            cost_anomaly = sum(1 for w in all_works if w["cost_status"] in ("HIGH", "VERY_HIGH"))
            duration_anomaly = sum(1 for w in all_works if w["duration_status"] in ("HIGH", "VERY_HIGH"))

            benchmark_qualified = sum(1 for r in rows if r["ranking_qualified"])
            insufficient = total_members - benchmark_qualified
            anomaly_qualified = sum(1 for r in rows if r["total_works"] >= 10)

            record = (
                "BOTH", total_members, work_bearing, zero_work, low_sample,
                total_works, rec, sanc, comp, ongoing, pending,
                (comp / rec * 100.0) if rec > 0 else 0.0,
                (sanc / rec * 100.0) if rec > 0 else 0.0,
                (comp / sanc * 100.0) if sanc > 0 else 0.0,
                allocated, rec_amt, sanc_amt, exp_amt, comp_amt, unspent,
                (exp_amt / allocated * 100.0) if allocated > 0 else 0.0,
                (exp_amt / sanc_amt * 100.0) if sanc_amt > 0 else 0.0,
                (exp_amt / rec_amt) if rec_amt > 0 else 0.0,
                (sanc_amt / total_works) if total_works > 0 else None,
                _median(sanc_amts), _percentile(sanc_amts, 25), _percentile(sanc_amts, 75),
                _percentile(sanc_amts, 90), _percentile(sanc_amts, 95),
                (sum(sanc_delays) / len(sanc_delays)) if sanc_delays else None,
                _median(sanc_delays),
                (sum(exec_days) / len(exec_days)) if exec_days else None,
                _median(exec_days),
                (sum(project_ages) / len(project_ages)) if project_ages else None,
                _median(project_ages),
                overdue_1y, overdue_2y, flagged, high_risk, medium_risk,
                cost_anomaly, duration_anomaly,
                0, benchmark_qualified, insufficient, anomaly_qualified,
                datetime.datetime.now(datetime.timezone.utc)
            )

            await conn.execute("TRUNCATE TABLE overall_metrics RESTART IDENTITY CASCADE")
            await conn.copy_records_to_table(
                "overall_metrics",
                records=[record],
                columns=[
                    "scope", "total_members", "work_bearing", "zero_work_members", "low_sample_members",
                    "total_works", "recommended_works", "sanctioned_works", "completed_works", "ongoing_works",
                    "pending_works", "completion_rate_pct", "sanction_rate_pct", "sanction_conversion_pct",
                    "allocated_amount", "recommended_amount", "sanctioned_amount", "expenditure_amount",
                    "completion_amount", "unspent_amount", "fund_utilization_pct", "expenditure_rate_pct",
                    "expenditure_per_recommended", "avg_work_cost", "median_work_cost", "p25_work_cost",
                    "p75_work_cost", "p90_work_cost", "p95_work_cost", "avg_sanction_delay_days",
                    "median_sanction_delay_days", "avg_execution_days", "median_execution_days",
                    "avg_project_age_days", "median_project_age_days", "overdue_over_1_year",
                    "overdue_over_2_years", "flagged_works", "high_risk_works", "medium_risk_works",
                    "cost_anomaly_works", "duration_anomaly_works", "negative_delay_count",
                    "benchmark_qualified", "insufficient_benchmark", "anomaly_qualified", "calculated_at"
                ]
            )
            return 1
    finally:
        await p2.close()


async def build_trends() -> int:
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            all_works = await conn.fetch("""
                SELECT 'MP' AS member_type, recommendation_date, sanction_date, completion_date,
                       recommended_amount, sanction_amount, expenditure_amount, completion_amount,
                       status, execution_days, sanction_delay_days
                FROM work_analysis
                UNION ALL
                SELECT 'MLA' AS member_type, recommendation_date, sanction_date, completion_date,
                       recommended_amount, sanction_amount, expenditure_amount, completion_amount,
                       status, execution_days, sanction_delay_days
                FROM mla_work_analysis
            """)

            def fy_year(d):
                if d is None:
                    return None
                if d.month >= 4:
                    return d.year
                return d.year - 1

            groups: Dict[Any, Dict[str, Any]] = {}
            for w in all_works:
                year = fy_year(w["recommendation_date"])
                if year is None:
                    continue
                mtype = w["member_type"]
                key = (year, mtype)
                g = groups.setdefault(key, {
                    "year": year,
                    "member_type": mtype,
                    "total_works": 0,
                    "recommended_works": 0,
                    "sanctioned_works": 0,
                    "completed_works": 0,
                    "ongoing_works": 0,
                    "pending_works": 0,
                    "recommended_amount": 0.0,
                    "sanctioned_amount": 0.0,
                    "expenditure_amount": 0.0,
                    "completion_amount": 0.0,
                    "exec_days": [],
                    "sanc_delays": [],
                })
                g["total_works"] += 1
                if w["recommendation_date"]:
                    g["recommended_works"] += 1
                if w["sanction_date"]:
                    g["sanctioned_works"] += 1
                if w["status"] == "COMPLETED":
                    g["completed_works"] += 1
                elif w["status"] == "ONGOING":
                    g["ongoing_works"] += 1
                else:
                    g["pending_works"] += 1
                g["recommended_amount"] += _safe_float(w["recommended_amount"])
                g["sanctioned_amount"] += _safe_float(w["sanction_amount"])
                g["expenditure_amount"] += _safe_float(w["expenditure_amount"])
                g["completion_amount"] += _safe_float(w["completion_amount"])
                if w["execution_days"] is not None and w["execution_days"] >= 0:
                    g["exec_days"].append(w["execution_days"])
                if w["sanction_delay_days"] is not None and w["sanction_delay_days"] >= 0:
                    g["sanc_delays"].append(w["sanction_delay_days"])

            records = []
            for g in groups.values():
                rec = g["recommended_works"]
                sanc = g["sanctioned_works"]
                comp = g["completed_works"]
                records.append((
                    g["year"], g["member_type"], False,
                    g["total_works"], rec, sanc, comp, g["ongoing_works"], g["pending_works"],
                    g["recommended_amount"], g["sanctioned_amount"], g["expenditure_amount"], g["completion_amount"],
                    (comp / rec * 100.0) if rec > 0 else 0.0,
                    (g["expenditure_amount"] / g["sanctioned_amount"] * 100.0) if g["sanctioned_amount"] > 0 else 0.0,
                    (sum(g["sanc_delays"]) / len(g["sanc_delays"])) if g["sanc_delays"] else None,
                    (sum(g["exec_days"]) / len(g["exec_days"])) if g["exec_days"] else None,
                    datetime.datetime.now(datetime.timezone.utc)
                ))

            await conn.execute("TRUNCATE TABLE trends RESTART IDENTITY CASCADE")
            if records:
                await conn.copy_records_to_table(
                    "trends",
                    records=records,
                    columns=[
                        "year", "member_type", "is_partial_year", "total_works", "recommended_works",
                        "sanctioned_works", "completed_works", "ongoing_works", "pending_works",
                        "recommended_amount", "sanctioned_amount", "expenditure_amount", "completion_amount",
                        "completion_rate_pct", "fund_utilization_pct", "avg_sanction_delay_days",
                        "avg_execution_days", "calculated_at"
                    ]
                )
            return len(records)
    finally:
        await p2.close()


async def build_category_metrics() -> int:
    """Build category_metrics using SQL aggregation for speed."""
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            print("  [category_metrics] running SQL aggregation...", flush=True)
            rows = await conn.fetch("""
                SELECT
                    'national' AS scope,
                    0::bigint AS state_id,
                    COALESCE(work_category, 'Uncategorized') AS category,
                    COUNT(*) AS sample_size,
                    COUNT(DISTINCT state_id) AS distinct_states,
                    COUNT(DISTINCT (member_id, member_type)) AS distinct_members,
                    COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed_works,
                    COUNT(*) FILTER (WHERE status = 'ONGOING') AS ongoing_works,
                    COUNT(*) FILTER (WHERE recommended_amount > 0) AS recommended_works,
                    COUNT(*) FILTER (WHERE sanction_amount > 0) AS sanctioned_works,
                    SUM(recommended_amount) AS recommended_amount,
                    SUM(sanction_amount) AS sanctioned_amount,
                    SUM(expenditure_amount) AS expenditure_amount,
                    CASE WHEN COUNT(*) FILTER (WHERE recommended_amount > 0) > 0
                         THEN COUNT(*) FILTER (WHERE status = 'COMPLETED')::numeric /
                              COUNT(*) FILTER (WHERE recommended_amount > 0) * 100
                         ELSE 0 END AS completion_rate_pct,
                    CASE WHEN COUNT(*) FILTER (WHERE recommended_amount > 0) > 0
                         THEN COUNT(*) FILTER (WHERE sanction_amount > 0)::numeric /
                              COUNT(*) FILTER (WHERE recommended_amount > 0) * 100
                         ELSE 0 END AS sanction_rate_pct,
                    CASE WHEN SUM(sanction_amount) > 0
                         THEN SUM(expenditure_amount) / SUM(sanction_amount) * 100
                         ELSE 0 END AS utilization_pct,
                    AVG(sanction_amount) AS avg_work_cost,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sanction_amount) AS median_work_cost,
                    AVG(execution_days) FILTER (WHERE execution_days >= 0) AS avg_execution_days,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY execution_days)
                        FILTER (WHERE execution_days >= 0) AS median_execution_days,
                    CASE WHEN COUNT(*) > 0
                         THEN COUNT(*) FILTER (WHERE status = 'ONGOING' AND project_age_days > 365)::numeric /
                              COUNT(*) * 100
                         ELSE 0 END AS overdue_rate_pct,
                    CASE WHEN COUNT(*) > 0
                         THEN COUNT(*) FILTER (WHERE risk_level IN ('LOW','MEDIUM','HIGH'))::numeric /
                              COUNT(*) * 100
                         ELSE 0 END AS risk_rate_pct,
                    CASE WHEN COUNT(*) > 0
                         THEN COUNT(*) FILTER (WHERE cost_status IN ('HIGH','VERY_HIGH'))::numeric /
                              COUNT(*) * 100
                         ELSE 0 END AS cost_anomaly_rate_pct,
                    CASE WHEN COUNT(*) > 0
                         THEN COUNT(*) FILTER (WHERE duration_status IN ('HIGH','VERY_HIGH'))::numeric /
                              COUNT(*) * 100
                         ELSE 0 END AS duration_anomaly_rate_pct,
                    CASE WHEN COUNT(*) >= 30 THEN 'HIGH'
                         WHEN COUNT(*) >= 10 THEN 'MEDIUM'
                         ELSE 'LOW' END AS confidence
                FROM (
                    SELECT * FROM work_analysis
                    UNION ALL
                    SELECT * FROM mla_work_analysis
                ) all_works
                GROUP BY COALESCE(work_category, 'Uncategorized')
            """)
            print(f"  [category_metrics] aggregated {len(rows)} categories", flush=True)

            await conn.execute("TRUNCATE TABLE category_metrics RESTART IDENTITY CASCADE")
            if rows:
                await conn.copy_records_to_table(
                    "category_metrics",
                    records=[tuple(r) for r in rows],
                    columns=[
                        "scope", "state_id", "category", "sample_size", "distinct_states", "distinct_members",
                        "completed_works", "ongoing_works", "recommended_works", "sanctioned_works",
                        "recommended_amount", "sanctioned_amount", "expenditure_amount", "completion_rate_pct",
                        "sanction_rate_pct", "utilization_pct", "avg_work_cost", "median_work_cost",
                        "avg_execution_days", "median_execution_days", "overdue_rate_pct", "risk_rate_pct",
                        "cost_anomaly_rate_pct", "duration_anomaly_rate_pct", "confidence"
                    ]
                )
            return len(rows)
    finally:
        await p2.close()


async def build_fy_metrics() -> int:
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            all_works = await conn.fetch("""
                SELECT 'MP' AS member_type, recommendation_date, sanction_date, completion_date,
                       recommended_amount, sanction_amount, expenditure_amount, completion_amount
                FROM work_analysis
                UNION ALL
                SELECT 'MLA' AS member_type, recommendation_date, sanction_date, completion_date,
                       recommended_amount, sanction_amount, expenditure_amount, completion_amount
                FROM mla_work_analysis
            """)

            def fy_year(d):
                if d is None:
                    return None
                return d.year if d.month >= 4 else d.year - 1

            groups: Dict[Any, Dict[str, Any]] = {}
            for w in all_works:
                year = fy_year(w["recommendation_date"])
                if year is None:
                    continue
                mtype = w["member_type"]
                key = (year, mtype)
                g = groups.setdefault(key, {
                    "fy_start": year, "fy_label": f"FY{year}-{str(year + 1)[-2:]}",
                    "member_type": mtype, "rec": 0, "sanc": 0, "comp": 0,
                    "exp_count": 0, "rec_amt": 0.0, "sanc_amt": 0.0,
                    "comp_amt": 0.0, "exp_amt": 0.0,
                })
                g["rec"] += 1
                g["rec_amt"] += _safe_float(w["recommended_amount"])
                if w["sanction_date"] is not None or _safe_float(w["sanction_amount"]) > 0:
                    g["sanc"] += 1
                    g["sanc_amt"] += _safe_float(w["sanction_amount"])
                if w["completion_date"] is not None:
                    g["comp"] += 1
                    g["comp_amt"] += _safe_float(w["completion_amount"])
                if _safe_float(w["expenditure_amount"]) > 0:
                    g["exp_count"] += 1
                    g["exp_amt"] += _safe_float(w["expenditure_amount"])

            records = [
                (g["fy_start"], g["fy_label"], g["member_type"], g["rec"], g["sanc"], g["comp"],
                 g["exp_count"], g["rec_amt"], g["sanc_amt"], g["comp_amt"], g["exp_amt"])
                for g in groups.values()
            ]

            await conn.execute("TRUNCATE TABLE fy_metrics RESTART IDENTITY CASCADE")
            if records:
                await conn.copy_records_to_table(
                    "fy_metrics",
                    records=records,
                    columns=[
                        "fy_start", "fy_label", "member_type", "recommended_works", "sanctioned_works",
                        "completed_works", "expenditure_count", "recommended_amount", "sanctioned_amount",
                        "completion_amount", "expenditure_amount"
                    ]
                )
            return len(records)
    finally:
        await p2.close()


async def build_all_statistics() -> Dict[str, int]:
    ns = await build_national_statistics()
    om = await build_overall_metrics()
    tr = await build_trends()
    cm = await build_category_metrics()
    fy = await build_fy_metrics()
    return {"national_statistics": ns, "overall_metrics": om, "trends": tr, "category_metrics": cm, "fy_metrics": fy}
