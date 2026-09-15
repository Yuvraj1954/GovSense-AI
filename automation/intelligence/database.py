"""Shared database utilities for GovSense AI intelligence generation."""
import os
import asyncpg
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()


async def _init_conn(conn):
    """Set a generous statement timeout on every pool connection."""
    await conn.execute("SET statement_timeout = '600000'")  # 10 minutes per statement


def db1_url() -> str:
    return os.environ["DATABASE_URL"]


def db2_url() -> str:
    return os.environ["DB2_DATABASE_URL"]


async def db1_pool(**kwargs):
    return await asyncpg.create_pool(
        db1_url(),
        min_size=1,
        max_size=4,
        statement_cache_size=0,
        command_timeout=600,
        init=_init_conn,
        **kwargs,
    )


async def db2_pool(**kwargs):
    return await asyncpg.create_pool(
        db2_url(),
        min_size=1,
        max_size=4,
        statement_cache_size=0,
        command_timeout=600,
        init=_init_conn,
        **kwargs,
    )


@asynccontextmanager
async def db1_conn():
    pool = await db1_pool()
    try:
        async with pool.acquire() as conn:
            yield conn
    finally:
        await pool.close()


@asynccontextmanager
async def db2_conn():
    pool = await db2_pool()
    try:
        async with pool.acquire() as conn:
            yield conn
    finally:
        await pool.close()


@asynccontextmanager
async def both_pools():
    p1 = await db1_pool()
    p2 = await db2_pool()
    try:
        yield p1, p2
    finally:
        await p1.close()
        await p2.close()
