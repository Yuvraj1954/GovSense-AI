"""Full DB2 intelligence backfill orchestration."""
import asyncio
import datetime
from typing import Dict, Any

from automation.intelligence.work_analysis import build_all_work_analysis
from automation.intelligence.member_metrics import build_member_metrics
from automation.intelligence.state_metrics import build_state_metrics
from automation.intelligence.performance import compute_all_performance
from automation.intelligence.clustering import run_all_clustering
from automation.intelligence.anomaly import run_all_anomaly
from automation.intelligence.delay_xgb import train_and_predict_delay
from automation.intelligence.risk import run_all_risk
from automation.intelligence.intelligence_tables import build_all_intelligence
from automation.intelligence.statistics import build_all_statistics
from automation.intelligence.registry import register_model, clear_registry


P = lambda *a, **k: print("  [backfill]", *a, **k, flush=True)


async def backfill_all(intelligence: bool = True, resume_from: int = 1) -> Dict[str, Any]:
    """Run the complete DB2 intelligence generation pipeline.

    This is idempotent: it truncates and regenerates all derived DB2 tables
    from authoritative DB1 raw data.

    Use resume_from=N to skip steps 1..N-1 and continue from step N.
    """
    started = datetime.datetime.now(datetime.timezone.utc)
    results = {
        "started": started.isoformat(),
        "intelligence_enabled": intelligence,
        "resume_from": resume_from,
    }

    if resume_from <= 1:
        P("Step 1/10: building work_analysis and mla_work_analysis from DB1 raw data...")
        results["work_analysis"] = await build_all_work_analysis()
        P(f"  work_analysis={results['work_analysis'].get('mp_work_analysis')}, mla_work_analysis={results['work_analysis'].get('mla_work_analysis')}")
    else:
        P("Step 1/10: SKIPPED (resume)")

    if resume_from <= 2:
        P("Step 2/10: computing member_metrics and state_metrics in parallel...")
        member_metrics_task = build_member_metrics()
        state_metrics_task = build_state_metrics()
        results["member_metrics"], results["state_metrics"] = await asyncio.gather(member_metrics_task, state_metrics_task)
        P(f"  member_metrics={results['member_metrics']}, state_metrics={results['state_metrics']}")
    else:
        P("Step 2/10: SKIPPED (resume)")

    if intelligence:
        if resume_from <= 3:
            P("Step 3/10: computing deterministic performance scores...")
            results["performance"] = await compute_all_performance()
            P(f"  member_performance={results['performance'].get('member_performance')}, state_performance={results['performance'].get('state_performance')}")
        else:
            P("Step 3/10: SKIPPED (resume)")

        if resume_from <= 4:
            P("Step 4/10: running K-Means clustering for members and states...")
            results["clustering"] = await run_all_clustering()
            P(f"  member clusters={results['clustering'].get('member', {}).get('n_clusters')}, state clusters={results['clustering'].get('state', {}).get('n_clusters')}")
        else:
            P("Step 4/10: SKIPPED (resume)")

        if resume_from <= 5:
            P("Step 5/10: running Isolation Forest anomaly detection...")
            results["anomaly"] = await run_all_anomaly()
            P(f"  isolation_forest status={results['anomaly'].get('isolation_forest', {}).get('status')}")
        else:
            P("Step 5/10: SKIPPED (resume)")

        if resume_from <= 6:
            P("Step 6/10: training XGBoost delay prediction model...")
            results["delay_xgb"] = await train_and_predict_delay()
            P(f"  project_delay_xgb status={results['delay_xgb'].get('status')}")
        else:
            P("Step 6/10: SKIPPED (resume)")

        if resume_from <= 7:
            P("Step 7/10: computing risk scores and evidence...")
            results["risk"] = await run_all_risk()
            P(f"  member_risk={results['risk'].get('member_risk')}, state_risk={results['risk'].get('state_risk')}")
        else:
            P("Step 7/10: SKIPPED (resume)")

        if resume_from <= 8:
            P("Step 8/10: building member_intelligence and state_intelligence...")
            results["intelligence_tables"] = await build_all_intelligence()
            P(f"  member_intelligence={results['intelligence_tables'].get('member_intelligence')}, state_intelligence={results['intelligence_tables'].get('state_intelligence')}")
        else:
            P("Step 8/10: SKIPPED (resume)")

        if resume_from <= 9:
            P("Step 9/10: computing national/overall/trends/category/fy statistics...")
            results["statistics"] = await build_all_statistics()
            P(f"  national_statistics={results['statistics'].get('national_statistics')}, overall_metrics={results['statistics'].get('overall_metrics')}, trends={results['statistics'].get('trends')}, category_metrics={results['statistics'].get('category_metrics')}, fy_metrics={results['statistics'].get('fy_metrics')}")
        else:
            P("Step 9/10: SKIPPED (resume)")

        P("Step 10/10: updating model_registry...")
        await clear_registry()

        clustering = results.get("clustering", {})
        member_meta = clustering.get("member")
        if member_meta and member_meta.get("status") == "READY":
            await register_model(
                model_name="member_kmeans",
                model_version=member_meta.get("model_version", "1.0.0"),
                model_type=member_meta.get("model_type", "KMeans"),
                status="READY",
                training_observations=member_meta.get("training_observations", 0),
                features=member_meta.get("features", []),
                target="operational_profile",
                validation_method="silhouette_score",
                metrics={"silhouette_score": member_meta.get("silhouette_score"), "inertia": member_meta.get("inertia")},
                threshold={"n_clusters": member_meta.get("n_clusters")},
                calibration="standardized_features",
                extra=member_meta.get("cluster_meta"),
            )

        state_meta = clustering.get("state")
        if state_meta and state_meta.get("status") == "READY":
            await register_model(
                model_name="state_kmeans",
                model_version=state_meta.get("model_version", "1.0.0"),
                model_type=state_meta.get("model_type", "KMeans"),
                status="READY",
                training_observations=state_meta.get("training_observations", 0),
                features=state_meta.get("features", []),
                target="operational_profile",
                validation_method="silhouette_score",
                metrics={"silhouette_score": state_meta.get("silhouette_score"), "inertia": state_meta.get("inertia")},
                threshold={"n_clusters": state_meta.get("n_clusters")},
                calibration="standardized_features",
                extra=state_meta.get("cluster_meta"),
            )

        anomaly_meta = results.get("anomaly", {}).get("isolation_forest")
        if anomaly_meta:
            await register_model(
                model_name="isolation_forest",
                model_version=anomaly_meta.get("model_version", "1.0.0"),
                model_type=anomaly_meta.get("model_type", "IsolationForest"),
                status=anomaly_meta.get("status", "NOT_READY"),
                training_observations=anomaly_meta.get("training_observations", 0),
                features=anomaly_meta.get("features", []),
                target="anomaly_score",
                validation_method="unsupervised_outlier_fraction",
                metrics={"score_min": anomaly_meta.get("score_min"), "score_max": anomaly_meta.get("score_max"), "mean_score": anomaly_meta.get("mean_score")},
                threshold={"highly_unusual": 80, "unusual": 60},
                calibration="decision_function_rescaled",
            )

        delay_meta = results.get("delay_xgb")
        if delay_meta:
            await register_model(
                model_name="project_delay_xgb",
                model_version=delay_meta.get("model_version", "1.0.0"),
                model_type=delay_meta.get("model_type", "XGBClassifier"),
                status=delay_meta.get("status", "NOT_READY"),
                training_observations=delay_meta.get("training_observations", 0),
                features=delay_meta.get("features", []),
                target="slow_completion",
                validation_method="time_aware_split_by_recommendation_date",
                metrics={
                    "auc_roc": delay_meta.get("auc_roc"),
                    "average_precision": delay_meta.get("average_precision"),
                    "brier_score": delay_meta.get("brier_score"),
                },
                threshold={"high": 0.7, "medium": 0.4},
                calibration="none" if delay_meta.get("status") != "READY" else "platt_scaling_optional",
            )

    finished = datetime.datetime.now(datetime.timezone.utc)
    results["finished"] = finished.isoformat()
    results["duration_seconds"] = (finished - started).total_seconds()
    return results


if __name__ == "__main__":
    out = asyncio.run(backfill_all())
    import json
    print(json.dumps(out, indent=2, default=str))
