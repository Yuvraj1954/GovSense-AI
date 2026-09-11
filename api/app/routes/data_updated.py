from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_pool

router = APIRouter()


class DataUpdatedResponse(BaseModel):
    completed_at: datetime
    status: str


@router.get("/data-updated", response_model=DataUpdatedResponse)
async def get_data_updated():
    pool = await get_pool()
    try:
        row = await pool.fetchrow("SELECT completed_at, status FROM public.data_updated WHERE id = 1")
    except Exception:
        raise HTTPException(status_code=500, detail="Database error")

    if row is None:
        raise HTTPException(status_code=404, detail="Data updated record not found")

    return DataUpdatedResponse(
        completed_at=row["completed_at"],
        status=row["status"],
    )
