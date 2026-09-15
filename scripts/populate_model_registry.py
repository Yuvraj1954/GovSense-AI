#!/usr/bin/env python3
"""Populate model_registry from existing DB2 outputs without retraining.

Use this after a resume-style backfill that did not write to model_registry,
or whenever the registry needs to be rebuilt from current DB2 state.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.intelligence.registry import register_model, clear_registry
from automation.intelligence.database import db2_pool


async def main():
    print("Populating model_registry from current DB2 state...")
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            member_cluster_count = await conn.fetchval(
                "SELECT COUNT(DISTINCT cluster_id) FROM member_metrics WHERE cluster_id IS NOT NULL"
            )
            state_cluster_count = await conn.fetchval(
                "SELECT COUNT(DISTINCT cluster_id) FROM state_metrics WHERE cluster_id IS NOT NULL"
            )
            anomaly_count = await conn.fetchval("SELECT COUNT(*) FROM ml_work_anomaly")
            delay_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM (
                    SELECT delay_probability FROM work_analysis WHERE delay_probability IS NOT NULL
                    UNION ALL
                    SELECT delay_probability FROM mla_work_analysis WHERE delay_probability IS NOT NULL
                ) t
                """
            )
    finally:
        await p2.close()

    await clear_registry()

    if member_cluster_count:
        await register_model(
            model_name="member_kmeans",
            model_version="1.0.0",
            model_type="KMeans",
            status="READY",
            training_observations=0,
            features=["performance_score", "completion_rate_pct", "fund_utilization_pct",
                      "sanction_rate_pct", "avg_execution_days", "avg_project_age_days", "flagged_rate_pct"],
            target="operational_profile",
            validation_method="silhouette_score",
            metrics={"n_clusters": member_cluster_count},
            threshold={"n_clusters": member_cluster_count},
            calibration="standardized_features",
        )
        print(f"  registered member_kmeans (clusters={member_cluster_count})")

    if state_cluster_count:
        await register_model(
            model_name="state_kmeans",
            model_version="1.0.0",
            model_type="KMeans",
            status="READY",
            training_observations=0,
            features=["performance_score", "completion_rate_pct", "fund_utilization_pct",
                      "sanction_rate_pct", "avg_execution_days", "avg_project_age_days",
                      "risk_rate_pct", "active_members"],
            target="operational_profile",
            validation_method="silhouette_score",
            metrics={"n_clusters": state_cluster_count},
            threshold={"n_clusters": state_cluster_count},
            calibration="standardized_features",
        )
        print(f"  registered state_kmeans (clusters={state_cluster_count})")

    await register_model(
        model_name="isolation_forest",
        model_version="1.0.0",
        model_type="IsolationForest",
        status="READY" if anomaly_count else "NOT_READY",
        training_observations=anomaly_count or 0,
        features=["sanction_amount", "expenditure_percentage", "completion_percentage",
                  "sanction_delay_days", "execution_days", "project_age_days",
                  "cost_deviation_from_median_percentage", "duration_deviation_from_median_percentage"],
        target="anomaly_score",
        validation_method="unsupervised_outlier_fraction",
        metrics={"anomaly_count": anomaly_count},
        threshold={"highly_unusual": 80, "unusual": 60},
        calibration="decision_function_rescaled",
    )
    print(f"  registered isolation_forest (anomalies={anomaly_count})")

    await register_model(
        model_name="project_delay_xgb",
        model_version="1.0.0",
        model_type="XGBClassifier",
        status="READY" if delay_count else "NOT_READY",
        training_observations=delay_count or 0,
        features=["sanction_amount", "recommended_amount", "cost_percentile",
                  "sanction_delay_days", "project_age_days", "expenditure_percentage",
                  "cost_deviation_from_median_percentage"],
        target="slow_completion",
        validation_method="time_aware_split_by_recommendation_date",
        metrics={"delay_predictions": delay_count},
        threshold={"high": 0.7, "medium": 0.4},
        calibration="none" if not delay_count else "platt_scaling_optional",
    )
    print(f"  registered project_delay_xgb (predictions={delay_count})")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
