"""K-Means operational profiling for members and states."""
import datetime
import json
from typing import List, Dict, Any, Optional
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import asyncpg
from automation.intelligence.database import db2_pool


def _safe_float(val) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _select_k(X: np.ndarray, k_range: range) -> int:
    """Select k by silhouette score. Fallback to 3 if no clear winner."""
    if len(X) < max(k_range):
        return min(2, len(X))
    best_k = 3
    best_score = -1.0
    for k in k_range:
        if k >= len(X):
            break
        try:
            labels = KMeans(n_clusters=k, random_state=42, n_init="auto").fit_predict(X)
            if len(set(labels)) < 2:
                continue
            score = silhouette_score(X, labels)
            if score > best_score:
                best_score = score
                best_k = k
        except Exception:
            continue
    return best_k


def _label_for_cluster(centroid: np.ndarray, feature_names: List[str]) -> str:
    """Produce a short descriptive label from scaled centroid values."""
    # centroid is in standardized space; find most extreme dimensions
    values = dict(zip(feature_names, centroid.tolist()))
    sorted_dims = sorted(values.items(), key=lambda x: abs(x[1]), reverse=True)
    top = sorted_dims[:2]
    parts = []
    for name, val in top:
        direction = "HIGH" if val > 0 else "LOW"
        parts.append(f"{direction}_{name.upper()}")
    return " | ".join(parts) if parts else "AVERAGE_PROFILE"


async def cluster_members() -> Dict[str, Any]:
    """Run K-Means profiling on members and return model metadata."""
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("""
                SELECT member_id, member_type, performance_score, completion_rate_pct,
                       fund_utilization_pct, sanction_rate_pct, sanctioned_works,
                       completed_works, avg_execution_days, avg_project_age_days,
                       flagged_rate_pct, allocated_amount
                FROM member_metrics
                WHERE total_works > 0
            """)
            if not rows:
                return {"status": "NOT_READY", "reason": "no qualifying members", "n": 0}

            feature_names = [
                "performance_score", "completion_rate_pct", "fund_utilization_pct",
                "sanction_rate_pct", "avg_execution_days", "avg_project_age_days",
                "flagged_rate_pct"
            ]
            X = []
            ids = []
            for r in rows:
                vec = [
                    _safe_float(r["performance_score"]),
                    min(100.0, _safe_float(r["completion_rate_pct"])),
                    min(100.0, _safe_float(r["fund_utilization_pct"])),
                    min(100.0, _safe_float(r["sanction_rate_pct"])),
                    _safe_float(r["avg_execution_days"]),
                    _safe_float(r["avg_project_age_days"]),
                    min(100.0, _safe_float(r["flagged_rate_pct"])),
                ]
                X.append(vec)
                ids.append((r["member_id"], r["member_type"]))

            X = np.array(X, dtype=float)
            scaler = StandardScaler()
            Xs = scaler.fit_transform(X)

            k = _select_k(Xs, range(2, min(8, len(Xs))))
            model = KMeans(n_clusters=k, random_state=42, n_init="auto")
            labels = model.fit_predict(Xs)

            # Compute silhouette if possible
            silhouette = None
            if len(set(labels)) > 1 and len(Xs) > k:
                try:
                    silhouette = float(silhouette_score(Xs, labels))
                except Exception:
                    pass

            # Assign labels and centroids
            cluster_meta = {}
            for cid in range(k):
                centroid = model.cluster_centers_[cid]
                cluster_meta[cid] = {
                    "label": _label_for_cluster(centroid, feature_names),
                    "size": int(sum(1 for lab in labels if lab == cid)),
                }

            # Update member_metrics with cluster_id and cluster_label
            await conn.executemany("""
                UPDATE member_metrics
                SET cluster_id = $3,
                    cluster_label = $4
                WHERE member_id = $1 AND member_type = $2
            """, [(ids[i][0], ids[i][1], int(labels[i]), cluster_meta[int(labels[i])]["label"]) for i in range(len(ids))])

            return {
                "status": "READY",
                "model_name": "member_kmeans",
                "model_version": "1.0.0",
                "model_type": "KMeans",
                "training_observations": len(Xs),
                "features": feature_names,
                "n_clusters": k,
                "silhouette_score": silhouette,
                "cluster_meta": cluster_meta,
                "inertia": float(model.inertia_),
            }
    finally:
        await p2.close()


async def cluster_states() -> Dict[str, Any]:
    """Run K-Means profiling on states and return model metadata."""
    p2 = await db2_pool()
    try:
        async with p2.acquire() as conn:
            rows = await conn.fetch("""
                SELECT state_id, performance_score, completion_rate_pct,
                       fund_utilization_pct, sanction_rate_pct, avg_execution_days,
                       avg_project_age_days, risk_rate_pct, active_members, total_works
                FROM state_metrics
                WHERE total_works > 0
            """)
            if not rows:
                return {"status": "NOT_READY", "reason": "no qualifying states", "n": 0}

            feature_names = [
                "performance_score", "completion_rate_pct", "fund_utilization_pct",
                "sanction_rate_pct", "avg_execution_days", "avg_project_age_days",
                "risk_rate_pct", "active_members"
            ]
            X = []
            ids = []
            for r in rows:
                vec = [
                    _safe_float(r["performance_score"]),
                    min(100.0, _safe_float(r["completion_rate_pct"])),
                    min(100.0, _safe_float(r["fund_utilization_pct"])),
                    min(100.0, _safe_float(r["sanction_rate_pct"])),
                    _safe_float(r["avg_execution_days"]),
                    _safe_float(r["avg_project_age_days"]),
                    min(100.0, _safe_float(r["risk_rate_pct"])),
                    _safe_float(r["active_members"]),
                ]
                X.append(vec)
                ids.append(r["state_id"])

            X = np.array(X, dtype=float)
            scaler = StandardScaler()
            Xs = scaler.fit_transform(X)

            k = _select_k(Xs, range(2, min(6, len(Xs))))
            model = KMeans(n_clusters=k, random_state=42, n_init="auto")
            labels = model.fit_predict(Xs)

            silhouette = None
            if len(set(labels)) > 1 and len(Xs) > k:
                try:
                    silhouette = float(silhouette_score(Xs, labels))
                except Exception:
                    pass

            cluster_meta = {}
            for cid in range(k):
                centroid = model.cluster_centers_[cid]
                cluster_meta[cid] = {
                    "label": _label_for_cluster(centroid, feature_names),
                    "size": int(sum(1 for lab in labels if lab == cid)),
                }

            await conn.executemany("""
                UPDATE state_metrics
                SET cluster_id = $2,
                    cluster_label = $3
                WHERE state_id = $1
            """, [(ids[i], int(labels[i]), cluster_meta[int(labels[i])]["label"]) for i in range(len(ids))])

            return {
                "status": "READY",
                "model_name": "state_kmeans",
                "model_version": "1.0.0",
                "model_type": "KMeans",
                "training_observations": len(Xs),
                "features": feature_names,
                "n_clusters": k,
                "silhouette_score": silhouette,
                "cluster_meta": cluster_meta,
                "inertia": float(model.inertia_),
            }
    finally:
        await p2.close()


async def run_all_clustering() -> Dict[str, Dict[str, Any]]:
    member_meta = await cluster_members()
    state_meta = await cluster_states()
    return {"member": member_meta, "state": state_meta}
