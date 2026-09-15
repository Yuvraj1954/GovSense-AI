"""Isolation Forest anomaly detection for works and member/state aggregates."""
import datetime
from typing import List, Dict, Any
import numpy as np
from sklearn.ensemble import IsolationForest
import asyncpg
from automation.intelligence.database import db2_pool


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


FEATURES = [
    "sanction_amount", "expenditure_percentage", "completion_percentage",
    "sanction_delay_days", "execution_days", "project_age_days",
    "cost_deviation_from_median_percentage", "duration_deviation_from_median_percentage"
]


def _work_vector(row: asyncpg.Record) -> List[float]:
    return [
        np.log1p(_safe_float(row["sanction_amount"])),
        _safe_float(row["expenditure_percentage"]),
        _safe_float(row["completion_percentage"]),
        _safe_float(row["sanction_delay_days"]),
        _safe_float(row["execution_days"]),
        _safe_float(row["project_age_days"]),
        _safe_float(row["cost_deviation_from_median_percentage"]),
        _safe_float(row["duration_deviation_from_median_percentage"]),
    ]


async def run_isolation_forest() -> Dict[str, Any]:
    """Train Isolation Forest on combined work_analysis features and score works.

    Writes ml_work_anomaly in DB2 and updates work_analysis/mla_work_analysis with
    isolation_score/isolation_level.
    """
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            mp_rows = await conn.fetch("SELECT * FROM work_analysis")
            mla_rows = await conn.fetch("SELECT * FROM mla_work_analysis")

        all_rows = list(mp_rows) + list(mla_rows)
        if len(all_rows) < 10:
            return {
                "status": "NOT_READY",
                "reason": f"insufficient works: {len(all_rows)}",
                "n_observations": len(all_rows),
            }

        X = np.array([_work_vector(r) for r in all_rows], dtype=float)
        # Handle NaN/Inf
        X = np.nan_to_num(X, nan=0.0, posinf=1e6, neginf=-1e6)

        model = IsolationForest(
            n_estimators=200,
            contamination="auto",
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X)
        scores = model.decision_function(X)  # lower = more anomalous

        # Convert decision_function to 0-100 anomaly score where higher = more anomalous
        # decision_function is roughly [-0.5, 0.5]
        anomaly_scores = [100.0 * (0.5 - s) for s in scores]

        def level(score: float) -> str:
            if score >= 80:
                return "HIGHLY_UNUSUAL"
            if score >= 60:
                return "UNUSUAL"
            return "NORMAL"

        anomaly_records = []
        updates_mp = []
        updates_mla = []
        for i, r in enumerate(all_rows):
            score = anomaly_scores[i]
            lvl = level(score)
            member_type = "MP" if i < len(mp_rows) else "MLA"
            wid = _safe_int(r["work_id"])
            anomaly_records.append((
                member_type, wid, float(score), lvl == "UNUSUAL" or lvl == "HIGHLY_UNUSUAL",
                "isolation_forest", "1.0.0", "v1", datetime.datetime.now(datetime.timezone.utc)
            ))
            if member_type == "MP":
                updates_mp.append((float(score), lvl, wid))
            else:
                updates_mla.append((float(score), lvl, wid))

        async with p2.acquire() as conn:
            await conn.execute("TRUNCATE TABLE ml_work_anomaly RESTART IDENTITY CASCADE")
            if anomaly_records:
                cols = ["member_type", "work_id", "ml_anomaly_score", "ml_anomaly_flag",
                        "model_name", "model_version", "feature_version", "calculated_at"]
                batch_size = 10000
                for i in range(0, len(anomaly_records), batch_size):
                    await conn.copy_records_to_table(
                        "ml_work_anomaly",
                        records=anomaly_records[i:i + batch_size],
                        columns=cols,
                    )
            if updates_mp:
                await conn.executemany("""
                    UPDATE work_analysis
                    SET isolation_score = $1, isolation_level = $2
                    WHERE work_id = $3
                """, updates_mp)
            if updates_mla:
                await conn.executemany("""
                    UPDATE mla_work_analysis
                    SET isolation_score = $1, isolation_level = $2
                    WHERE work_id = $3
                """, updates_mla)

        return {
            "status": "READY",
            "model_name": "isolation_forest",
            "model_version": "1.0.0",
            "model_type": "IsolationForest",
            "training_observations": len(X),
            "features": FEATURES,
            "n_estimators": 200,
            "contamination": "auto",
            "score_min": float(min(anomaly_scores)),
            "score_max": float(max(anomaly_scores)),
            "mean_score": float(np.mean(anomaly_scores)),
        }
    finally:
        await p2.close()


