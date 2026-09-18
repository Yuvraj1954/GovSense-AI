#!/usr/bin/env python3
"""Manual runner for the GovSense AI DB2 intelligence backfill.

Usage:
    python run_intelligence_backfill.py
    python run_intelligence_backfill.py --resume-from 4

Environment:
    Requires DATABASE_URL and DB2_DATABASE_URL in .env or environment.
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import json
from datetime import datetime, timezone
from automation.intelligence.backfill import backfill_all

P = lambda *a, **k: print(*a, **k, flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GovSense AI DB2 intelligence backfill")
    parser.add_argument("--resume-from", type=int, default=1,
                        help="Resume from step N (1-10). Steps 1..N-1 are skipped.")
    args = parser.parse_args()

    P("=" * 70)
    P("GOVSENSE AI — DB2 INTELLIGENCE BACKFILL (PHASE 4)")
    P("=" * 70)
    P(f"Started: {datetime.now(timezone.utc).isoformat()}")
    P(f"Resume from step: {args.resume_from}")
    P("Loading environment and connecting to DB1 + DB2...")

    try:
        result = asyncio.run(backfill_all(intelligence=True, resume_from=args.resume_from))
    except Exception as e:
        P(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    P("\n" + "=" * 70)
    P("BACKFILL COMPLETE")
    P("=" * 70)
    P(f"Finished: {result.get('finished')}")
    P(f"Duration: {result.get('duration_seconds', 0):.1f}s")
    P("\nWork analysis:")
    P(json.dumps(result.get("work_analysis", {}), indent=2))
    P("\nMetrics counts:")
    P(f"  member_metrics: {result.get('member_metrics', 0)}")
    P(f"  state_metrics: {result.get('state_metrics', 0)}")
    P(f"  member_intelligence: {result.get('intelligence_tables', {}).get('member_intelligence', 0)}")
    P(f"  state_intelligence: {result.get('intelligence_tables', {}).get('state_intelligence', 0)}")
    P("\nML model statuses:")
    P(f"  isolation_forest: {result.get('anomaly', {}).get('isolation_forest', {}).get('status')}")
    P("\nStatistics:")
    P(json.dumps(result.get("statistics", {}), indent=2, default=str))
    P("\nFull result JSON:")
    P(json.dumps(result, indent=2, default=str))
