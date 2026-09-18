import psycopg2
import sys
from datetime import datetime

DB1_CONN = "postgresql://postgres:!2026Sih2026@db.szmepsgyekvmxbmumaep.supabase.co:5432/postgres"
DB2_CONN = "postgresql://postgres:!2026Sih2026@db.nhtrvpsqfztuuiitydlh.supabase.co:5432/postgres"

def connect_db(conn_str, db_name):
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    print(f"✅ Connected to {db_name}")
    return conn

def run_query(conn, query, query_name):
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        cursor.close()
        return {"success": True, "columns": columns, "results": results, "query": query}
    except Exception as e:
        return {"success": False, "error": str(e), "query": query}

def format_results(result, query_name):
    output = []
    output.append(f"\n{'='*60}")
    output.append(f"📊 {query_name}")
    output.append(f"{'='*60}")
    if not result["success"]:
        output.append(f"❌ Error: {result['error']}")
        return "\n".join(output)
    if not result["results"]:
        output.append("No results returned.")
        return "\n".join(output)
    columns = result["columns"]
    rows = result["results"]
    col_widths = [len(str(col)) for col in columns]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val) if val is not None else "NULL"))
    header = " | ".join(str(col).ljust(col_widths[i]) for i, col in enumerate(columns))
    output.append(header)
    output.append("-" * len(header))
    for i, row in enumerate(rows[:100]):
        line = " | ".join(str(val if val is not None else "NULL").ljust(col_widths[i]) for i, val in enumerate(row))
        output.append(line)
    if len(rows) > 100:
        output.append(f"... and {len(rows) - 100} more rows")
    output.append(f"Total rows: {len(rows)}")
    return "\n".join(output)

