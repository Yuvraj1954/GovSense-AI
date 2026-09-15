"""Build work_analysis and mla_work_analysis in DB2 from DB1 raw tables."""
import asyncio
import datetime
from typing import List, Dict, Any, Optional
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


def _days_between(start, end) -> Optional[int]:
    if start is None:
        return None
    if end is None:
        end = datetime.date.today()
    if isinstance(start, str):
        start = datetime.date.fromisoformat(start)
    if isinstance(end, str):
        end = datetime.date.fromisoformat(end)
    return (end - start).days


def _percentile_rank(value: float, sorted_values: List[float]) -> float:
    if not sorted_values or value is None:
        return 50.0
    n = len(sorted_values)
    below = sum(1 for v in sorted_values if v < value)
    return 100.0 * below / n


def _percentile_value(sorted_values: List[float], p: float) -> Optional[float]:
    if not sorted_values:
        return None
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    k = (n - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, n - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


async def _fetch_batched(pool, label: str, sql: str, batch_size: int = 10000):
    """Yield batches of rows using LIMIT/OFFSET with progress logging."""
    print(f"  [{label}] fetching in batches of {batch_size}...", flush=True)
    fetched = 0
    offset = 0
    while True:
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"{sql} LIMIT {batch_size} OFFSET {offset}")
        if not rows:
            break
        fetched += len(rows)
        print(f"  [{label}] fetched batch ending at row {fetched}", flush=True)
        yield rows
        if len(rows) < batch_size:
            break
        offset += batch_size
    print(f"  [{label}] total fetched: {fetched}", flush=True)


async def _fetch_works(pool, is_mla: bool) -> List[Dict[str, Any]]:
    table = "mla_works" if is_mla else "works"
    member_col = "mla_id" if is_mla else "mp_id"
    sql = f"""
        SELECT work_id, {member_col} AS member_id, constituency_id,
               work_category, activity_name, work_description
        FROM {table}
        ORDER BY work_id
    """
    result = []
    async for batch in _fetch_batched(pool, f"{table}.works", sql, batch_size=10000):
        result.extend(batch)

    async with pool.acquire() as conn:
        constituencies = {r["constituency_id"]: r["state_id"] for r in await conn.fetch("SELECT constituency_id, state_id FROM constituencies")}
        states = {r["state_id"]: r["state_name"] for r in await conn.fetch("SELECT state_id, state_name FROM states")}

    mapped = []
    for w in result:
        cid = w["constituency_id"]
        sid = constituencies.get(cid)
        mapped.append({
            "work_id": w["work_id"],
            "member_id": w["member_id"],
            "constituency_id": cid,
            "state_id": sid,
            "state_name": states.get(sid),
            "work_category": w["work_category"],
            "activity_name": w["activity_name"],
            "work_description": w["work_description"],
        })
    return mapped


async def _fetch_recommendations(pool, is_mla: bool) -> Dict[int, asyncpg.Record]:
    table = "mla_work_recommendations" if is_mla else "work_recommendations"
    sql = f"""
        SELECT DISTINCT ON (work_id) work_id, recommendation_date, recommended_amount
        FROM {table}
        ORDER BY work_id, recommendation_date NULLS LAST
    """
    result = {}
    async for batch in _fetch_batched(pool, f"{table}.recommendations", sql, batch_size=20000):
        for r in batch:
            result[r["work_id"]] = r
    return result


async def _fetch_sanctions(pool, is_mla: bool) -> Dict[int, asyncpg.Record]:
    table = "mla_work_sanctions" if is_mla else "work_sanctions"
    sql = f"""
        SELECT DISTINCT ON (work_id) work_id, sanction_date, sanction_amount, work_stage
        FROM {table}
        ORDER BY work_id, sanction_date NULLS LAST
    """
    result = {}
    async for batch in _fetch_batched(pool, f"{table}.sanctions", sql, batch_size=20000):
        for r in batch:
            result[r["work_id"]] = r
    return result


async def _fetch_expenditures(pool, is_mla: bool) -> Dict[int, Dict[str, Any]]:
    table = "mla_work_expenditures" if is_mla else "work_expenditures"
    sql = f"""
        SELECT work_id, expenditure_date, fund_disbursed_amount
        FROM {table}
        ORDER BY work_id, expenditure_date
    """
    result = {}
    async for batch in _fetch_batched(pool, f"{table}.expenditures", sql, batch_size=20000):
        for r in batch:
            wid = r["work_id"]
            if wid not in result:
                result[wid] = {"total": 0.0, "first": None, "last": None}
            amt = _safe_float(r["fund_disbursed_amount"])
            result[wid]["total"] += amt
            ed = r["expenditure_date"]
            if result[wid]["first"] is None or (ed and ed < result[wid]["first"]):
                result[wid]["first"] = ed
            if result[wid]["last"] is None or (ed and ed > result[wid]["last"]):
                result[wid]["last"] = ed
    return result


