from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
import time

from app.database import get_db2_pool

router = APIRouter()

# Lightweight in-process TTL cache, mirroring the pattern in routes/dashboard.py.
_cache_store: dict = {}


def _cache_get(key):
    e = _cache_store.get(key)
    if e and (time.time() - e["t"]) < e["ttl"]:
        return e["v"]
    return None


def _cache_set(key, value, ttl=300):
    _cache_store[key] = {"t": time.time(), "ttl": ttl, "v": value}
    return value


def _with_cache_headers(response: Response, max_age: int):
    response.headers["Cache-Control"] = f"public, max-age={max_age}"


class ClassificationDistItem(BaseModel):
    classification: str
    count: int


class ClassificationDistResponse(BaseModel):
    items: list[ClassificationDistItem]
    total: int


class MemberClassificationResponse(BaseModel):
    member_id: int
    member_type: str
    member_name: str
    state_name: str | None
    house_name: str | None
    tenure: str | None
    performance_score: float | None
    performance_classification: str
    total_works: int
    recommended_works: int
    sanctioned_works: int
    completed_works: int
    ongoing_works: int
    pending_works: int
    completion_rate_pct: float | None
    sanction_rate_pct: float | None
    allocated_amount: float | None
    recommended_amount: float | None
    sanctioned_amount: float | None
    expenditure_amount: float | None
    fund_utilization_pct: float | None
    anomaly_level: str | None
    flagged_rate_pct: float | None
    high_risk_rate_pct: float | None
    avg_sanction_delay_days: float | None
    avg_execution_days: float | None
    overdue_over_1_year: int | None
    overdue_over_2_years: int | None


class StateClassificationResponse(BaseModel):
    state_id: int
    state_name: str
    performance_score: float | None
    performance_classification: str
    total_works: int
    completed_works: int
    completion_rate_pct: float | None
    fund_utilization_pct: float | None


@router.get("/classification/distribution", response_model=ClassificationDistResponse)
async def get_member_classification_distribution(response: Response):
    cached = _cache_get("class_dist")
    if cached is not None:
        _with_cache_headers(response, 300)
        return cached
    pool = await get_db2_pool()
    try:
        rows = await pool.fetch(
            "SELECT performance_classification as classification, count(*) as count "
            "FROM public.member_metrics "
            "GROUP BY performance_classification "
            "ORDER BY count DESC"
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")

    items = [ClassificationDistItem(classification=r["classification"], count=r["count"]) for r in rows]
    total = sum(i.count for i in items)
    value = ClassificationDistResponse(items=items, total=total)
    _with_cache_headers(response, 300)
    return _cache_set("class_dist", value, ttl=300)


@router.get("/classification/member/{member_id}", response_model=MemberClassificationResponse)
async def get_member_classification(member_id: int):
    pool = await get_db2_pool()
    try:
        row = await pool.fetchrow(
            "SELECT member_id, member_type, member_name, state_name, house_name, tenure, "
            "performance_score, performance_classification, "
            "total_works, recommended_works, sanctioned_works, completed_works, ongoing_works, pending_works, "
            "completion_rate_pct, sanction_rate_pct, "
            "allocated_amount, recommended_amount, sanctioned_amount, expenditure_amount, "
            "fund_utilization_pct, anomaly_level, flagged_rate_pct, high_risk_rate_pct, "
            "avg_sanction_delay_days, avg_execution_days, overdue_over_1_year, overdue_over_2_years "
            "FROM public.member_metrics WHERE member_id = $1",
            member_id,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")

    if row is None:
        raise HTTPException(status_code=404, detail="Member not found")

    return MemberClassificationResponse(**dict(row))


@router.get("/classification/states", response_model=list[StateClassificationResponse])
async def get_state_classifications(response: Response):
    cached = _cache_get("class_states")
    if cached is not None:
        _with_cache_headers(response, 300)
        return cached
    pool = await get_db2_pool()
    try:
        rows = await pool.fetch(
            "SELECT state_id, state_name, performance_score, performance_classification, "
            "total_works, completed_works, completion_rate_pct, fund_utilization_pct "
            "FROM public.state_metrics "
            "ORDER BY state_name"
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")

    value = [StateClassificationResponse(**dict(r)) for r in rows]
    _with_cache_headers(response, 300)
    return _cache_set("class_states", value, ttl=300)


@router.get("/classification/member/{member_id}/evidence")
async def get_member_evidence(member_id: int):
    pool = await get_db2_pool()
    try:
        # First get member name and type
        member = await pool.fetchrow(
            "SELECT member_name, member_type FROM public.member_metrics WHERE member_id = $1",
            member_id
        )
        if member is None:
            return {"evidence": None}
        
        # Now get evidence by name and type
        row = await pool.fetchrow(
            "SELECT evidence FROM public.entity_evidence "
            "WHERE entity_name = $1 AND entity_type = $2 "
            "ORDER BY evidence_version DESC LIMIT 1",
            member["member_name"], member["member_type"]
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")
    if row is None:
        return {"evidence": None}
    return {"evidence": dict(row).get("evidence")}


@router.get("/classification/member/{member_id}/analysis")
async def get_member_analysis(member_id: int):
    pool = await get_db2_pool()
    try:
        # First get member name and type
        member = await pool.fetchrow(
            "SELECT member_name, member_type FROM public.member_metrics WHERE member_id = $1",
            member_id
        )
        if member is None:
            return {"analysis": None}
        
        # Now get analysis by name and type
        row = await pool.fetchrow(
            "SELECT analysis_text, model, prompt_version, generated_at FROM public.ai_analysis "
            "WHERE entity_name = $1 AND entity_type = $2 "
            "ORDER BY generated_at DESC LIMIT 1",
            member["member_name"], member["member_type"]
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")
    if row is None:
        return {"analysis": None}
    r = dict(row)
    return {"analysis": r.get("analysis_text"), "model": r.get("model"), "generated_at": str(r.get("generated_at", ""))}
