import asyncio
import json
import time
from fastapi import APIRouter, HTTPException, Query, Response
from ..database import get_pool, get_db2_pool

router = APIRouter(prefix="/api", tags=["dashboard"])

# Lightweight in-process TTL cache for expensive, rarely-changing national queries.
_cache_store = {}

# Cache TTL policy (seconds). Aggregates that only change on a daily pipeline
# can afford longer TTLs; user-driven filters stay short.
TTL = {
    "overview": 120,           # /api/overview
    "trends": 300,             # /api/trends
    "state_perf": 300,         # /api/state-performance
    "states": 600,             # /api/states (master list)
    "class_dist": 300,         # /api/classification/distribution
    "class_states": 300,       # /api/classification/states
    "scatter": 300,            # /api/members/scatter
    "projects_summary": 300,   # /api/projects/summary
    "risk_overview": 300,      # /api/risk/overview
    "risk_alerts": 300,        # /api/risk/alerts
    "members_search": 30,      # /api/members/search (param-dependent)
    "members_list": 30,        # /api/members/list (param-dependent)
    "works": 60,               # /api/works (param-dependent)
    "state_detail": 600,       # /api/states/detail/{id}
    "state_works": 60,         # /api/states/detail/{id}/works
    "member_detail": 600,      # /api/members/detail/{id}
    "member_works": 60,        # /api/members/detail/{id}/works
    "constituencies": 600,     # /api/constituencies (state list)
}


def _cache_get(key):
    e = _cache_store.get(key)
    if e and (time.time() - e["t"]) < e["ttl"]:
        return e["v"]
    return None


def _cache_set(key, value, ttl=300):
    _cache_store[key] = {"t": time.time(), "ttl": ttl, "v": value}
    return value


def _cacheable(key_prefix, ttl_name, *parts):
    """Build cache key + ttl pair for a given endpoint + params."""
    return key_prefix + "::" + "::".join("" if p is None else str(p) for p in parts), TTL.get(ttl_name, 300)


def _with_cache_headers(response: Response, max_age: int, stale_while_revalidate: int = 0):
    """Set HTTP Cache-Control on the response so repeat visitors / CDNs can
    skip the network round-trip entirely."""
    if stale_while_revalidate > 0:
        response.headers["Cache-Control"] = (
            f"public, max-age={max_age}, stale-while-revalidate={stale_while_revalidate}"
        )
    else:
        response.headers["Cache-Control"] = f"public, max-age={max_age}"


@router.get("/overview")
async def get_overview(response: Response, scope: str = Query("BOTH", pattern="^(BOTH|MP|MLA)$")):
    cache_key, ttl = _cacheable("overview", "overview", scope)
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()
    row = await db2.fetchrow("""
        SELECT * FROM public.overall_metrics WHERE scope = $1 LIMIT 1
    """, scope)
    value = dict(row) if row else {}
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


@router.get("/trends")
async def get_trends(response: Response, member_type: str = Query(None, pattern="^(MP|MLA)$")):
    cache_key, ttl = _cacheable("trends", "trends", member_type)
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()
    if member_type:
        rows = await db2.fetch("""
            SELECT year, member_type, total_works, sanctioned_works, completed_works,
                   recommended_amount, sanctioned_amount, expenditure_amount,
                   fund_utilization_pct AS utilization_pct, completion_rate_pct,
                   0 AS flagged_works, 0 AS high_risk_works, 0 AS flagged_rate_pct, 0 AS high_risk_rate_pct
            FROM public.trends
            WHERE member_type = $1
            ORDER BY year
        """, member_type)
    else:
        rows = await db2.fetch("""
            SELECT year, member_type, total_works, sanctioned_works, completed_works,
                   recommended_amount, sanctioned_amount, expenditure_amount,
                   fund_utilization_pct AS utilization_pct, completion_rate_pct,
                   0 AS flagged_works, 0 AS high_risk_works, 0 AS flagged_rate_pct, 0 AS high_risk_rate_pct
            FROM public.trends
            ORDER BY year, member_type
        """)
    value = [dict(r) for r in rows]
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


@router.get("/state-performance")
async def get_state_performance(response: Response, member_type: str = Query(None, pattern="^(MP|MLA)$")):
    cache_key, ttl = _cacheable("state_perf", "state_perf", member_type)
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    if member_type:
        db2 = await get_db2_pool()
        rows = await db2.fetch("""
            SELECT state_id, state_name,
                   SUM(total_works)::int AS total_works,
                   SUM(sanctioned_works)::int AS sanctioned_works,
                   SUM(completed_works)::int AS completed_works,
                   SUM(recommended_amount) AS recommended_amount,
                   SUM(sanctioned_amount) AS sanctioned_amount,
                   SUM(expenditure_amount) AS expenditure_amount,
                   ROUND(
                     CASE WHEN SUM(sanctioned_amount) > 0
                       THEN SUM(expenditure_amount) / SUM(sanctioned_amount) * 100
                       ELSE 0 END, 2
                   ) AS expenditure_sanction_utilization_pct,
                   ROUND(
                     CASE WHEN SUM(total_works) > 0
                       THEN SUM(completed_works)::numeric / SUM(total_works) * 100
                       ELSE 0 END, 2
                   ) AS completion_rate_pct,
                   ROUND(
                     CASE WHEN SUM(total_works) > 0
                       THEN SUM(sanctioned_works)::numeric / SUM(total_works) * 100
                       ELSE 0 END, 2
                   ) AS sanction_rate_pct,
                   SUM(flagged_works)::int AS flagged_works,
                   SUM(high_risk_works)::int AS high_risk_works,
                   ROUND(
                     CASE WHEN SUM(total_works) > 0
                       THEN SUM(flagged_works)::numeric / SUM(total_works) * 100
                       ELSE 0 END, 2
                   ) AS flagged_rate_pct
            FROM public.member_metrics
            WHERE member_type = $1
            GROUP BY state_id, state_name
            ORDER BY expenditure_sanction_utilization_pct DESC
        """, member_type)
    else:
        db2 = await get_db2_pool()
        rows = await db2.fetch("""
            SELECT state_id, state_name, total_works, sanctioned_works, completed_works,
                   recommended_amount, sanctioned_amount, expenditure_amount,
                   completion_rate_pct, sanction_rate_pct, fund_utilization_pct AS expenditure_sanction_utilization_pct,
                   active_members, flagged_works, high_risk_works, risk_rate_pct AS flagged_rate_pct
            FROM public.state_metrics
            ORDER BY fund_utilization_pct DESC
        """)
    value = [dict(r) for r in rows]
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


@router.get("/members/scatter")
async def get_members_scatter(response: Response, member_type: str = Query("MP", pattern="^(MP|MLA|BOTH)$")):
    cache_key, ttl = _cacheable("scatter", "scatter", member_type)
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()
    if member_type == "BOTH":
        rows = await db2.fetch("""
            SELECT member_id, member_name, state_name, completion_rate_pct, fund_utilization_pct,
                   total_works, performance_score, performance_classification
            FROM public.member_metrics
            WHERE completion_rate_pct IS NOT NULL
              AND fund_utilization_pct IS NOT NULL
              AND total_works >= 5
            ORDER BY member_name
        """)
    else:
        rows = await db2.fetch("""
            SELECT member_id, member_name, state_name, completion_rate_pct, fund_utilization_pct,
                   total_works, performance_score, performance_classification
            FROM public.member_metrics
            WHERE member_type = $1
              AND completion_rate_pct IS NOT NULL
              AND fund_utilization_pct IS NOT NULL
              AND total_works >= 5
            ORDER BY member_name
        """, member_type)
    value = [dict(r) for r in rows]
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


