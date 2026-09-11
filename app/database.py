import asyncpg
from app.config import settings

_pool_db1: asyncpg.Pool | None = None
_pool_db2: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """DB1 — raw data + Phase A analytics."""
    global _pool_db1
    if _pool_db1 is None:
        _pool_db1 = await asyncpg.create_pool(dsn=settings.DATABASE_URL, min_size=1, max_size=5, statement_cache_size=0)
    return _pool_db1


async def get_db2_pool() -> asyncpg.Pool:
    """DB2 — application analytics, classifications, AI analysis."""
    global _pool_db2
    if _pool_db2 is None:
        dsn = settings.DB2_DATABASE_URL
        if not dsn:
            raise RuntimeError("DB2_DATABASE_URL not configured")
        _pool_db2 = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5, statement_cache_size=0)
    return _pool_db2


async def close_pool() -> None:
    global _pool_db1, _pool_db2
    if _pool_db1 is not None:
        await _pool_db1.close()
        _pool_db1 = None
    if _pool_db2 is not None:
        await _pool_db2.close()
        _pool_db2 = None
