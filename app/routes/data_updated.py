from datetime import datetime
import time

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from app.database import get_pool

router = APIRouter()


class DataUpdatedResponse(BaseModel):
    completed_at: datetime
    status: str


_cache_store: dict = {}


def _cache_get(key):
    e = _cache_store.get(key)
    if e and (time.time() - e["t"]) < e["ttl"]:
        return e["v"]
    return None


def _cache_set(key, value, ttl=300):
    _cache_store[key] = {"t": time.time(), "ttl": ttl, "v": value}
    return value


@router.get("/data-updated", response_model=DataUpdatedResponse)
async def get_data_updated(response: Response):
    cached = _cache_get("data_updated")
    if cached is not None:
        # Dynamic status endpoint: never let a browser/proxy cache a response
        # that a newer frontend might read with a different schema.
        response.headers["Cache-Control"] = "no-store"
        return cached
    pool = await get_pool()
    try:
        row = await pool.fetchrow("SELECT completed_at, status FROM public.data_updated WHERE id = 1")
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")

    if row is None:
        raise HTTPException(status_code=404, detail="Data updated record not found")

    value = DataUpdatedResponse(
        completed_at=row["completed_at"],
        status=row["status"],
    )
    response.headers["Cache-Control"] = "no-store"
    return _cache_set("data_updated", value, ttl=60)