async def aggregate_anomaly_scores() -> Dict[str, Any]:
    """Propagate work anomaly scores to member_metrics and state_metrics."""
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            # Member aggregates — join ml_work_anomaly via work_analysis to get member_id
            member_rows = await conn.fetch("""
                SELECT m.member_id, m.member_type, COALESCE(AVG(an.ml_anomaly_score), 0) AS avg_score,
                       COUNT(an.work_id) FILTER (WHERE an.ml_anomaly_score >= 80) AS highly_unusual,
                       COUNT(an.work_id) FILTER (WHERE an.ml_anomaly_score >= 60) AS unusual,
                       COUNT(an.work_id) AS total
                FROM member_metrics m
                LEFT JOIN (
                    SELECT work_id, member_id, member_type, state_id FROM work_analysis
                    UNION ALL
                    SELECT work_id, member_id, member_type, state_id FROM mla_work_analysis
                ) w ON w.member_id = m.member_id AND w.member_type = m.member_type
                LEFT JOIN ml_work_anomaly an
                  ON an.work_id = w.work_id AND an.member_type = w.member_type
                GROUP BY m.member_id, m.member_type
            """)
            for r in member_rows:
                avg_score = float(r["avg_score"])
                total = _safe_int(r["total"])
                if total == 0:
                    level = "NORMAL"
                    conf = "LOW"
                elif avg_score >= 80:
                    level = "HIGHLY_UNUSUAL"
                    conf = "HIGH"
                elif avg_score >= 60:
                    level = "UNUSUAL"
                    conf = "MEDIUM"
                else:
                    level = "NORMAL"
                    conf = "HIGH" if total >= 15 else "MEDIUM"
                await conn.execute("""
                    UPDATE member_metrics
                    SET anomaly_score = $3, anomaly_level = $4, confidence_level = $5
                    WHERE member_id = $1 AND member_type = $2
                """, r["member_id"], r["member_type"], avg_score, level, conf)

            # State aggregates
            state_rows = await conn.fetch("""
                SELECT s.state_id, COALESCE(AVG(an.ml_anomaly_score), 0) AS avg_score,
                       COUNT(an.work_id) AS total
                FROM state_metrics s
                LEFT JOIN (
                    SELECT work_id, member_type, state_id FROM work_analysis
                    UNION ALL
                    SELECT work_id, member_type, state_id FROM mla_work_analysis
                ) w ON w.state_id = s.state_id
                LEFT JOIN ml_work_anomaly an
                  ON an.work_id = w.work_id AND an.member_type = w.member_type
                GROUP BY s.state_id
            """)
            for r in state_rows:
                avg_score = float(r["avg_score"])
                total = _safe_int(r["total"])
                if total == 0:
                    level = "NORMAL"
                    conf = "LOW"
                elif avg_score >= 80:
                    level = "HIGHLY_UNUSUAL"
                    conf = "HIGH"
                elif avg_score >= 60:
                    level = "UNUSUAL"
                    conf = "MEDIUM"
                else:
                    level = "NORMAL"
                    conf = "HIGH"
                await conn.execute("""
                    UPDATE state_metrics
                    SET anomaly_score = $2, anomaly_level = $3, confidence_level = $4
                    WHERE state_id = $1
                """, r["state_id"], avg_score, level, conf)

        return {"status": "READY", "member_rows": len(member_rows), "state_rows": len(state_rows)}
    finally:
        await p2.close()


async def run_all_anomaly() -> Dict[str, Any]:
    forest_meta = await run_isolation_forest()
    agg_meta = await aggregate_anomaly_scores()
    return {"isolation_forest": forest_meta, "aggregation": agg_meta}
