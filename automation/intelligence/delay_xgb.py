"""XGBoost project-delay prediction."""
import datetime
from typing import List, Dict, Any, Optional
import numpy as np
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
    "sanction_amount",
    "recommended_amount",
    "cost_percentile",
    "sanction_delay_days",
    "project_age_days",
    "expenditure_percentage",
    "cost_deviation_from_median_percentage",
]


def _features(row: asyncpg.Record) -> List[float]:
    return [
        np.log1p(_safe_float(row["sanction_amount"])),
        np.log1p(_safe_float(row["recommended_amount"])),
        _safe_float(row["cost_percentile"]),
        _safe_float(row["sanction_delay_days"]),
        _safe_float(row["project_age_days"]),
        _safe_float(row["expenditure_percentage"]),
        _safe_float(row["cost_deviation_from_median_percentage"]),
    ]


async def _load_labeled_works(p2: asyncpg.Pool):
    """Load completed works with known execution_days for supervised training."""
    async with p2.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM work_analysis WHERE status = 'COMPLETED' AND execution_days IS NOT NULL
            UNION ALL
            SELECT * FROM mla_work_analysis WHERE status = 'COMPLETED' AND execution_days IS NOT NULL
        """)
    return rows


async def train_and_predict_delay() -> Dict[str, Any]:
    """Train XGBoost to predict slow_completion and apply to relevant works.

    Target: slow_completion = execution_days > 365.
    Uses time-aware split by recommendation_date if available, otherwise random split.
    """
    p2 = await db2_pool()
    try:
        import xgboost as xgb
        rows = await _load_labeled_works(p2)
        if len(rows) < 50:
            return {
                "status": "NOT_READY",
                "reason": f"insufficient completed works: {len(rows)}",
                "n_observations": len(rows),
            }

        X = []
        y = []
        dates = []
        for r in rows:
            X.append(_features(r))
            y.append(1 if _safe_int(r["execution_days"]) > 365 else 0)
            dates.append(r["recommendation_date"])

        X = np.array(X, dtype=float)
        X = np.nan_to_num(X, nan=0.0, posinf=1e6, neginf=-1e6)
        y = np.array(y, dtype=int)

        if len(set(y)) < 2:
            return {
                "status": "NOT_READY",
                "reason": "single-class target after filtering",
                "class_distribution": {int(k): int(v) for k, v in zip(*np.unique(y, return_counts=True))},
            }

        # Time-aware split: sort by recommendation_date, use last 20% as test
        sort_idx = np.argsort([d.isoformat() if d else "1900-01-01" for d in dates])
        split_point = int(0.8 * len(sort_idx))
        train_idx = sort_idx[:split_point]
        test_idx = sort_idx[split_point:]

        if len(train_idx) < 10 or len(test_idx) < 5 or len(set(y[test_idx])) < 2:
            # Fallback to random stratified split if time split is degenerate
            from sklearn.model_selection import train_test_split
            train_idx, test_idx = train_test_split(
                np.arange(len(y)), test_size=0.2, random_state=42, stratify=y
            )

        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        scale_pos_weight = float(np.sum(y_train == 0) / max(1, np.sum(y_train == 1)))

        model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="binary:logistic",
            eval_metric="logloss",
            scale_pos_weight=scale_pos_weight,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train, y_train)

        from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
        y_proba = model.predict_proba(X_test)[:, 1]
        try:
            auc = float(roc_auc_score(y_test, y_proba))
        except Exception:
            auc = None
        try:
            ap = float(average_precision_score(y_test, y_proba))
        except Exception:
            ap = None
        try:
            brier = float(brier_score_loss(y_test, y_proba))
        except Exception:
            brier = None

        # Predict on all ongoing works
        async with p2.acquire() as conn:
            all_rows = await conn.fetch("""
                SELECT 'MP' AS member_type, work_id, recommendation_date, sanction_date, completion_date,
                       status, execution_days, sanction_amount, recommended_amount, cost_percentile,
                       project_age_days, expenditure_percentage, cost_deviation_from_median_percentage
                FROM work_analysis
                UNION ALL
                SELECT 'MLA' AS member_type, work_id, recommendation_date, sanction_date, completion_date,
                       status, execution_days, sanction_amount, recommended_amount, cost_percentile,
                       project_age_days, expenditure_percentage, cost_deviation_from_median_percentage
                FROM mla_work_analysis
            """)

        updates_mp = []
        updates_mla = []
        for r in all_rows:
            features = np.array([_features(r)], dtype=float)
            features = np.nan_to_num(features, nan=0.0, posinf=1e6, neginf=-1e6)
            proba = float(model.predict_proba(features)[0, 1])
            band = "HIGH" if proba >= 0.7 else ("MEDIUM" if proba >= 0.4 else "LOW")
            if r["member_type"] == "MP":
                updates_mp.append((proba, band, r["work_id"]))
            else:
                updates_mla.append((proba, band, r["work_id"]))

        async with p2.acquire() as conn:
            if updates_mp:
                await conn.executemany("""
                    UPDATE work_analysis
                    SET delay_probability = $1, delay_risk_band = $2
                    WHERE work_id = $3
                """, updates_mp)
            if updates_mla:
                await conn.executemany("""
                    UPDATE mla_work_analysis
                    SET delay_probability = $1, delay_risk_band = $2
                    WHERE work_id = $3
                """, updates_mla)

        return {
            "status": "READY",
            "model_name": "project_delay_xgb",
            "model_version": "1.0.0",
            "model_type": "XGBClassifier",
            "training_observations": len(X_train),
            "test_observations": len(X_test),
            "features": FEATURES,
            "class_distribution": {int(k): int(v) for k, v in zip(*np.unique(y, return_counts=True))},
            "auc_roc": auc,
            "average_precision": ap,
            "brier_score": brier,
            "scale_pos_weight": scale_pos_weight,
        }
    except ImportError as e:
        return {
            "status": "NOT_READY",
            "reason": f"dependency missing: {e}",
        }
    except Exception as e:
        return {
            "status": "NOT_READY",
            "reason": str(e),
        }
    finally:
        await p2.close()