@router.get("/members/list")
async def get_members_list(
    response: Response,
    member_type: str = Query("MP", pattern="^(MP|MLA|BOTH)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(6, ge=1, le=50),
    sort_by: str = Query("mixed", pattern="^(mixed|completion_rate_pct|fund_utilization_pct|total_works|expenditure_amount|member_name|performance_score)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    state: str = Query(None),
    classification: str = Query(None),
):
    cache_key, ttl = _cacheable(
        "members_list", "members_list",
        member_type, page, page_size, sort_by, sort_dir,
        (state or "").lower(), classification,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()

    if member_type == "BOTH":
        base_where = "total_works >= 5"
        base_args = []
    else:
        base_where = "member_type = $1 AND total_works >= 5"
        base_args = [member_type]

    extra = ""
    extra_args = []
    next_idx = len(base_args) + 1
    if state:
        extra += f" AND state_name ILIKE ${next_idx}"
        extra_args.append(f"%{state}%")
        next_idx += 1
    if classification:
        extra += f" AND performance_classification = ${next_idx}"
        extra_args.append(classification)
        next_idx += 1

    if not state and not classification:
        scope = "BOTH" if member_type == "BOTH" else member_type
        count_row = await db2.fetchrow("""
            SELECT total_members FROM public.overall_metrics WHERE scope = $1 LIMIT 1
        """, scope)
        total = count_row["total_members"] if count_row else 0
    else:
        count_row = await db2.fetchrow(f"""
            SELECT COUNT(*) as cnt FROM public.member_metrics
            WHERE {base_where} {extra}
        """, *(base_args + extra_args))
        total = count_row["cnt"] if count_row else 0

    if sort_by == "mixed":
        offset = (page - 1) * page_size
        if extra:
            rows = await _fetch_mixed_page_filtered(db2, member_type, page_size, offset, extra, extra_args, next_idx)
        else:
            rows = await _fetch_mixed_page(db2, member_type, page_size, offset)
        value = {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
        _with_cache_headers(response, ttl)
        return _cache_set(cache_key, value, ttl=ttl)

    allowed = {"completion_rate_pct", "fund_utilization_pct", "total_works", "expenditure_amount", "member_name", "performance_score"}
    col = sort_by if sort_by in allowed else "completion_rate_pct"
    direction = "DESC" if sort_dir == "desc" else "ASC"

    offset = (page - 1) * page_size
    all_args = base_args + extra_args + [page_size, offset]
    rows = await db2.fetch(f"""
        SELECT member_id, member_name, member_type as member_type_field, state_name, completion_rate_pct, fund_utilization_pct,
               total_works, completed_works, sanctioned_works, performance_score, performance_classification,
               sanctioned_amount, expenditure_amount
        FROM public.member_metrics
        WHERE {base_where} {extra}
        ORDER BY {col} {direction} NULLS LAST
        LIMIT ${len(all_args) - 1} OFFSET ${len(all_args)}
    """, *all_args)

    value = {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


@router.get("/members/search")
async def search_members(
    response: Response,
    q: str = Query("", min_length=0, max_length=100),
    member_type: str = Query("MP", pattern="^(MP|MLA|BOTH)$"),
    state: str = Query(None),
    classification: str = Query(None),
    limit: int = Query(20, ge=1, le=50),
):
    cache_key, ttl = _cacheable(
        "members_search", "members_search",
        (q or "").lower(), member_type, (state or "").lower(), classification, limit,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()
    if member_type == "BOTH":
        conditions = ["total_works >= 5"]
        args = []
    else:
        conditions = ["member_type = $1", "total_works >= 5"]
        args = [member_type]
    idx = len(args) + 1

    if q and len(q) >= 1:
        words = q.split()
        for w in words:
            conditions.append(f"member_name ILIKE ${idx}")
            args.append(f"%{w}%")
            idx += 1

    if state:
        conditions.append(f"state_name ILIKE ${idx}")
        args.append(f"%{state}%")
        idx += 1

    if classification:
        conditions.append(f"performance_classification = ${idx}")
        args.append(classification)
        idx += 1

    where = " AND ".join(conditions)
    rows = await db2.fetch(f"""
        SELECT member_id, member_name, member_type as member_type_field, state_name, completion_rate_pct, fund_utilization_pct,
               total_works, completed_works, sanctioned_works, performance_score, performance_classification,
               sanctioned_amount, expenditure_amount
        FROM public.member_metrics
        WHERE {where}
        ORDER BY member_name
        LIMIT ${idx}
    """, *args, limit)

    value = {"items": [dict(r) for r in rows], "total": len(rows)}
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


async def _fetch_mixed_page(pool, member_type: str, page_size: int, offset: int):
    """Return a balanced mix using a SINGLE query with window functions."""
    import math
    page_num = (offset // page_size) + 1 if page_size > 0 else 1
    per_bucket = max(1, math.ceil(page_size / 4) + 1)

    if member_type == "BOTH":
        mt_filter = ""
        mt_args = []
    else:
        mt_filter = "AND member_type = $1"
        mt_args = [member_type]

    rows = await pool.fetch(f"""
        WITH ranked AS (
            SELECT member_id, member_name, member_type as member_type_field, state_name, completion_rate_pct, fund_utilization_pct,
                   total_works, completed_works, sanctioned_works, performance_score, performance_classification,
                   sanctioned_amount, expenditure_amount,
                   ROW_NUMBER() OVER (PARTITION BY performance_classification ORDER BY performance_score DESC NULLS LAST) as rn
            FROM public.member_metrics
            WHERE total_works >= 5 {mt_filter}
        ),
        bucket_pick AS (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY performance_classification ORDER BY rn) as pick_num
            FROM ranked
        )
        SELECT member_id, member_name, member_type_field, state_name, completion_rate_pct, fund_utilization_pct,
               total_works, completed_works, sanctioned_works, performance_score, performance_classification,
               sanctioned_amount, expenditure_amount
        FROM bucket_pick
        WHERE pick_num > {(page_num - 1) * per_bucket} AND pick_num <= {page_num * per_bucket}
        ORDER BY performance_classification, performance_score DESC NULLS LAST
    """, *mt_args)

    buckets = {}
    for r in rows:
        cls = r["performance_classification"]
        if cls not in buckets:
            buckets[cls] = []
        buckets[cls].append(dict(r))

    mixed = []
    cls_order = ["PERFORMER", "AVERAGE", "NEEDS_ATTENTION", "UNDERPERFORMER", "NO_DATA", "INSUFFICIENT_DATA"]
    round_num = 0
    while len(mixed) < page_size:
        added = False
        for cls in cls_order:
            if len(mixed) >= page_size:
                break
            if cls in buckets and round_num < len(buckets[cls]):
                member = buckets[cls][round_num]
                if not any(m["member_id"] == member["member_id"] for m in mixed):
                    mixed.append(member)
                    added = True
        if not added:
            break
        round_num += 1

    return mixed[:page_size]


async def _fetch_mixed_page_filtered(pool, member_type: str, page_size: int, offset: int, extra: str, extra_args: list, next_idx: int):
    """Return a balanced mix with filters applied, SINGLE query."""
    import math
    page_num = (offset // page_size) + 1 if page_size > 0 else 1
    per_bucket = max(1, math.ceil(page_size / 4) + 1)

    if member_type == "BOTH":
        rows = await pool.fetch(f"""
            WITH ranked AS (
                SELECT member_id, member_name, member_type as member_type_field, state_name, completion_rate_pct, fund_utilization_pct,
                       total_works, completed_works, sanctioned_works, performance_score, performance_classification,
                       sanctioned_amount, expenditure_amount,
                       ROW_NUMBER() OVER (PARTITION BY performance_classification ORDER BY performance_score DESC NULLS LAST) as rn
                FROM public.member_metrics
                WHERE total_works >= 5 {extra}
            ),
            bucket_pick AS (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY performance_classification ORDER BY rn) as pick_num
                FROM ranked
            )
            SELECT member_id, member_name, member_type_field, state_name, completion_rate_pct, fund_utilization_pct,
                   total_works, completed_works, sanctioned_works, performance_score, performance_classification,
                   sanctioned_amount, expenditure_amount
            FROM bucket_pick
            WHERE pick_num > {(page_num - 1) * per_bucket} AND pick_num <= {page_num * per_bucket}
            ORDER BY performance_classification, performance_score DESC NULLS LAST
        """, *extra_args)
    else:
        all_args = [member_type] + extra_args
        rows = await pool.fetch(f"""
            WITH ranked AS (
                SELECT member_id, member_name, member_type as member_type_field, state_name, completion_rate_pct, fund_utilization_pct,
                       total_works, completed_works, sanctioned_works, performance_score, performance_classification,
                       sanctioned_amount, expenditure_amount,
                       ROW_NUMBER() OVER (PARTITION BY performance_classification ORDER BY performance_score DESC NULLS LAST) as rn
                FROM public.member_metrics
                WHERE total_works >= 5 AND member_type = $1 {extra}
            ),
            bucket_pick AS (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY performance_classification ORDER BY rn) as pick_num
                FROM ranked
            )
            SELECT member_id, member_name, member_type_field, state_name, completion_rate_pct, fund_utilization_pct,
                   total_works, completed_works, sanctioned_works, performance_score, performance_classification,
                   sanctioned_amount, expenditure_amount
            FROM bucket_pick
            WHERE pick_num > {(page_num - 1) * per_bucket} AND pick_num <= {page_num * per_bucket}
            ORDER BY performance_classification, performance_score DESC NULLS LAST
        """, *all_args)

    buckets = {}
    for r in rows:
        cls = r["performance_classification"]
        if cls not in buckets:
            buckets[cls] = []
        buckets[cls].append(dict(r))

    mixed = []
    cls_order = ["PERFORMER", "AVERAGE", "NEEDS_ATTENTION", "UNDERPERFORMER", "NO_DATA", "INSUFFICIENT_DATA"]
    round_num = 0
    while len(mixed) < page_size:
        added = False
        for cls in cls_order:
            if len(mixed) >= page_size:
                break
            if cls in buckets and round_num < len(buckets[cls]):
                member = buckets[cls][round_num]
                if not any(m["member_id"] == member["member_id"] for m in mixed):
                    mixed.append(member)
                    added = True
        if not added:
            break
        round_num += 1

    return mixed[:page_size]


@router.get("/members/detail/{member_id}")
async def get_member_detail(response: Response, member_id: int):
    """Comprehensive member profile: metrics, AI analysis, evidence, benchmarks and works."""
    cache_key, ttl = _cacheable("member_detail", "member_detail", member_id)
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()
    db1 = await get_pool()

    # 1. Core member metrics (must be first to get member_type)
    member = await db2.fetchrow("""
        SELECT member_id, member_type, member_name, state_id, state_name, constituency_id,
               house_name, tenure, total_works, recommended_works, sanctioned_works,
               completed_works, ongoing_works, pending_works, completion_rate_pct,
               sanction_rate_pct, sanction_conversion_pct, allocated_amount,
               recommended_amount, sanctioned_amount, expenditure_amount,
               completion_amount, unspent_amount, fund_utilization_pct,
               expenditure_rate_pct, avg_work_cost, median_work_cost,
               avg_sanction_delay_days, median_sanction_delay_days,
               avg_execution_days, median_execution_days, avg_project_age_days,
               max_project_age_days, overdue_over_1_year, overdue_over_2_years,
               flagged_works, high_risk_works, medium_risk_works,
               flagged_rate_pct, high_risk_rate_pct, cost_anomaly_works,
               duration_anomaly_works, anomaly_score, anomaly_level,
               confidence_level, performance_classification, rank, performance_score
        FROM public.member_metrics
        WHERE member_id = $1
    """, member_id)

    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")

    member_dict = dict(member)
    member_type = member_dict.get("member_type") or "MP"
    scope = member_type if member_type in ("MP", "MLA") else "BOTH"

    # Run all remaining queries in parallel
    async def fetch_analysis():
        row = await db2.fetchrow("""
            SELECT a.analysis_text, a.model, a.prompt_version, a.generated_at
            FROM public.ai_analysis a
            WHERE a.entity_id = $1 AND a.entity_type = $2
            ORDER BY a.generated_at DESC LIMIT 1
        """, member_id, member_type)
        if row and row["analysis_text"]:
            try:
                payload = json.loads(row["analysis_text"])
            except Exception:
                payload = {"summary": row["analysis_text"], "highlights": [], "cautions": []}
            payload = payload or {}
            payload.setdefault("summary", "")
            payload.setdefault("highlights", [])
            payload.setdefault("cautions", [])
            payload["_model"] = row.get("model")
            payload["_generated_at"] = str(row.get("generated_at", ""))
            return payload
        return None

    async def fetch_evidence():
        row = await db2.fetchrow("""
            SELECT e.evidence, e.evidence_hash, e.generated_at
            FROM public.entity_evidence e
            WHERE e.entity_id = $1 AND e.entity_type = $2
            ORDER BY e.evidence_version DESC, e.generated_at DESC LIMIT 1
        """, member_id, member_type)
        if row and row["evidence"]:
            try:
                ev = row["evidence"]
                if isinstance(ev, str):
                    ev = json.loads(ev)
                return ev
            except Exception:
                return None
        return None

    async def fetch_benchmarks():
        rows = await db2.fetch("""
            SELECT metric_name, median
            FROM public.national_statistics
            WHERE scope = $1 AND metric_name IN (
                'fund_utilization_pct', 'completion_rate_pct', 'sanction_rate_pct',
                'total_works', 'expenditure_amount', 'sanctioned_amount'
            )
        """, scope)
        return {r["metric_name"]: float(r["median"]) if r["median"] is not None else None for r in rows}

    # Execute the lightweight queries in parallel.
    # Heavy works aggregation is served by /members/detail/{id}/works and the
    # Overview tab derives risk/status breakdowns from member_metrics instead.
    analysis_result, evidence_result, benchmarks_result = await asyncio.gather(
        fetch_analysis(), fetch_evidence(), fetch_benchmarks()
    )

    value = {
        "member": member_dict,
        "analysis": analysis_result,
        "evidence": evidence_result,
        "benchmarks": benchmarks_result,
        "works_summary": {"by_status": {}, "by_risk": {}, "by_category": {},
                          "total_sanction_amount": 0.0, "total_expenditure_amount": 0.0, "total_completion_amount": 0.0},
        "works": [],
    }
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


@router.get("/members/detail/{member_id}/works")
async def get_member_works_paginated(
    response: Response,
    member_id: int,
    category: str = Query("all", pattern="^(all|completed|ongoing|recommended)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(6, ge=1, le=50),
):
    """Server-side category-filtered, paginated works for a member."""
    cache_key, ttl = _cacheable("member_works", "member_works", member_id, category, page, page_size)
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()
    db1 = await get_pool()

    member = await db2.fetchrow(
        "SELECT member_type FROM public.member_metrics WHERE member_id = $1", member_id
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    member_type = member["member_type"] or "MP"

    if category == "completed":
        status_clause = " AND LOWER(status) = 'completed'"
    elif category == "ongoing":
        status_clause = " AND LOWER(status) IN ('in progress','ongoing','inprogress','active','ongoing work')"
    elif category == "recommended":
        status_clause = " AND (LOWER(status) IN ('recommended','sanctioned','pending','proposed') OR (recommendation_date IS NOT NULL AND LOWER(status) NOT IN ('completed','in progress','ongoing','inprogress','active')))"
    else:
        status_clause = ""

    offset = (page - 1) * page_size
    args = [member_id, member_type]

    items = []
    total = 0

    try:
        rows = await db1.fetch(f"""
            SELECT work_id, work_description, activity_name, normalized_activity,
                   work_category, status, risk_level, risk_flags,
                   recommended_amount, sanction_amount, expenditure_amount,
                   completion_percentage, expenditure_percentage,
                   recommendation_date, sanction_date, completion_date,
                   project_age_days, execution_days, cost_status, duration_status,
                   COUNT(*) OVER() AS _total
            FROM public.work_analysis
            WHERE member_id = $1 AND member_type = $2 {status_clause}
            ORDER BY sanction_amount DESC NULLS LAST
            LIMIT {page_size} OFFSET {offset}
        """, *args)
        if rows:
            total = int(rows[0]["_total"] or 0)
            items = [{k: v for k, v in dict(r).items() if k != "_total"} for r in rows]
        else:
            cr = await db1.fetchrow(f"""
                SELECT COUNT(*) AS cnt FROM public.work_analysis
                WHERE member_id = $1 AND member_type = $2 {status_clause}
            """, *args)
            total = int(cr["cnt"]) if cr else 0
    except Exception:
        # Fallback: query works table directly
        try:
            id_col = "mp_id" if member_type == "MP" else "mla_id"
            fb_status = ""
            if category == "completed":
                fb_status = " AND LOWER(status) = 'completed'"
            elif category == "ongoing":
                fb_status = " AND LOWER(status) IN ('in progress','ongoing','inprogress','active')"
            elif category == "recommended":
                fb_status = " AND LOWER(status) IN ('recommended','sanctioned','pending','proposed')"

            count_row = await db1.fetchrow(f"""
                SELECT COUNT(*) AS cnt FROM public.works
                WHERE {id_col} = $1 {fb_status}
            """, member_id)
            total = int(count_row["cnt"]) if count_row else 0

            rows = await db1.fetch(f"""
                SELECT work_id, work_description, activity_name,
                       NULL as normalized_activity, NULL as work_category,
                       status, NULL as risk_level, NULL as risk_flags,
                       recommended_amount, 0 as sanction_amount, 0 as expenditure_amount,
                       0 as completion_percentage, 0 as expenditure_percentage,
                       recommendation_date, NULL as sanction_date, NULL as completion_date,
                       0 as project_age_days, 0 as execution_days,
                       NULL as cost_status, NULL as duration_status
                FROM public.works
                WHERE {id_col} = $1 {fb_status}
                ORDER BY recommended_amount DESC NULLS LAST
                LIMIT {page_size} OFFSET {offset}
            """, member_id)
            items = [dict(r) for r in rows]
        except Exception:
            pass

    total_pages = max(1, (total + page_size - 1) // page_size)
    value = {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


@router.get("/states/detail/{state_id}")
async def get_state_detail(response: Response, state_id: int):
    """Comprehensive state profile: metrics, AI analysis, evidence and benchmarks."""
    cache_key, ttl = _cacheable("state_detail", "state_detail", state_id)
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()

    state = await db2.fetchrow("""
        SELECT * FROM public.state_metrics WHERE state_id = $1
    """, state_id)
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")

    state_dict = dict(state)
    state_name = state_dict.get("state_name")

    async def fetch_analysis():
        try:
            row = await db2.fetchrow("""
                SELECT analysis_text, model, generated_at
                FROM public.ai_analysis
                WHERE LOWER(entity_type) = 'state' AND entity_id = $1
                ORDER BY generated_at DESC LIMIT 1
            """, state_id)
            if row is None and state_name:
                row = await db2.fetchrow("""
                    SELECT analysis_text, model, generated_at
                    FROM public.ai_analysis
                    WHERE LOWER(entity_type) = 'state' AND entity_name = $1
                    ORDER BY generated_at DESC LIMIT 1
                """, state_name)
            if row and row["analysis_text"]:
                try:
                    payload = json.loads(row["analysis_text"])
                except Exception:
                    payload = {"summary": row["analysis_text"], "highlights": [], "cautions": []}
                payload = payload or {}
                payload.setdefault("summary", "")
                payload.setdefault("highlights", [])
                payload.setdefault("cautions", [])
                payload["_model"] = row.get("model")
                payload["_generated_at"] = str(row.get("generated_at", ""))
                return payload
        except Exception:
            pass
        return None

    async def fetch_evidence():
        try:
            row = await db2.fetchrow("""
                SELECT evidence FROM public.entity_evidence
                WHERE LOWER(entity_type) = 'state' AND entity_id = $1
                ORDER BY evidence_version DESC, generated_at DESC LIMIT 1
            """, state_id)
            if row is None and state_name:
                row = await db2.fetchrow("""
                    SELECT evidence FROM public.entity_evidence
                    WHERE LOWER(entity_type) = 'state' AND entity_name = $1
                    ORDER BY evidence_version DESC, generated_at DESC LIMIT 1
                """, state_name)
            if row and row["evidence"]:
                ev = row["evidence"]
                if isinstance(ev, str):
                    ev = json.loads(ev)
                return ev
        except Exception:
            pass
        return None

    async def fetch_benchmarks():
        try:
            rows = await db2.fetch("""
                SELECT metric_name, median
                FROM public.national_statistics
                WHERE metric_name IN (
                    'fund_utilization_pct', 'completion_rate_pct', 'sanction_rate_pct',
                    'total_works', 'expenditure_amount', 'sanctioned_amount'
                )
                AND scope IN ('BOTH', 'STATE')
                ORDER BY CASE WHEN scope = 'STATE' THEN 0 ELSE 1 END
            """)
            out = {}
            for r in rows:
                if r["metric_name"] not in out and r["median"] is not None:
                    out[r["metric_name"]] = float(r["median"])
            return out
        except Exception:
            return {}

    async def fetch_members():
        try:
            rows = await db2.fetch("""
                SELECT member_id, member_name, member_type, house_name, constituency_id,
                       total_works, completed_works, completion_rate_pct, fund_utilization_pct,
                       performance_classification, sanctioned_amount, expenditure_amount
                FROM public.member_metrics
                WHERE state_id = $1
                ORDER BY total_works DESC NULLS LAST
            """, state_id)
            return [dict(r) for r in rows]
        except Exception:
            return []

    analysis_result, evidence_result, benchmarks_result, members = await asyncio.gather(
        fetch_analysis(), fetch_evidence(), fetch_benchmarks(), fetch_members()
    )

    value = {
        "state": state_dict,
        "analysis": analysis_result,
        "evidence": evidence_result,
        "benchmarks": benchmarks_result,
        "members": members,
    }
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


@router.get("/states/detail/{state_id}/works")
async def get_state_works_paginated(
    response: Response,
    state_id: int,
    category: str = Query("all", pattern="^(all|completed|ongoing|recommended)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(6, ge=1, le=50),
):
    """Server-side category-filtered, paginated works for a state."""
    cache_key, ttl = _cacheable("state_works", "state_works", state_id, category, page, page_size)
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db1 = await get_pool()

    if category == "completed":
        status_clause = " AND LOWER(status) = 'completed'"
    elif category == "ongoing":
        status_clause = " AND LOWER(status) IN ('in progress','ongoing','inprogress','active')"
    elif category == "recommended":
        status_clause = " AND (LOWER(status) IN ('recommended','sanctioned','pending','proposed') OR (recommendation_date IS NOT NULL AND LOWER(status) NOT IN ('completed','in progress','ongoing','inprogress','active')))"
    else:
        status_clause = ""

    offset = (page - 1) * page_size
    items = []
    total = 0

    try:
        count_row = await db1.fetchrow(f"""
            SELECT COUNT(*) AS cnt FROM (
                SELECT work_id FROM public.work_analysis WHERE state_id = $1 {status_clause}
                UNION ALL
                SELECT work_id FROM public.mla_work_analysis WHERE state_id = $1 {status_clause}
            ) t
        """, state_id)
        total = int(count_row["cnt"]) if count_row else 0

        rows = await db1.fetch(f"""
            SELECT * FROM (
                SELECT work_id, work_description, activity_name, work_category, status, risk_level,
                       recommended_amount, sanction_amount, expenditure_amount, completion_percentage,
                       recommendation_date, sanction_date, completion_date, member_type
                FROM public.work_analysis WHERE state_id = $1 {status_clause}
                UNION ALL
                SELECT work_id, work_description, activity_name, work_category, status, risk_level,
                       recommended_amount, sanction_amount, expenditure_amount, completion_percentage,
                       recommendation_date, sanction_date, completion_date, member_type
                FROM public.mla_work_analysis WHERE state_id = $1 {status_clause}
            ) t
            ORDER BY sanction_amount DESC NULLS LAST
            LIMIT {page_size} OFFSET {offset}
        """, state_id)
        items = [dict(r) for r in rows]
    except Exception:
        try:
            count_row = await db1.fetchrow(f"""
                SELECT COUNT(*) AS cnt FROM public.work_analysis
                WHERE state_id = $1 {status_clause}
            """, state_id)
            total = int(count_row["cnt"]) if count_row else 0
            rows = await db1.fetch(f"""
                SELECT work_id, work_description, activity_name, work_category, status, risk_level,
                       recommended_amount, sanction_amount, expenditure_amount, completion_percentage,
                       recommendation_date, sanction_date, completion_date, member_type
                FROM public.work_analysis
                WHERE state_id = $1 {status_clause}
                ORDER BY sanction_amount DESC NULLS LAST
                LIMIT {page_size} OFFSET {offset}
            """, state_id)
            items = [dict(r) for r in rows]
        except Exception:
            pass

    total_pages = max(1, (total + page_size - 1) // page_size)
    value = {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


@router.get("/states/detail/{state_id}/constituencies")
async def get_state_constituencies(state_id: int):
    """Representative/constituency-level aggregation for a state. Names are
    resolved on the frontend from the state's member records."""
    db1 = await get_pool()
    rows = []
    try:
        rows = await db1.fetch("""
            SELECT t.member_id,
                   t.member_type,
                   COUNT(*) AS total_works,
                   COUNT(*) FILTER (WHERE LOWER(t.status) = 'completed') AS completed_works,
                   COALESCE(SUM(t.sanction_amount), 0) AS sanctioned_amount,
                   COALESCE(SUM(t.expenditure_amount), 0) AS expenditure_amount,
                   ROUND(CASE WHEN COALESCE(SUM(t.sanction_amount),0) > 0
                        THEN SUM(t.expenditure_amount)/SUM(t.sanction_amount)*100 ELSE 0 END, 2) AS utilization_pct,
                   ROUND(CASE WHEN COUNT(*) > 0
                        THEN COUNT(*) FILTER (WHERE LOWER(t.status)='completed')::numeric/COUNT(*)*100 ELSE 0 END, 2) AS completion_rate_pct
            FROM (
                SELECT member_id, member_type, status, sanction_amount, expenditure_amount
                FROM public.work_analysis WHERE state_id = $1
                UNION ALL
                SELECT member_id, member_type, status, sanction_amount, expenditure_amount
                FROM public.mla_work_analysis WHERE state_id = $1
            ) t
            GROUP BY t.member_id, t.member_type
            ORDER BY utilization_pct DESC NULLS LAST
        """, state_id)
    except Exception:
        rows = []

    items = []
    for r in rows:
        d = dict(r)
        d["constituency_name"] = None
        items.append(d)
    return {"items": items, "total": len(items)}


@router.get("/states")
async def list_states(response: Response):
    """Canonical list of states/UTs for dropdowns. Uses state_metrics so the
    state_id numbering matches work_analysis.state_id."""
    cache_key, ttl = _cacheable("states", "states")
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()
    try:
        rows = await db2.fetch("SELECT state_id, state_name FROM public.state_metrics ORDER BY state_name")
        value = [dict(r) for r in rows]
        _with_cache_headers(response, ttl)
        return _cache_set(cache_key, value, ttl=ttl)
    except Exception:
        return []


@router.get("/constituencies")
async def list_constituencies(response: Response, state_id: int = Query(None)):
    """List constituencies present in the works data for a state. Names are
    resolved from member records (work constituency_id maps to member_id in
    the source data)."""
    cache_key, ttl = _cacheable("constituencies", "constituencies", state_id)
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db1 = await get_pool()
    db2 = await get_db2_pool()
    if state_id:
        try:
            rows = await db1.fetch("""
                SELECT constituency_id, COUNT(*) AS work_count FROM (
                    SELECT constituency_id FROM public.work_analysis WHERE state_id = $1
                    UNION ALL
                    SELECT constituency_id FROM public.mla_work_analysis WHERE state_id = $1
                ) t
                WHERE constituency_id IS NOT NULL
                GROUP BY constituency_id
            """, state_id)
            mmap = {}
            try:
                mrows = await db2.fetch(
                    "SELECT member_id, member_name, member_type FROM public.member_metrics WHERE state_id = $1",
                    state_id,
                )
                mmap = {r["member_id"]: r for r in mrows}
            except Exception:
                pass
            const_table = {}
            try:
                crows = await db1.fetch("SELECT constituency_id, constituency_name FROM public.constituencies")
                const_table = {r["constituency_id"]: r["constituency_name"] for r in crows}
            except Exception:
                pass

            out = []
            for r in rows:
                cid = r["constituency_id"]
                m = mmap.get(cid)
                name = None
                mtype = None
                if m:
                    name = m["member_name"]
                    mtype = m["member_type"]
                if not name:
                    name = const_table.get(cid) or ("Constituency #" + str(cid))
                out.append({
                    "constituency_id": cid,
                    "member_id": cid,
                    "constituency_name": name,
                    "member_name": name,
                    "member_type": mtype,
                    "work_count": int(r["work_count"]),
                })
            out.sort(key=lambda x: (-x["work_count"], (x["member_type"] or "Z")))
            _with_cache_headers(response, ttl)
            return _cache_set(cache_key, out, ttl=ttl)
        except Exception:
            return []
    try:
        rows = await db1.fetch("""
            SELECT constituency_id, constituency_name, state_id
            FROM public.constituencies ORDER BY constituency_name
        """)
        value = [dict(r) for r in rows]
        _with_cache_headers(response, ttl)
        return _cache_set(cache_key, value, ttl=ttl)
    except Exception:
        return []


def _work_status_clause(category: str) -> str:
    if category == "completed":
        return " AND LOWER(status) = 'completed'"
    if category == "ongoing":
        return " AND LOWER(status) IN ('in progress','ongoing','inprogress','active')"
    if category == "recommended":
        return " AND LOWER(status) IN ('recommended','sanctioned','pending','proposed')"
    if category == "sanctioned":
        return " AND COALESCE(sanction_amount,0) > 0"
    return ""


@router.get("/works")
async def list_works(
    response: Response,
    state_id: int = Query(None),
    constituency_id: int = Query(None),
    member_id: int = Query(None),
    category: str = Query("all", pattern="^(all|completed|ongoing|recommended|sanctioned)$"),
    work_category: str = Query(None),
    q: str = Query(None),
    sort: str = Query("highest_comp", pattern="^(newest|highest_sanction|highest_comp|longest_running)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(9, ge=1, le=50),
):
    """Global paginated works listing with filters. Works with real names are
    prioritized ahead of unnamed/NA entries."""
    cache_key, ttl = _cacheable(
        "works", "works",
        state_id, constituency_id, member_id, category,
        (work_category or "").lower(), (q or "").lower(),
        sort, page, page_size,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db1 = await get_pool()

    filters = []
    args = []
    idx = 1
    if state_id:
        filters.append(f"state_id = ${idx}"); args.append(state_id); idx += 1
    if constituency_id:
        filters.append(f"constituency_id = ${idx}"); args.append(constituency_id); idx += 1
    if member_id:
        filters.append(f"member_id = ${idx}"); args.append(member_id); idx += 1
    if work_category:
        filters.append(f"work_category = ${idx}"); args.append(work_category); idx += 1
    status_clause = _work_status_clause(category)
    if q:
        filters.append(f"(work_description ILIKE ${idx} OR activity_name ILIKE ${idx})")
        args.append(f"%{q}%"); idx += 1
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    order_map = {
        "newest": "recommendation_date DESC, work_id DESC",
        "highest_sanction": "sanction_amount DESC NULLS LAST",
        "highest_comp": "completion_percentage DESC NULLS LAST",
        "longest_running": "project_age_days DESC NULLS LAST",
    }
    order = order_map.get(sort, "completion_percentage DESC NULLS LAST")

    union = f"""
        SELECT work_id, member_id, member_type, constituency_id, state_id, state_name,
               work_category, work_description, activity_name, status,
               recommended_amount, sanction_amount, expenditure_amount,
               completion_percentage, recommendation_date, sanction_date, completion_date,
               project_age_days, execution_days, risk_level
        FROM public.work_analysis {where} {status_clause}
        UNION ALL
        SELECT work_id, member_id, member_type, constituency_id, state_id, state_name,
               work_category, work_description, activity_name, status,
               recommended_amount, sanction_amount, expenditure_amount,
               completion_percentage, recommendation_date, sanction_date, completion_date,
               project_age_days, execution_days, risk_level
        FROM public.mla_work_analysis {where} {status_clause}
    """

    unnamed_flag = """
        CASE WHEN (
              (COALESCE(activity_name,'') <> '' AND activity_name NOT ILIKE 'NA-%' AND LENGTH(TRIM(activity_name)) > 3)
           OR (COALESCE(work_description,'') <> '' AND work_description NOT ILIKE 'NA-%' AND LENGTH(TRIM(work_description)) > 3)
        ) THEN 0 ELSE 1 END
    """

    offset = (page - 1) * page_size
    total = 0
    items = []
    try:
        crow = await db1.fetchrow(f"SELECT COUNT(*) AS cnt FROM ({union}) t", *args)
        total = int(crow["cnt"]) if crow else 0
        rows = await db1.fetch(f"""
            SELECT t.*, c.constituency_name
            FROM ({union}) t
            LEFT JOIN public.constituencies c ON c.constituency_id = t.constituency_id
            ORDER BY {unnamed_flag}, {order}
            LIMIT {page_size} OFFSET {offset}
        """, *args)
        items = [dict(r) for r in rows]
    except Exception:
        pass

    total_pages = max(1, (total + page_size - 1) // page_size)
    value = {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


@router.get("/projects/summary")
async def projects_summary(response: Response, state_id: int = Query(None)):
    """Aggregates for the Projects dashboard KPIs and charts."""
    cache_key, ttl = _cacheable("projects_summary", "projects_summary", state_id or "all")
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db1 = await get_pool()
    args = []
    where = ""
    if state_id:
        where = "WHERE state_id = $1"
        args = [state_id]

    union = f"""
        SELECT status, work_category, sanction_amount, recommended_amount, expenditure_amount,
               completion_percentage, execution_days, project_age_days, risk_level
        FROM public.work_analysis {where}
        UNION ALL
        SELECT status, work_category, sanction_amount, recommended_amount, expenditure_amount,
               completion_percentage, execution_days, project_age_days, risk_level
        FROM public.mla_work_analysis {where}
    """

    out = {
        "total_works": 0, "completed_works": 0, "ongoing_works": 0, "pending_works": 0,
        "sanctioned_amount": 0.0, "recommended_amount": 0.0, "expenditure_amount": 0.0,
        "completion_rate_pct": 0.0, "categories": [],
        "milestones": [], "duration": [], "age": [], "cost": [],
    }

    async def fetch_kpis():
        return await db1.fetchrow(f"""
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE LOWER(status)='completed') AS completed,
              COUNT(*) FILTER (WHERE LOWER(status) IN ('in progress','ongoing','inprogress','active')) AS ongoing,
              COUNT(*) FILTER (WHERE LOWER(status) IN ('recommended','sanctioned','pending','proposed')) AS pending,
              COUNT(*) FILTER (WHERE COALESCE(sanction_amount,0) > 0) AS sanctioned_count,
              COALESCE(SUM(sanction_amount),0) AS sanctioned_amount,
              COALESCE(SUM(recommended_amount),0) AS recommended_amount,
              COALESCE(SUM(expenditure_amount),0) AS expenditure_amount,
              COUNT(*) FILTER (WHERE completion_percentage >= 100) AS m100,
              COUNT(*) FILTER (WHERE completion_percentage >= 75 AND completion_percentage < 100) AS m75,
              COUNT(*) FILTER (WHERE completion_percentage >= 25 AND completion_percentage < 75) AS m25,
              COUNT(*) FILTER (WHERE completion_percentage > 0 AND completion_percentage < 25) AS m0a,
              COUNT(*) FILTER (WHERE COALESCE(completion_percentage,0) <= 0) AS m0,
              COUNT(*) FILTER (WHERE execution_days > 0 AND execution_days < 180) AS d1,
              COUNT(*) FILTER (WHERE execution_days >= 180 AND execution_days < 365) AS d2,
              COUNT(*) FILTER (WHERE execution_days >= 365 AND execution_days < 730) AS d3,
              COUNT(*) FILTER (WHERE execution_days >= 730) AS d4,
              COUNT(*) FILTER (WHERE project_age_days < 365) AS a1,
              COUNT(*) FILTER (WHERE project_age_days >= 365 AND project_age_days < 730) AS a2,
              COUNT(*) FILTER (WHERE project_age_days >= 730 AND project_age_days < 1095) AS a3,
              COUNT(*) FILTER (WHERE project_age_days >= 1095) AS a4,
              COUNT(*) FILTER (WHERE COALESCE(sanction_amount,0) < 500000) AS c1,
              COUNT(*) FILTER (WHERE sanction_amount >= 500000 AND sanction_amount < 1500000) AS c2,
              COUNT(*) FILTER (WHERE sanction_amount >= 1500000 AND sanction_amount < 5000000) AS c3,
              COUNT(*) FILTER (WHERE sanction_amount >= 5000000) AS c4
            FROM ({union}) t
        """, *args)

    async def fetch_categories():
        return await db1.fetch(f"""
            SELECT work_category AS category, COUNT(*) AS cnt,
                   COALESCE(SUM(sanction_amount),0) AS amount
            FROM ({union}) t
            GROUP BY work_category
            ORDER BY cnt DESC
        """, *args)

    # Both db1 queries were serial in the original code (~2×500ms).
    # Run them concurrently on the same pool to halve the wait.
    row, crows = await asyncio.gather(fetch_kpis(), fetch_categories(), return_exceptions=True)
    if not isinstance(row, Exception) and row:
        total = int(row["total"] or 0)
        completed = int(row["completed"] or 0)
        out["total_works"] = total
        out["completed_works"] = completed
        out["ongoing_works"] = int(row["ongoing"] or 0)
        out["pending_works"] = int(row["pending"] or 0)
        out["recommended_works"] = total
        out["sanctioned_works"] = int(row["sanctioned_count"] or 0)
        out["sanctioned_amount"] = float(row["sanctioned_amount"] or 0)
        out["recommended_amount"] = float(row["recommended_amount"] or 0)
        out["expenditure_amount"] = float(row["expenditure_amount"] or 0)
        out["completion_rate_pct"] = round(completed / total * 100, 2) if total else 0
        out["milestones"] = [
            {"label": "100% Complete", "count": int(row["m100"] or 0)},
            {"label": "75-99%", "count": int(row["m75"] or 0)},
            {"label": "25-74%", "count": int(row["m25"] or 0)},
            {"label": "1-24%", "count": int(row["m0a"] or 0)},
            {"label": "Not Started", "count": int(row["m0"] or 0)},
        ]
        out["duration"] = [
            {"label": "<6 months", "count": int(row["d1"] or 0)},
            {"label": "6-12 months", "count": int(row["d2"] or 0)},
            {"label": "12-24 months", "count": int(row["d3"] or 0)},
            {"label": ">24 months", "count": int(row["d4"] or 0)},
        ]
        out["age"] = [
            {"label": "0-1 year", "count": int(row["a1"] or 0)},
            {"label": "1-2 years", "count": int(row["a2"] or 0)},
            {"label": "2-3 years", "count": int(row["a3"] or 0)},
            {"label": ">3 years", "count": int(row["a4"] or 0)},
        ]
        out["cost"] = [
            {"label": "< 5L", "count": int(row["c1"] or 0)},
            {"label": "5-15L", "count": int(row["c2"] or 0)},
            {"label": "15-50L", "count": int(row["c3"] or 0)},
            {"label": "> 50L", "count": int(row["c4"] or 0)},
        ]
    if not isinstance(crows, Exception):
        out["categories"] = [{"category": r["category"] or "Other", "count": int(r["cnt"]), "amount": float(r["amount"])} for r in crows]

    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, out, ttl=ttl)


@router.get("/risk/overview")
async def risk_overview(response: Response):
    """National risk KPIs and chart aggregates."""
    cache_key, ttl = _cacheable("risk_overview", "risk_overview")
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()
    db1 = await get_pool()
    out = {
        "high_reps": 0, "medium_reps": 0, "normal_reps": 0, "high_states": 0,
        "flagged_works": 0, "cost_anomaly_works": 0, "duration_anomaly_works": 0, "overdue_works": 0,
        "cost_only": 0, "duration_only": 0, "dual_anomaly": 0, "cost_total": 0, "duration_total": 0,
        "rep_distribution": [], "trend": [], "total_members": 0, "total_works": 0, "completion_rate_pct": 0,
    }

    # All 5 reads were sequential in the original code. Fan them out.
    async def q_member_levels():
        return await db2.fetch(
            "SELECT anomaly_level, COUNT(*) AS cnt FROM public.member_metrics GROUP BY anomaly_level"
        )
    async def q_high_states():
        return await db2.fetchrow(
            "SELECT COUNT(*) FILTER (WHERE UPPER(anomaly_level)='HIGH') AS h FROM public.state_metrics"
        )
    async def q_overall():
        return await db2.fetchrow(
            "SELECT * FROM public.overall_metrics WHERE scope='BOTH' LIMIT 1"
        )
    async def q_work_anomalies():
        return await db1.fetchrow("""
            SELECT
              COUNT(*) FILTER (WHERE risk_flags && ARRAY['COST_ANOMALY'] AND NOT (risk_flags && ARRAY['DURATION_ANOMALY'])) AS cost_only,
              COUNT(*) FILTER (WHERE risk_flags && ARRAY['DURATION_ANOMALY'] AND NOT (risk_flags && ARRAY['COST_ANOMALY'])) AS duration_only,
              COUNT(*) FILTER (WHERE risk_flags && ARRAY['COST_ANOMALY'] AND risk_flags && ARRAY['DURATION_ANOMALY']) AS dual,
              COUNT(*) FILTER (WHERE risk_flags && ARRAY['COST_ANOMALY']) AS cost_total,
              COUNT(*) FILTER (WHERE risk_flags && ARRAY['DURATION_ANOMALY']) AS duration_total
            FROM public.work_analysis
        """)
    async def q_trend():
        return await db1.fetch("""
            SELECT EXTRACT(YEAR FROM recommendation_date)::int AS yr,
                   COUNT(*) FILTER (WHERE COALESCE(flag_count, 0) > 0) AS flagged,
                   COUNT(*) FILTER (WHERE LOWER(status) = 'completed') AS resolved,
                   COUNT(*) AS total
            FROM public.work_analysis
            WHERE recommendation_date IS NOT NULL
            GROUP BY yr ORDER BY yr
        """)

    member_levels, high_states, overall, work_anom, trend_rows = await asyncio.gather(
        q_member_levels(), q_high_states(), q_overall(), q_work_anomalies(), q_trend(),
        return_exceptions=True,
    )

    if not isinstance(member_levels, Exception):
        levels = {(r["anomaly_level"] or "NORMAL").upper(): int(r["cnt"]) for r in member_levels}
        out["high_reps"] = levels.get("HIGH", 0)
        out["medium_reps"] = levels.get("MEDIUM", 0)
        out["normal_reps"] = levels.get("NORMAL", 0)
        out["total_members"] = sum(levels.values())
        out["rep_distribution"] = [
            {"level": "Normal", "count": out["normal_reps"]},
            {"level": "Medium", "count": out["medium_reps"]},
            {"level": "High", "count": out["high_reps"]},
        ]
    if not isinstance(high_states, Exception) and high_states:
        out["high_states"] = int(high_states["h"] or 0)
    if not isinstance(overall, Exception) and overall:
        d = dict(overall)
        out["flagged_works"] = int(d.get("flagged_works") or 0)
        out["cost_anomaly_works"] = int(d.get("cost_anomaly_works") or 0)
        out["duration_anomaly_works"] = int(d.get("duration_anomaly_works") or 0)
        out["overdue_works"] = int(d.get("overdue_over_1_year") or 0)
        out["total_works"] = int(d.get("total_works") or 0)
        out["completion_rate_pct"] = float(d.get("completion_rate_pct") or 0)
    if not isinstance(work_anom, Exception) and work_anom:
        out["cost_only"] = int(work_anom["cost_only"] or 0)
        out["duration_only"] = int(work_anom["duration_only"] or 0)
        out["dual_anomaly"] = int(work_anom["dual"] or 0)
        out["cost_total"] = int(work_anom["cost_total"] or 0)
        out["duration_total"] = int(work_anom["duration_total"] or 0)
    if not isinstance(trend_rows, Exception):
        out["trend"] = [
            {"year": r["yr"], "flagged": int(r["flagged"]), "resolved": int(r["resolved"]), "total": int(r["total"])}
            for r in trend_rows if r["yr"]
        ]

    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, out, ttl=ttl)


@router.get("/risk/entities")
async def risk_entities(
    response: Response,
    entity: str = Query("mp", pattern="^(mp|mla|state)$"),
    sort: str = Query("score", pattern="^(score|flagged|utilization|alpha)$"),
    state_id: int = Query(None),
    level: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(9, ge=1, le=50),
):
    """Risk-ranked members or states."""
    cache_key, ttl = _cacheable(
        "risk_entities", "members_list",  # use a shorter TTL group
        entity, sort, state_id, (level or "").lower(), page, page_size,
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()
    offset = (page - 1) * page_size

    def _levels(level):
        if not level:
            return None
        lv = []
        for x in level.split(","):
            x = x.strip().upper()
            if not x:
                continue
            lv.append("NORMAL" if x == "LOW" else x)
        return lv or None

    if entity == "state":
        order = {
            "score": "anomaly_score DESC NULLS LAST",
            "flagged": "flagged_works DESC NULLS LAST",
            "utilization": "fund_utilization_pct DESC NULLS LAST",
            "alpha": "state_name ASC",
        }.get(sort, "anomaly_score DESC NULLS LAST")
        where = ""
        args = []
        lv = _levels(level)
        if lv:
            where = "WHERE UPPER(anomaly_level) = ANY($1)"
            args = [lv]
        total = int(await db2.fetchval(f"SELECT COUNT(*) FROM public.state_metrics {where}", *args) or 0)
        rows = await db2.fetch(f"""
            SELECT state_id AS id, state_name AS name, 'State'::text AS member_type, state_name AS state_name,
                   anomaly_score, anomaly_level, confidence_level, flagged_works, high_risk_works,
                   cost_anomaly_works, duration_anomaly_works, risk_rate_pct AS flagged_rate_pct,
                   fund_utilization_pct, completion_rate_pct, performance_classification, rank
            FROM public.state_metrics {where}
            ORDER BY {order} LIMIT {page_size} OFFSET {offset}
        """, *args)
    else:
        mt = "MP" if entity == "mp" else "MLA"
        conds = ["member_type = $1"]
        args = [mt]
        if state_id:
            conds.append(f"state_id = ${len(args) + 1}"); args.append(state_id)
        lv = _levels(level)
        if lv:
            conds.append(f"UPPER(anomaly_level) = ANY(${len(args) + 1})"); args.append(lv)
        where = "WHERE " + " AND ".join(conds)
        order = {
            "score": "anomaly_score DESC NULLS LAST",
            "flagged": "flagged_works DESC NULLS LAST",
            "utilization": "fund_utilization_pct DESC NULLS LAST",
            "alpha": "member_name ASC",
        }.get(sort, "anomaly_score DESC NULLS LAST")
        total = int(await db2.fetchval(f"SELECT COUNT(*) FROM public.member_metrics {where}", *args) or 0)
        rows = await db2.fetch(f"""
            SELECT member_id AS id, member_name AS name, member_type, state_name,
                   anomaly_score, anomaly_level, confidence_level, flagged_works, high_risk_works,
                   cost_anomaly_works, duration_anomaly_works, flagged_rate_pct,
                   fund_utilization_pct, completion_rate_pct, performance_classification, rank
            FROM public.member_metrics {where}
            ORDER BY {order} LIMIT {page_size} OFFSET {offset}
        """, *args)

    total_pages = max(1, (total + page_size - 1) // page_size)
    value = {"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)


@router.get("/risk/alerts")
async def risk_alerts(response: Response, limit: int = Query(6, ge=1, le=50), entity_type: str = Query("all", pattern="^(all|mp|mla|state)$")):
    """Top entities by anomaly score."""
    cache_key, ttl = _cacheable("risk_alerts", "risk_alerts", limit, entity_type)
    cached = _cache_get(cache_key)
    if cached is not None:
        _with_cache_headers(response, ttl)
        return cached
    db2 = await get_db2_pool()
    out = []

    async def fetch_members():
        if entity_type not in ("all", "mp", "mla"):
            return []
        if entity_type == "mp":
            w = "WHERE member_type = 'MP'"
        elif entity_type == "mla":
            w = "WHERE member_type = 'MLA'"
        else:
            w = "WHERE member_type IN ('MP','MLA')"
        return await db2.fetch(f"""
            SELECT member_id AS id, member_name AS name, member_type, state_name,
                   anomaly_score, anomaly_level, confidence_level, flagged_works, high_risk_works, flagged_rate_pct
            FROM public.member_metrics {w}
            ORDER BY anomaly_score DESC NULLS LAST LIMIT {limit}
        """)

    async def fetch_states():
        if entity_type not in ("all", "state"):
            return []
        return await db2.fetch(f"""
            SELECT state_id AS id, state_name AS name, 'State'::text AS member_type, state_name,
                   anomaly_score, anomaly_level, confidence_level, flagged_works, high_risk_works,
                   risk_rate_pct AS flagged_rate_pct
            FROM public.state_metrics
            ORDER BY anomaly_score DESC NULLS LAST LIMIT {limit}
        """)

    member_rows, state_rows = await asyncio.gather(fetch_members(), fetch_states(), return_exceptions=True)
    if not isinstance(member_rows, Exception):
        for r in member_rows:
            d = dict(r); d["entity_type"] = (d.get("member_type") or "").lower(); out.append(d)
    if not isinstance(state_rows, Exception):
        for r in state_rows:
            d = dict(r); d["entity_type"] = "state"; out.append(d)
    out.sort(key=lambda x: -(x.get("anomaly_score") or 0))
    value = {"items": out[:limit]}
    _with_cache_headers(response, ttl)
    return _cache_set(cache_key, value, ttl=ttl)
