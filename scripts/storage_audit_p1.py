#!/usr/bin/env python3
"""
GovSense DB1 / DB2 storage architecture audit.
READ-ONLY. No DELETE/DROP/TRUNCATE/ALTER/UPDATE/INSERT.
"""

import asyncio
import asyncpg
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

P = lambda *a, **k: print(*a, **k, flush=True)


async def db_size(pool, name):
    P(f"\n{'='*70}")
    P(f"{name} DATABASE SIZE")
    P(f"{'='*70}")
    row = await pool.fetchrow("""
        SELECT pg_size_pretty(pg_database_size(current_database())) as total_size,
               pg_database_size(current_database()) as total_bytes
    """)
    P(f"Total database size: {row['total_size']} ({row['total_bytes']:,} bytes)")


async def table_audit(pool, name):
    P(f"\n{'='*70}")
    P(f"{name} TABLE AUDIT")
    P(f"{'='*70}")
    P(f"{'Table':<40} {'Rows':>10} {'Data':>10} {'Index':>10} {'Toast':>10} {'Total':>10} {'Purpose'}")
    P("-" * 110)
    rows = await pool.fetch("""
        SELECT c.relname as table_name,
               c.reltuples::bigint as estimated_rows,
               pg_size_pretty(pg_relation_size(c.oid)) as data_size,
               pg_size_pretty(pg_indexes_size(c.oid)) as index_size,
               pg_size_pretty(pg_total_relation_size(c.oid) - pg_relation_size(c.oid) - pg_indexes_size(c.oid)) as toast_size,
               pg_size_pretty(pg_total_relation_size(c.oid)) as total_size,
               pg_total_relation_size(c.oid) as total_bytes
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
        ORDER BY pg_total_relation_size(c.oid) DESC
    """)
    total_bytes = 0
    for r in rows:
        total_bytes += r['total_bytes']
        P(f"{r['table_name']:<40} {r['estimated_rows']:>10,} {r['data_size']:>10} {r['index_size']:>10} {r['toast_size']:>10} {r['total_size']:>10}")
    P(f"{'TOTAL':<40} {'':>10} {'':>10} {'':>10} {'':>10} {pg_size_pretty(total_bytes):>10}")
    return rows


def pg_size_pretty(bytes_val):
    for unit in ['B', 'kB', 'MB', 'GB']:
        if bytes_val < 1024:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.2f} TB"


async def index_audit(pool, name):
    P(f"\n{'='*70}")
    P(f"{name} INDEX AUDIT")
    P(f"{'='*70}")
    P(f"{'Index':<50} {'Table':<35} {'Size':>8} {'Columns'}")
    P("-" * 120)
    rows = await pool.fetch("""
        SELECT schemaname, tablename, indexname,
               pg_size_pretty(pg_relation_size(c.oid)) as index_size,
               pg_get_indexdef(c.oid) as index_def
        FROM pg_indexes i
        JOIN pg_class c ON c.relname = i.indexname
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = i.schemaname
        WHERE i.schemaname = 'public'
        ORDER BY pg_relation_size(c.oid) DESC
    """)
    for r in rows:
        # Extract columns roughly from indexdef
        idxdef = r['index_def']
        P(f"{r['indexname']:<50} {r['tablename']:<35} {r['index_size']:>8}")
    return rows


async def column_null_stats(pool, table_name):
    """Get null % and distinct % for columns in a table."""
    cols = await pool.fetch("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
    """, table_name)
    
    total = await pool.fetchval(f"SELECT COUNT(*) FROM public.{table_name}")
    if total == 0:
        return []
    
    results = []
    for c in cols:
        col = c['column_name']
        # Use a safe identifier
        nulls = await pool.fetchval(f'SELECT COUNT(*) FROM public."{table_name}" WHERE "{col}" IS NULL')
        distinct = await pool.fetchval(f'SELECT COUNT(DISTINCT "{col}") FROM public."{table_name}"')
        results.append({
            'column': col,
            'type': c['data_type'],
            'null_pct': round(nulls / total * 100, 2),
            'distinct_pct': round(distinct / total * 100, 2),
            'total_rows': total,
        })
    return results


async def main():
    P("="*70)
    P("GOVSENSE DB1 / DB2 STORAGE ARCHITECTURE AUDIT")
    P("READ-ONLY — no data modification")
    P("="*70)
    P(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    
    db1 = await asyncpg.connect(dsn=settings.DATABASE_URL, timeout=30)
    db2 = await asyncpg.connect(dsn=settings.DB2_DATABASE_URL, timeout=30)
    
    await db_size(db1, "DB1")
    db1_tables = await table_audit(db1, "DB1")
    await index_audit(db1, "DB1")
    
    await db_size(db2, "DB2")
    db2_tables = await table_audit(db2, "DB2")
    await index_audit(db2, "DB2")
    
    # Column stats for largest tables
    P(f"\n{'='*70}")
    P("COLUMN NULL/DISTINCT STATS FOR LARGEST TABLES")
    P(f"{'='*70}")
    for db_name, db_conn, tables in [("DB1", db1, db1_tables[:8]), ("DB2", db2, db2_tables[:8])]:
        P(f"\n--- {db_name} ---")
        for t in tables:
            tn = t['table_name']
            P(f"\nTable: {tn} (~{t['estimated_rows']:,} rows)")
            stats = await column_null_stats(db_conn, tn)
            P(f"{'Column':<35} {'Type':<20} {'Null%':>8} {'Distinct%':>10}")
            P("-" * 80)
            for s in stats:
                P(f"{s['column']:<35} {s['type']:<20} {s['null_pct']:>8.1f} {s['distinct_pct']:>10.1f}")
    
    await db1.close()
    await db2.close()


if __name__ == "__main__":
    asyncio.run(main())