def main():
    print("=" * 70)
    print("🔍 FORENSIC AUDIT - FIX-UP QUERIES FOR FAILED ITEMS")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    db1 = connect_db(DB1_CONN, "DB1 (Source)")
    db2 = connect_db(DB2_CONN, "DB2 (Intelligence)")

    # ===== FIX 1: DB1 has mps and mlas tables instead of members =====
    print("\n" + "=" * 70)
    print("📋 FIX 1: DB1 - Using mps/mlas tables instead of members")
    print("=" * 70)

    # Discover mps columns
    result = run_query(db1, "SELECT column_name FROM information_schema.columns WHERE table_name = 'mps' ORDER BY ordinal_position;", "mps columns")
    print(format_results(result, "mps columns"))

    result = run_query(db1, "SELECT column_name FROM information_schema.columns WHERE table_name = 'mlas' ORDER BY ordinal_position;", "mlas columns")
    print(format_results(result, "mlas columns"))

    # MP count
    result = run_query(db1, "SELECT 'source_mps' as label, COUNT(*) as cnt FROM mps;", "MP count (mps table)")
    print(format_results(result, "MP count (mps table)"))

    # MLA count
    result = run_query(db1, "SELECT 'source_mlas' as label, COUNT(*) as cnt FROM mlas;", "MLA count (mlas table)")
    print(format_results(result, "MLA count (mlas table)"))

    # Total members
    result = run_query(db1, """
        SELECT 'total_members' as label, 
        (SELECT COUNT(*) FROM mps) + (SELECT COUNT(*) FROM mlas) as cnt;
    """, "Total members (mps+mlas)")
    print(format_results(result, "Total members (mps+mlas)"))

    # Duplicate member check in mps
    result = run_query(db1, """
        SELECT member_id, 'MP' as member_type, COUNT(*) as cnt FROM mps 
        GROUP BY member_id HAVING COUNT(*) > 1;
    """, "Duplicate member check in mps")
    print(format_results(result, "Duplicate member check in mps"))

    # Duplicate member check in mlas
    result = run_query(db1, """
        SELECT member_id, 'MLA' as member_type, COUNT(*) as cnt FROM mlas 
        GROUP BY member_id HAVING COUNT(*) > 1;
    """, "Duplicate member check in mlas")
    print(format_results(result, "Duplicate member check in mlas"))

    # Same name different IDs in mps
    result = run_query(db1, """
        SELECT name, 'MP' as member_type, COUNT(DISTINCT member_id) as id_count FROM mps 
        GROUP BY name HAVING COUNT(DISTINCT member_id) > 1 ORDER BY id_count DESC LIMIT 30;
    """, "Same name different IDs in mps")
    print(format_results(result, "Same name different IDs in mps"))

    # Same name different IDs in mlas
    result = run_query(db1, """
        SELECT name, 'MLA' as member_type, COUNT(DISTINCT member_id) as id_count FROM mlas 
        GROUP BY name HAVING COUNT(DISTINCT member_id) > 1 ORDER BY id_count DESC LIMIT 30;
    """, "Same name different IDs in mlas")
    print(format_results(result, "Same name different IDs in mlas"))

    # Rahul Gandhi check in mps
    result = run_query(db1, """
        SELECT member_id, 'MP' as member_type, name, state_name FROM mps WHERE name ILIKE '%rahul%gandhi%';
    """, "Rahul Gandhi in mps")
    print(format_results(result, "Rahul Gandhi in mps"))

    # Rahul Gandhi check in mlas
    result = run_query(db1, """
        SELECT member_id, 'MLA' as member_type, name, state_name FROM mlas WHERE name ILIKE '%rahul%gandhi%';
    """, "Rahul Gandhi in mlas")
    print(format_results(result, "Rahul Gandhi in mlas"))

    # ===== FIX 2: DB2 member_intelligence - find correct columns =====
    print("\n" + "=" * 70)
    print("📋 FIX 2: DB2 member_intelligence - Rahul Gandhi query")
    print("=" * 70)

    result = run_query(db2, """
        SELECT member_id, member_type, performance_score_100, performance_label, 
               national_rank, national_percentile, peer_rank, peer_percentile, 
               cluster_id, cluster_label, risk_level
        FROM member_intelligence 
        WHERE member_id IN (144, 355);
    """, "Rahul Gandhi in member_intelligence (fixed)")
    print(format_results(result, "Rahul Gandhi in member_intelligence (fixed)"))

    # ===== FIX 3: Classification doesn't exist - find what classification-like columns exist =====
    print("\n" + "=" * 70)
    print("📋 FIX 3: DB2 member_metrics - classification-like columns")
    print("=" * 70)

    # Check for classification/ranking columns in member_metrics
    result = run_query(db2, """
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'member_metrics' 
        AND (column_name ILIKE '%class%' OR column_name ILIKE '%tier%' OR column_name ILIKE '%grade%' 
             OR column_name ILIKE '%rank%' OR column_name ILIKE '%label%')
        ORDER BY ordinal_position;
    """, "Classification-like columns in member_metrics")
    print(format_results(result, "Classification-like columns in member_metrics"))

    # Try ranking_qualified and performance_label
    result = run_query(db2, """
        SELECT ranking_qualified, COUNT(*) as cnt FROM member_metrics GROUP BY ranking_qualified ORDER BY cnt DESC;
    """, "ranking_qualified distribution")
    print(format_results(result, "ranking_qualified distribution"))

    result = run_query(db2, """
        SELECT performance_label, COUNT(*) as cnt FROM member_metrics GROUP BY performance_label ORDER BY cnt DESC;
    """, "performance_label distribution (member_metrics)")
    print(format_results(result, "performance_label distribution (member_metrics)"))

    # ===== FIX 4: Raw works table columns =====
    print("\n" + "=" * 70)
    print("📋 FIX 4: DB1 raw works table columns")
    print("=" * 70)

    for tbl in ['work_sanctions', 'work_completions', 'work_recommendations']:
        result = run_query(db1, f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = '{tbl}' ORDER BY ordinal_position;
        """, f"{tbl} columns")
        print(format_results(result, f"{tbl} columns"))

    # Count with correct column names
    result = run_query(db1, "SELECT 'mp_work_sanctions' as label, COUNT(*) as cnt FROM work_sanctions;", "mp_work_sanctions (all)")
    print(format_results(result, "mp_work_sanctions (all)"))

    result = run_query(db1, "SELECT 'mp_work_completions' as label, COUNT(*) as cnt FROM work_completions;", "mp_work_completions (all)")
    print(format_results(result, "mp_work_completions (all)"))

    result = run_query(db1, "SELECT 'mp_work_recommendations' as label, COUNT(*) as cnt FROM work_recommendations;", "mp_work_recommendations (all)")
    print(format_results(result, "mp_work_recommendations (all)"))

    # Also check works table and phase_a_work_unified
    result = run_query(db1, "SELECT 'works_total' as label, COUNT(*) as cnt FROM works;", "works total")
    print(format_results(result, "works total"))

    result = run_query(db1, "SELECT 'phase_a_work_unified' as label, COUNT(*) as cnt FROM phase_a_work_unified;", "phase_a_work_unified total")
    print(format_results(result, "phase_a_work_unified total"))

    # ===== ADDITIONAL: DB1 mps/mlas full counts =====
    print("\n" + "=" * 70)
    print("📋 ADDITIONAL: DB1 member details")
    print("=" * 70)

    result = run_query(db1, """
        SELECT 'mps_total' as label, COUNT(*) as cnt FROM mps
        UNION ALL
        SELECT 'mlas_total', COUNT(*) FROM mlas
        UNION ALL
        SELECT 'constituencies_total', COUNT(*) FROM constituencies
        UNION ALL
        SELECT 'states_total', COUNT(*) FROM states
        UNION ALL
        SELECT 'work_analysis_total', COUNT(*) FROM work_analysis
        UNION ALL
        SELECT 'mla_work_analysis_total', COUNT(*) FROM mla_work_analysis;
    """, "DB1 population summary")
    print(format_results(result, "DB1 population summary"))

    # ===== ADDITIONAL: DB2 orphan/missing check using mps/mlas =====
    print("\n" + "=" * 70)
    print("📋 ADDITIONAL: Cross-database integrity")
    print("=" * 70)

    # Check if DB2 member_metrics has any records not matching DB1 mps or mlas
    # (Can't do cross-DB join, so check column names match)
    result = run_query(db2, """
        SELECT 
            SUM(CASE WHEN member_type = 'MP' THEN 1 ELSE 0 END) as mp_count,
            SUM(CASE WHEN member_type = 'MLA' THEN 1 ELSE 0 END) as mla_count,
            SUM(CASE WHEN member_type NOT IN ('MP', 'MLA') THEN 1 ELSE 0 END) as other_count
        FROM member_metrics;
    """, "DB2 member_metrics type breakdown")
    print(format_results(result, "DB2 member_metrics type breakdown"))

    # DB2 member_intelligence type breakdown
    result = run_query(db2, """
        SELECT 
            SUM(CASE WHEN member_type = 'MP' THEN 1 ELSE 0 END) as mp_count,
            SUM(CASE WHEN member_type = 'MLA' THEN 1 ELSE 0 END) as mla_count,
            SUM(CASE WHEN member_type NOT IN ('MP', 'MLA') THEN 1 ELSE 0 END) as other_count
        FROM member_intelligence;
    """, "DB2 member_intelligence type breakdown")
    print(format_results(result, "DB2 member_intelligence type breakdown"))

    # Null checks
    result = run_query(db2, """
        SELECT 
            'mm_performance_score_nulls' as label, COUNT(*) as cnt FROM member_metrics WHERE performance_score_weighted IS NULL
        UNION ALL
        SELECT 'mm_completion_rate_nulls', COUNT(*) FROM member_metrics WHERE completion_rate_pct IS NULL
        UNION ALL
        SELECT 'mm_fund_utilization_nulls', COUNT(*) FROM member_metrics WHERE fund_utilization_pct IS NULL
        UNION ALL
        SELECT 'mm_scale_score_nulls', COUNT(*) FROM member_metrics WHERE scale_score IS NULL
        UNION ALL
        SELECT 'mm_national_rank_nulls', COUNT(*) FROM member_metrics WHERE national_rank IS NULL
        UNION ALL
        SELECT 'mm_national_percentile_nulls', COUNT(*) FROM member_metrics WHERE national_percentile IS NULL;
    """, "DB2 member_metrics null counts")
    print(format_results(result, "DB2 member_metrics null counts"))

    # member_intelligence nulls
    result = run_query(db2, """
        SELECT 
            'mi_national_rank_nulls' as label, COUNT(*) as cnt FROM member_intelligence WHERE national_rank IS NULL
        UNION ALL
        SELECT 'mi_national_percentile_nulls', COUNT(*) FROM member_intelligence WHERE national_percentile IS NULL
        UNION ALL
        SELECT 'mi_peer_rank_nulls', COUNT(*) FROM member_intelligence WHERE peer_rank IS NULL
        UNION ALL
        SELECT 'mi_risk_level_nulls', COUNT(*) FROM member_intelligence WHERE risk_level IS NULL
        UNION ALL
        SELECT 'mi_cluster_id_nulls', COUNT(*) FROM member_intelligence WHERE cluster_id IS NULL;
    """, "DB2 member_intelligence null counts")
    print(format_results(result, "DB2 member_intelligence null counts"))

    # Rahul in DB1 with correct table
    result = run_query(db1, """
        SELECT member_id, 'MP' as type, name, state_name FROM mps WHERE name ILIKE '%gandhi%'
        UNION ALL
        SELECT member_id, 'MLA' as type, name, state_name FROM mlas WHERE name ILIKE '%gandhi%';
    """, "Gandhi in DB1 (mps+mlas)")
    print(format_results(result, "Gandhi in DB1 (mps+mlas)"))

    # ===== DB1 mps/mlas schema =====
    print("\n" + "=" * 70)
    print("📋 DB1 mps table sample")
    print("=" * 70)
    result = run_query(db1, "SELECT * FROM mps LIMIT 5;", "mps sample")
    print(format_results(result, "mps sample"))

    result = run_query(db1, "SELECT * FROM mlas LIMIT 5;", "mlas sample")
    print(format_results(result, "mlas sample"))

    db1.close()
    db2.close()
    print("\n✅ Fix-up audit complete.")

if __name__ == "__main__":
    main()
