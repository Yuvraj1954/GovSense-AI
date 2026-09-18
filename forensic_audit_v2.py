import psycopg2
from psycopg2 import sql, errorcodes
import sys
from datetime import datetime

# Database connection strings
DB1_CONN = "postgresql://postgres:!2026Sih2026@db.szmepsgyekvmxbmumaep.supabase.co:5432/postgres"
DB2_CONN = "postgresql://postgres:!2026Sih2026@db.nhtrvpsqfztuuiitydlh.supabase.co:5432/postgres"

def connect_db(conn_str, db_name):
    try:
        conn = psycopg2.connect(conn_str)
        conn.autocommit = True  # Use autocommit to avoid transaction abort cascading
        print(f"✅ Connected to {db_name}")
        return conn
    except Exception as e:
        print(f"❌ Failed to connect to {db_name}: {e}")
        return None

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
    
    for i, row in enumerate(rows[:50]):
        line = " | ".join(str(val if val is not None else "NULL").ljust(col_widths[i]) for i, val in enumerate(row))
        output.append(line)
    
    if len(rows) > 50:
        output.append(f"... and {len(rows) - 50} more rows")
    
    output.append(f"Total rows: {len(rows)}")
    return "\n".join(output)

def main():
    print("=" * 70)
    print("🔍 FORENSIC AUDIT REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    db1 = connect_db(DB1_CONN, "DB1 (Source)")
    db2 = connect_db(DB2_CONN, "DB2 (Intelligence)")
    
    if not db1 or not db2:
        print("❌ Cannot proceed without database connections")
        sys.exit(1)
    
    all_results = []
    
    # ========== DISCOVER TABLES FIRST ==========
    print("\n" + "=" * 70)
    print("📋 DISCOVERING TABLES")
    print("=" * 70)
    
    # DB1 tables
    result = run_query(db1, """
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' ORDER BY table_name;
    """, "DB1 Tables")
    print(format_results(result, "DB1 Tables"))
    db1_tables = set(row[0] for row in result["results"]) if result["success"] else set()
    
    # DB2 tables
    result = run_query(db2, """
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public' ORDER BY table_name;
    """, "DB2 Tables")
    print(format_results(result, "DB2 Tables"))
    db2_tables = set(row[0] for row in result["results"]) if result["success"] else set()
    
    # ========== QUERY SET 1 - DB1 SOURCE POPULATION ==========
    print("\n" + "=" * 70)
    print("📋 QUERY SET 1 - DB1 SOURCE POPULATION")
    print("=" * 70)
    
    queries_db1 = [
        ("MP count from members table", "SELECT 'source_mps' as label, COUNT(*) as cnt FROM members WHERE member_type = 'MP';"),
        ("MLA count from members table", "SELECT 'source_mlas' as label, COUNT(*) as cnt FROM members WHERE member_type = 'MLA';"),
        ("Total members count", "SELECT 'total_members' as label, COUNT(*) as cnt FROM members;"),
        ("State count", "SELECT 'source_states' as label, COUNT(*) as cnt FROM states;"),
        ("Constituency count", "SELECT 'source_constituencies' as label, COUNT(*) as cnt FROM constituencies;"),
        ("Work analysis counts", "SELECT 'db1_work_analysis' as label, COUNT(*) as cnt FROM work_analysis;"),
        ("MLA work analysis counts", "SELECT 'db1_mla_work_analysis' as label, COUNT(*) as cnt FROM mla_work_analysis;"),
        ("Duplicate member check", """SELECT member_id, member_type, COUNT(*) as cnt FROM members GROUP BY member_id, member_type HAVING COUNT(*) > 1;"""),
        ("Same name different IDs", """SELECT name, member_type, COUNT(DISTINCT member_id) as id_count FROM members GROUP BY name, member_type HAVING COUNT(DISTINCT member_id) > 1 ORDER BY id_count DESC LIMIT 30;"""),
        ("Rahul Gandhi check", """SELECT member_id, member_type, name, state_name FROM members WHERE name ILIKE '%rahul%gandhi%';"""),
        ("Duplicate in work_analysis", """SELECT member_id, member_type, COUNT(*) FROM work_analysis GROUP BY member_id, member_type HAVING COUNT(*) > 1 LIMIT 20;"""),
        ("Duplicate in mla_work_analysis", """SELECT member_id, member_type, COUNT(*) FROM mla_work_analysis GROUP BY member_id, member_type HAVING COUNT(*) > 1 LIMIT 20;"""),
    ]
    
    for name, query in queries_db1:
        result = run_query(db1, query, name)
        print(format_results(result, name))
        all_results.append((name, "DB1", result))
    
    # ========== QUERY SET 2 - DB2 DERIVED POPULATION ==========
    print("\n" + "=" * 70)
    print("📋 QUERY SET 2 - DB2 DERIVED POPULATION")
    print("=" * 70)
    
    queries_db2 = [
        ("Member metrics counts", "SELECT 'db2_member_metrics' as label, COUNT(*) as cnt FROM member_metrics;"),
        ("Member metrics MP", "SELECT 'db2_mm_mp' as label, COUNT(*) as cnt FROM member_metrics WHERE member_type = 'MP';"),
        ("Member metrics MLA", "SELECT 'db2_mm_mla' as label, COUNT(*) as cnt FROM member_metrics WHERE member_type = 'MLA';"),
        ("State metrics", "SELECT 'db2_state_metrics' as label, COUNT(*) as cnt FROM state_metrics;"),
        ("Member intelligence", "SELECT 'db2_member_intelligence' as label, COUNT(*) as cnt FROM member_intelligence;"),
        ("Member intelligence MP", "SELECT 'db2_mi_mp' as label, COUNT(*) as cnt FROM member_intelligence WHERE member_type = 'MP';"),
        ("Member intelligence MLA", "SELECT 'db2_mi_mla' as label, COUNT(*) as cnt FROM member_intelligence WHERE member_type = 'MLA';"),
        ("State intelligence", "SELECT 'db2_state_intelligence' as label, COUNT(*) as cnt FROM state_intelligence;"),
        ("Duplicate in member_metrics", """SELECT member_id, member_type, COUNT(*) as cnt FROM member_metrics GROUP BY member_id, member_type HAVING COUNT(*) > 1 ORDER BY cnt DESC LIMIT 20;"""),
        ("Duplicate in member_intelligence", """SELECT member_id, member_type, COUNT(*) as cnt FROM member_intelligence GROUP BY member_id, member_type HAVING COUNT(*) > 1 ORDER BY cnt DESC LIMIT 20;"""),
        ("Score distribution", """SELECT 
  CASE 
    WHEN performance_score_weighted BETWEEN 0 AND 10 THEN '0-10'
    WHEN performance_score_weighted BETWEEN 10 AND 20 THEN '10-20'
    WHEN performance_score_weighted BETWEEN 20 AND 30 THEN '20-30'
    WHEN performance_score_weighted BETWEEN 30 AND 40 THEN '30-40'
    WHEN performance_score_weighted BETWEEN 40 AND 50 THEN '40-50'
    WHEN performance_score_weighted BETWEEN 50 AND 60 THEN '50-60'
    WHEN performance_score_weighted BETWEEN 60 AND 70 THEN '60-70'
    WHEN performance_score_weighted BETWEEN 70 AND 80 THEN '70-80'
    WHEN performance_score_weighted BETWEEN 80 AND 90 THEN '80-90'
    WHEN performance_score_weighted BETWEEN 90 AND 100 THEN '90-100'
    ELSE 'NULL/other'
  END as score_bucket,
  COUNT(*) as cnt
FROM member_metrics
GROUP BY score_bucket ORDER BY score_bucket;"""),
    ]
    
    for name, query in queries_db2:
        result = run_query(db2, query, name)
        print(format_results(result, name))
        all_results.append((name, "DB2", result))
    
    # Discover actual column names for member_metrics and member_intelligence
    print("\n" + "=" * 70)
    print("📋 DISCOVERING COLUMN NAMES")
    print("=" * 70)
    
    result = run_query(db2, """
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'member_metrics' ORDER BY ordinal_position;
    """, "member_metrics columns")
    print(format_results(result, "member_metrics columns"))
    mm_columns = set(row[0] for row in result["results"]) if result["success"] else set()
    
    result = run_query(db2, """
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'member_intelligence' ORDER BY ordinal_position;
    """, "member_intelligence columns")
    print(format_results(result, "member_intelligence columns"))
    mi_columns = set(row[0] for row in result["results"]) if result["success"] else set()
    
    # Build dynamic queries based on actual columns
    print("\n" + "=" * 70)
    print("📋 QUERY SET 2 (CONTINUED) - DYNAMIC QUERIES")
    print("=" * 70)
    
    # Rahul Gandhi in member_metrics
    mm_cols_to_select = ['member_id', 'member_type', 'member_name']
    for col in ['performance_score_weighted', 'completion_rate_pct', 'fund_utilization_pct', 'scale_score', 'rank', 'percentile', 'percentile_rank', 'classification']:
        if col in mm_columns:
            mm_cols_to_select.append(col)
    
    rahul_mm_query = f"""SELECT {', '.join(mm_cols_to_select)} FROM member_metrics WHERE member_id IN (144, 355) OR member_name ILIKE '%rahul%gandhi%';"""
    result = run_query(db2, rahul_mm_query, "Rahul Gandhi in member_metrics (fixed)")
    print(format_results(result, "Rahul Gandhi in member_metrics (fixed)"))
    all_results.append(("Rahul Gandhi in member_metrics (fixed)", "DB2", result))
    
    # Rahul Gandhi in member_intelligence
    mi_cols_to_select = ['member_id', 'member_type', 'member_name']
    for col in ['circular_score', 'performance_label', 'national_rank', 'percentile', 'percentile_rank', 'peer_rank', 'peer_percentile', 'cluster', 'risk_level']:
        if col in mi_columns:
            mi_cols_to_select.append(col)
    
    rahul_mi_query = f"""SELECT {', '.join(mi_cols_to_select)} FROM member_intelligence WHERE member_id IN (144, 355) OR member_name ILIKE '%rahul%gandhi%';"""
    result = run_query(db2, rahul_mi_query, "Rahul Gandhi in member_intelligence (fixed)")
    print(format_results(result, "Rahul Gandhi in member_intelligence (fixed)"))
    all_results.append(("Rahul Gandhi in member_intelligence (fixed)", "DB2", result))
    
    # Classification distribution
    result = run_query(db2, "SELECT classification, COUNT(*) as cnt FROM member_metrics GROUP BY classification ORDER BY cnt DESC;", "Classification distribution")
    print(format_results(result, "Classification distribution"))
    all_results.append(("Classification distribution", "DB2", result))
    
    # Rank nulls - use actual column names
    rank_col = 'rank' if 'rank' in mm_columns else None
    percentile_col = 'percentile' if 'percentile' in mm_columns else ('percentile_rank' if 'percentile_rank' in mm_columns else None)
    
    if rank_col:
        result = run_query(db2, f"SELECT 'mm_rank_nulls' as label, COUNT(*) as cnt FROM member_metrics WHERE {rank_col} IS NULL;", "Rank nulls")
        print(format_results(result, "Rank nulls"))
        all_results.append(("Rank nulls", "DB2", result))
    
    if percentile_col:
        result = run_query(db2, f"SELECT 'mm_percentile_nulls' as label, COUNT(*) as cnt FROM member_metrics WHERE {percentile_col} IS NULL;", "Percentile nulls")
        print(format_results(result, "Percentile nulls"))
        all_results.append(("Percentile nulls", "DB2", result))
    
    # ML tables
    ml_tables = [
        ("db2_ml_work_anomaly", "ml_work_anomaly"),
        ("db2_overall_metrics", "overall_metrics"),
        ("db2_national_statistics", "national_statistics"),
        ("db2_trends", "trends"),
        ("db2_category_metrics", "category_metrics"),
        ("db2_fy_metrics", "fy_metrics"),
        ("db2_entity_evidence", "entity_evidence"),
        ("db2_model_registry", "model_registry"),
    ]
    
    for label, table in ml_tables:
        if table in db2_tables:
            result = run_query(db2, f"SELECT '{label}' as label, COUNT(*) as cnt FROM {table};", label)
            print(format_results(result, label))
            all_results.append((label, "DB2", result))
        else:
            print(f"\n⚠️  Table '{table}' does not exist in DB2")
            all_results.append((label, "DB2", {"success": False, "error": f"Table '{table}' does not exist", "query": f"SELECT FROM {table}"}))
    
    # ========== QUERY SET 3 - MATH VERIFICATION ==========
    print("\n" + "=" * 70)
    print("📋 QUERY SET 3 - MATH VERIFICATION")
    print("=" * 70)
    
    # Rahul Gandhi score formula verification
    rahul_verify = f"""SELECT 
  member_id, member_name, member_type,
  completion_rate_pct,
  fund_utilization_pct,
  scale_score,
  performance_score_weighted as stored_score,
  (0.40 * completion_rate_pct + 0.40 * fund_utilization_pct + 0.20 * scale_score) as expected_score,
  ABS(performance_score_weighted - (0.40 * completion_rate_pct + 0.40 * fund_utilization_pct + 0.20 * scale_score)) as diff
FROM member_metrics 
WHERE member_id = 355;"""
    result = run_query(db2, rahul_verify, "Rahul Gandhi score formula verification (DB2)")
    print(format_results(result, "Rahul Gandhi score formula verification (DB2)"))
    all_results.append(("Rahul Gandhi score formula verification (DB2)", "DB2", result))
    
    # Overall mismatch check
    mismatch_query = f"""SELECT 
  COUNT(*) as total,
  SUM(CASE WHEN ABS(performance_score_weighted - (0.40 * COALESCE(completion_rate_pct,0) + 0.40 * COALESCE(fund_utilization_pct,0) + 0.20 * COALESCE(scale_score,0))) > 0.01 THEN 1 ELSE 0 END) as mismatches
FROM member_metrics;"""
    result = run_query(db2, mismatch_query, "Overall mismatch check (DB2)")
    print(format_results(result, "Overall mismatch check (DB2)"))
    all_results.append(("Overall mismatch check (DB2)", "DB2", result))
    
    # ========== QUERY SET 4 - WORK ANALYSIS INTEGRITY ==========
    print("\n" + "=" * 70)
    print("📋 QUERY SET 4 - WORK ANALYSIS INTEGRITY")
    print("=" * 70)
    
    queries_wa_db1 = [
        ("Work analysis total", "SELECT 'wa_total' as label, COUNT(*) as cnt FROM work_analysis;"),
        ("Work analysis unique work IDs", "SELECT 'wa_unique_work_ids' as label, COUNT(DISTINCT work_id) as cnt FROM work_analysis;"),
        ("Work analysis unique members", "SELECT 'wa_unique_members' as label, COUNT(DISTINCT member_id || '-' || member_type) as cnt FROM work_analysis;"),
        ("MLA work analysis total", "SELECT 'mwa_total' as label, COUNT(*) as cnt FROM mla_work_analysis;"),
        ("MLA work analysis unique work IDs", "SELECT 'mwa_unique_work_ids' as label, COUNT(DISTINCT work_id) as cnt FROM mla_work_analysis;"),
        ("MLA work analysis unique members", "SELECT 'mwa_unique_members' as label, COUNT(DISTINCT member_id || '-' || member_type) as cnt FROM mla_work_analysis;"),
        ("Work ID collisions", """SELECT COUNT(*) as colliding_work_ids FROM work_analysis w
INNER JOIN mla_work_analysis mw ON w.work_id = mw.work_id;"""),
    ]
    
    for name, query in queries_wa_db1:
        result = run_query(db1, query, name)
        print(format_results(result, name))
        all_results.append((name, "DB1", result))
    
    # Raw works tables
    raw_tables = [
        ("mp_work_sanctions", "work_sanctions", "mp_id"),
        ("mp_work_completions", "work_completions", "mp_id"),
        ("mp_work_expenditures", "work_expenditures", "mp_id"),
        ("mp_work_recommendations", "work_recommendations", "mp_id"),
        ("mp_allocations", "mp_allocations", None),
    ]
    
    for label, table, col in raw_tables:
        if table in db1_tables:
            query = f"SELECT '{label}' as label, COUNT(*) as cnt FROM {table}" + (f" WHERE {col} IS NOT NULL;" if col else ";")
            result = run_query(db1, query, label)
            print(format_results(result, label))
            all_results.append((label, "DB1", result))
        else:
            print(f"\n⚠️  Table '{table}' does not exist in DB1")
            all_results.append((label, "DB1", {"success": False, "error": f"Table '{table}' does not exist", "query": f"SELECT FROM {table}"}))
    
    # ========== SUMMARY ==========
    print("\n" + "=" * 70)
    print("📊 EXECUTIVE SUMMARY")
    print("=" * 70)
    
    errors = [(name, db, res) for name, db, res in all_results if not res["success"]]
    successes = [(name, db, res) for name, db, res in all_results if res["success"]]
    
    print(f"Total queries executed: {len(all_results)}")
    print(f"✅ Successful: {len(successes)}")
    print(f"❌ Failed: {len(errors)}")
    
    if errors:
        print("\n⚠️  FAILED QUERIES:")
        for name, db, res in errors:
            print(f"  - [{db}] {name}: {res['error'][:150]}")
    
    # Close connections
    db1.close()
    db2.close()
    print("\n✅ Audit complete. Connections closed.")

if __name__ == "__main__":
    main()
