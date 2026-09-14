#!/usr/bin/env python3
"""
GovSense ML readiness gate.

Reads model_registry and reports readiness for each intelligence capability.
Does NOT train models — it validates the persisted production state.
"""

import asyncio
import asyncpg
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

P = lambda *a, **k: print(*a, **k, flush=True)


async def main():
    P("=" * 70)
    P("GOVSENSE ML READINESS GATE")
    P("=" * 70)
    P(f"Started: {datetime.now(timezone.utc).isoformat()}")

    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=30)

    models = await db2.fetch("SELECT * FROM public.model_registry ORDER BY model_name")

    P("\n--- Registered Models ---")
    all_ready = True
    for m in models:
        name = m["model_name"]
        status = m["status"]
        observations = m["training_observations"]
        metrics = m["metrics"]
        method = m["validation_method"]
        ready = status == "READY"
        if not ready:
            all_ready = False
        P(f"\n{name}")
        P(f"  status:      {status}")
        P(f"  version:     {m['model_version']}")
        P(f"  type:        {m['model_type']}")
        P(f"  trained:     {m['training_date']}")
        P(f"  observations:{observations}")
        P(f"  features:    {m['features']}")
        P(f"  target:      {m['target']}")
        P(f"  validation:  {method}")
        P(f"  metrics:     {metrics}")
        P(f"  -> {'READY' if ready else 'NOT_READY'}")

    # Representative / state profiling are inferred from cluster labels in
    # member_intelligence and state_intelligence.
    P("\n--- Profiling Capabilities ---")
    mi_clusters = await db2.fetch("SELECT DISTINCT cluster_id, cluster_label FROM public.member_intelligence ORDER BY cluster_id")
    si_clusters = await db2.fetch("SELECT DISTINCT cluster_id, cluster_label FROM public.state_intelligence ORDER BY cluster_id")

    P("Representative profiling (member_intelligence):")
    for r in mi_clusters:
        P(f"  cluster {r['cluster_id']}: {r['cluster_label']}")
    # Null cluster_id is acceptable if it carries an honest descriptive label
    rep_ready = len(mi_clusters) > 0 and all(
        r["cluster_label"] and r["cluster_label"].strip().lower() not in ("", "none")
        for r in mi_clusters
    )
    P(f"  -> {'READY' if rep_ready else 'NOT_READY'}")

    P("\nState profiling (state_intelligence):")
    for r in si_clusters:
        P(f"  cluster {r['cluster_id']}: {r['cluster_label']}")
    state_ready = len(si_clusters) > 0 and all(r["cluster_label"] for r in si_clusters)
    P(f"  -> {'READY' if state_ready else 'NOT_READY'}")

    # Isolation Forest readiness
    if_ready = any(m["model_name"] == "isolation_forest" and m["status"] == "READY" for m in models)
    P("\nIsolation Forest:")
    P(f"  -> {'READY' if if_ready else 'NOT_READY'}")

    # XGBoost delay readiness
    xgb_ready = any(m["model_name"] == "project_delay_xgb" and m["status"] == "READY" for m in models)
    P("\nProject Delay XGBoost:")
    P(f"  -> {'READY' if xgb_ready else 'NOT_READY'}")
    xgb_model = next((m for m in models if m["model_name"] == "project_delay_xgb"), None)
    if xgb_model:
        P(f"  reason: {xgb_model['metrics']}")

    await db2.close()

    P(f"\nOverall ML readiness: {'READY' if all_ready else 'NOT_READY'}")
    P("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