async def _fetch_completions(pool, is_mla: bool) -> Dict[int, asyncpg.Record]:
    table = "mla_work_completions" if is_mla else "work_completions"
    sql = f"""
        SELECT DISTINCT ON (work_id) work_id, completion_date, amount_disbursed
        FROM {table}
        ORDER BY work_id, completion_date NULLS LAST
    """
    result = {}
    async for batch in _fetch_batched(pool, f"{table}.completions", sql, batch_size=20000):
        for r in batch:
            result[r["work_id"]] = r
    return result


def _derive_status(sanction, completion) -> str:
    if completion and completion.get("completion_date"):
        return "COMPLETED"
    if sanction and sanction.get("sanction_date"):
        return "ONGOING"
    if sanction and not sanction.get("sanction_date"):
        return "RECOMMENDED"
    return "PENDING"


def _risk_flags(record: Dict[str, Any]) -> List[str]:
    flags = []
    status = record.get("status", "")
    if status == "ONGOING":
        age = record.get("project_age_days")
        if age is not None and age > 730:
            flags.append("LONG_RUNNING_2Y")
        elif age is not None and age > 365:
            flags.append("LONG_RUNNING_1Y")
        exec_days = record.get("execution_days")
        if exec_days is not None and exec_days > 365:
            flags.append("SLOW_EXECUTION")
    cost_status = record.get("cost_status", "")
    duration_status = record.get("duration_status", "")
    if cost_status in ("HIGH", "VERY_HIGH"):
        flags.append("COST_ANOMALY")
    if duration_status in ("HIGH", "VERY_HIGH"):
        flags.append("DURATION_ANOMALY")
    exp_pct = _safe_float(record.get("expenditure_percentage"))
    comp_pct = _safe_float(record.get("completion_percentage"))
    if status == "ONGOING" and exp_pct > 90 and comp_pct < 50:
        flags.append("SPEND_WITHOUT_PROGRESS")
    return flags


def _level_from_flags(flags: List[str]) -> str:
    critical = {"SPEND_WITHOUT_PROGRESS", "LONG_RUNNING_2Y", "COST_ANOMALY", "DURATION_ANOMALY"}
    high = {"LONG_RUNNING_1Y", "SLOW_EXECUTION"}
    score = 0
    for f in flags:
        if f in critical:
            score += 3
        elif f in high:
            score += 2
        else:
            score += 1
    if score >= 4:
        return "HIGH"
    if score >= 2:
        return "MEDIUM"
    if score >= 1:
        return "LOW"
    return "NONE"


