#!/usr/bin/env python3
"""
Daily pipeline classification step.

This module is imported by the daily pipeline after the main analytics run.
It reads from DB2 (member_metrics, state_metrics),
classifies all entities using the 200-point system, and writes back to DB2.

TODO: DAILY PIPELINE — MP/MLA/STATE PERFORMANCE CLASSIFICATION
    Recalculate the same DB2 performance_score and performance_classification
    during the daily pipeline after the underlying analysis/precomputed metrics
    have been refreshed. Persist updated labels and scores to DB2.
    Use exactly the same 200-point classification algorithm.

Usage from pipeline:
    from app.classification import run_classification
    result = await run_classification(db2_pool)
"""

import asyncio
import sys
import os
import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings
from app.classification import run_classification


async def pipeline_classify():
    """Run classification as part of the daily pipeline."""
    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=15)

    class FakePool:
        def __init__(self, conn):
            self._conn = conn
        async def fetch(self, query, *args):
            return await self._conn.fetch(query, *args)
        async def execute(self, query, *args):
            return await self._conn.execute(query, *args)

    result = await run_classification(FakePool(db2))

    await db2.close()
    return result


if __name__ == "__main__":
    result = asyncio.run(pipeline_classify())
    print(f"Classification complete: {result}")
