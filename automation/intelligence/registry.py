"""Model registry helpers."""
import datetime
import json
from typing import Dict, Any, List
import asyncpg
from automation.intelligence.database import db2_pool


def _to_jsonb(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


async def register_model(
    model_name: str,
    model_version: str,
    model_type: str,
    status: str,
    training_observations: int,
    features: list,
    target: str,
    validation_method: str,
    metrics: Dict[str, Any],
    threshold: Dict[str, Any],
    calibration: str,
    extra: Dict[str, Any] = None,
) -> None:
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            await conn.execute("""
                INSERT INTO model_registry (
                    model_name, model_version, model_type, training_date, training_observations,
                    features, target, validation_method, metrics, threshold, calibration, status,
                    data_version, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (model_name) DO UPDATE SET
                    model_version = EXCLUDED.model_version,
                    model_type = EXCLUDED.model_type,
                    training_date = EXCLUDED.training_date,
                    training_observations = EXCLUDED.training_observations,
                    features = EXCLUDED.features,
                    target = EXCLUDED.target,
                    validation_method = EXCLUDED.validation_method,
                    metrics = EXCLUDED.metrics,
                    threshold = EXCLUDED.threshold,
                    calibration = EXCLUDED.calibration,
                    status = EXCLUDED.status,
                    data_version = EXCLUDED.data_version,
                    created_at = EXCLUDED.created_at
            """,
            model_name, model_version, model_type, datetime.datetime.now(datetime.timezone.utc),
            training_observations, _to_jsonb(features), target, validation_method, _to_jsonb(metrics), _to_jsonb(threshold),
            calibration, status, "govsense_v1", datetime.datetime.now(datetime.timezone.utc))
    finally:
        await p2.close()


async def clear_registry() -> None:
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            await conn.execute("TRUNCATE TABLE model_registry RESTART IDENTITY CASCADE")
    finally:
        await p2.close()


async def get_model_status(model_name: str) -> str:
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM model_registry WHERE model_name = $1", model_name
            )
            return row["status"] if row else "NOT_READY"
    finally:
        await p2.close()