async def build_work_analysis(is_mla: bool = False) -> int:
    """Build the work_analysis/mla_work_analysis table in DB2 from DB1 raw data."""
    target = "mla_work_analysis" if is_mla else "work_analysis"
    source_member_type = "MLA" if is_mla else "MP"

    print(f"  [{target}] connecting to DB1 + DB2...", flush=True)
    p1 = await db1_pool()
    p2 = await db2_pool()
    try:
        print(f"  [{target}] fetching works...", flush=True)
        works = await _fetch_works(p1, is_mla)
        print(f"  [{target}] fetching recommendations...", flush=True)
        recs = await _fetch_recommendations(p1, is_mla)
        print(f"  [{target}] fetching sanctions...", flush=True)
        sancs = await _fetch_sanctions(p1, is_mla)
        print(f"  [{target}] fetching expenditures...", flush=True)
        exps = await _fetch_expenditures(p1, is_mla)
        print(f"  [{target}] fetching completions...", flush=True)
        comps = await _fetch_completions(p1, is_mla)
        print(f"  [{target}] raw fetch complete; building {len(works)} records...", flush=True)

        all_costs: Dict[str, List[float]] = {}
        all_durations: Dict[str, List[float]] = {}
        records: List[Dict[str, Any]] = []

        for i, w in enumerate(works):
            wid = w["work_id"]
            rec = recs.get(wid, {})
            sanc = sancs.get(wid, {})
            exp = exps.get(wid, {"total": 0.0, "first": None, "last": None})
            comp = comps.get(wid, {})

            rec_amt = _safe_float(rec.get("recommended_amount"))
            sanc_amt = _safe_float(sanc.get("sanction_amount"))
            exp_amt = exp["total"]
            comp_amt = _safe_float(comp.get("amount_disbursed"))

            rec_date = rec.get("recommendation_date")
            sanc_date = sanc.get("sanction_date")
            first_exp = exp["first"]
            last_exp = exp["last"]
            comp_date = comp.get("completion_date")

            status = _derive_status(sanc, comp)

            sanction_delay_days = _days_between(rec_date, sanc_date) if sanc_date else None
            project_age_days = _days_between(rec_date, None)
            execution_days = _days_between(sanc_date, comp_date) if sanc_date else None
            pending_days = _days_between(last_exp or sanc_date or rec_date, None)

            expenditure_percentage = min(100.0, (exp_amt / sanc_amt * 100.0) if sanc_amt > 0 else 0.0)
            completion_percentage = min(100.0, (comp_amt / sanc_amt * 100.0) if sanc_amt > 0 else 0.0)

            category = w["work_category"] or "Uncategorized"
            all_costs.setdefault(category, []).append(sanc_amt)
            if execution_days is not None and execution_days >= 0:
                all_durations.setdefault(category, []).append(float(execution_days))

            records.append({
                "work_id": wid,
                "member_id": w["member_id"],
                "member_type": source_member_type,
                "constituency_id": w["constituency_id"],
                "state_id": w["state_id"],
                "state_name": w["state_name"],
                "work_category": category,
                "activity_name": w["activity_name"],
                "normalized_activity": w["activity_name"],
                "work_description": w["work_description"],
                "status": status,
                "recommended_amount": rec_amt,
                "sanction_amount": sanc_amt,
                "expenditure_amount": exp_amt,
                "completion_amount": comp_amt,
                "recommendation_date": rec_date,
                "sanction_date": sanc_date,
                "first_expenditure_date": first_exp,
                "last_expenditure_date": last_exp,
                "completion_date": comp_date,
                "sanction_delay_days": sanction_delay_days,
                "project_age_days": project_age_days,
                "execution_days": execution_days,
                "pending_days": pending_days,
                "expenditure_percentage": expenditure_percentage,
                "completion_percentage": completion_percentage,
                "benchmark_peer_group": category,
                "benchmark_quality": None,
                "benchmark_sample_size": None,
                "cost_p25": None,
                "cost_p50": None,
                "cost_p75": None,
                "cost_p90": None,
                "cost_p95": None,
                "duration_p25": None,
                "duration_p50": None,
                "duration_p75": None,
                "duration_p90": None,
                "duration_p95": None,
                "cost_percentile": None,
                "duration_percentile": None,
                "cost_status": "NORMAL",
                "duration_status": "NORMAL",
                "cost_deviation_from_median_percentage": None,
                "duration_deviation_from_median_percentage": None,
            })

        sorted_costs = {cat: sorted(v) for cat, v in all_costs.items() if v}
        sorted_durations = {cat: sorted(v) for cat, v in all_durations.items() if v}

        cost_p_keys = [25, 50, 75, 90, 95]
        duration_p_keys = [25, 50, 75, 90, 95]

        for rec in records:
            cat = rec["work_category"]
            sanc_amt = _safe_float(rec["sanction_amount"])
            exec_days = rec["execution_days"]

            cost_pvals = {p: _percentile_value(sorted_costs.get(cat, []), p) for p in cost_p_keys}
            duration_pvals = {p: _percentile_value(sorted_durations.get(cat, []), p) for p in duration_p_keys}

            rec["cost_p25"] = cost_pvals[25]
            rec["cost_p50"] = cost_pvals[50]
            rec["cost_p75"] = cost_pvals[75]
            rec["cost_p90"] = cost_pvals[90]
            rec["cost_p95"] = cost_pvals[95]
            rec["duration_p25"] = duration_pvals[25]
            rec["duration_p50"] = duration_pvals[50]
            rec["duration_p75"] = duration_pvals[75]
            rec["duration_p90"] = duration_pvals[90]
            rec["duration_p95"] = duration_pvals[95]
            rec["benchmark_sample_size"] = len(sorted_costs.get(cat, []))

            rec["cost_percentile"] = _percentile_rank(sanc_amt, sorted_costs.get(cat, []))
            if exec_days is not None and exec_days >= 0:
                rec["duration_percentile"] = _percentile_rank(exec_days, sorted_durations.get(cat, []))
            else:
                rec["duration_percentile"] = None

            median_cost = cost_pvals[50]
            if median_cost and median_cost > 0:
                dev = (sanc_amt - median_cost) / median_cost * 100.0
                rec["cost_deviation_from_median_percentage"] = dev
                if dev > 200:
                    rec["cost_status"] = "VERY_HIGH"
                elif dev > 100:
                    rec["cost_status"] = "HIGH"
                elif dev > 50:
                    rec["cost_status"] = "ELEVATED"
                else:
                    rec["cost_status"] = "NORMAL"

            median_dur = duration_pvals[50]
            if median_dur and median_dur > 0 and exec_days is not None and exec_days >= 0:
                dev = (exec_days - median_dur) / median_dur * 100.0
                rec["duration_deviation_from_median_percentage"] = dev
                if dev > 200:
                    rec["duration_status"] = "VERY_HIGH"
                elif dev > 100:
                    rec["duration_status"] = "HIGH"
                elif dev > 50:
                    rec["duration_status"] = "ELEVATED"
                else:
                    rec["duration_status"] = "NORMAL"

            quality = "GOOD" if rec["benchmark_sample_size"] and rec["benchmark_sample_size"] >= 10 else "LIMITED"
            rec["benchmark_quality"] = quality

            flags = _risk_flags(rec)
            rec["risk_flags"] = flags
            rec["flag_count"] = len(flags)
            rec["risk_level"] = _level_from_flags(flags)
            rec["last_calculated"] = datetime.datetime.now(datetime.timezone.utc)
            rec["delay_probability"] = None
            rec["delay_risk_band"] = None
            rec["isolation_score"] = None
            rec["isolation_level"] = None

        async with p2.acquire() as conn:
            await conn.execute(f"TRUNCATE TABLE {target} RESTART IDENTITY CASCADE")
            columns = [
                "work_id", "member_id", "member_type", "constituency_id", "state_id", "state_name",
                "work_category", "activity_name", "normalized_activity", "work_description", "status",
                "recommended_amount", "sanction_amount", "expenditure_amount", "completion_amount",
                "recommendation_date", "sanction_date", "first_expenditure_date", "last_expenditure_date",
                "completion_date", "sanction_delay_days", "project_age_days", "execution_days", "pending_days",
                "expenditure_percentage", "completion_percentage", "benchmark_peer_group", "benchmark_quality",
                "benchmark_sample_size", "cost_p25", "cost_p50", "cost_p75", "cost_p90", "cost_p95",
                "duration_p25", "duration_p50", "duration_p75", "duration_p90", "duration_p95",
                "cost_percentile", "duration_percentile", "cost_status", "duration_status",
                "cost_deviation_from_median_percentage", "duration_deviation_from_median_percentage",
                "risk_flags", "flag_count", "risk_level", "last_calculated",
                "delay_probability", "delay_risk_band", "isolation_score", "isolation_level"
            ]
            values = []
            for rec in records:
                values.append(tuple(rec.get(c) for c in columns))
            if values:
                batch_size = 5000
                total_inserted = 0
                print(f"  [{target}] inserting {len(values)} rows in batches of {batch_size}...", flush=True)
                for i in range(0, len(values), batch_size):
                    batch = values[i:i + batch_size]
                    await conn.copy_records_to_table(
                        target,
                        records=batch,
                        columns=columns,
                    )
                    total_inserted += len(batch)
                    print(f"  [{target}] inserted {total_inserted}/{len(values)}", flush=True)
            print(f"  [{target}] done writing {len(records)} rows", flush=True)
            return len(records)
    finally:
        await p1.close()
        await p2.close()


async def build_all_work_analysis() -> Dict[str, int]:
    """Build both MP and MLA work_analysis tables in parallel."""
    import time
    t0 = time.time()
    print("[work_analysis] starting MP + MLA builds in parallel...", flush=True)
    mp_task = build_work_analysis(is_mla=False)
    mla_task = build_work_analysis(is_mla=True)
    mp_count, mla_count = await asyncio.gather(mp_task, mla_task)
    print(f"[work_analysis] MP={mp_count}, MLA={mla_count} in {time.time() - t0:.1f}s", flush=True)
    return {"mp_work_analysis": mp_count, "mla_work_analysis": mla_count}
