import psycopg2

DB1_CONN = "postgresql://postgres:!2026Sih2026@db.szmepsgyekvmxbmumaep.supabase.co:5432/postgres"
DB2_CONN = "postgresql://postgres:!2026Sih2026@db.nhtrvpsqfztuuiitydlh.supabase.co:5432/postgres"

def connect_db(conn_str):
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    return conn

def run_query(conn, query, label):
    try:
        cur = conn.cursor()
        cur.execute(query)
        results = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        cur.close()
        print(f"\n{'='*60}")
        print(f"📊 {label}")
        print(f"{'='*60}")
        if not results:
            print("No results returned.")
            return
        widths = [len(c) for c in cols]
        for row in results:
            for i, v in enumerate(row):
                widths[i] = max(widths[i], len(str(v) if v is not None else "NULL"))
        hdr = " | ".join(c.ljust(widths[i]) for i, c in enumerate(cols))
        print(hdr)
        print("-" * len(hdr))
        for row in results:
            print(" | ".join(str(v if v is not None else "NULL").ljust(widths[i]) for i, v in enumerate(row)))
        print(f"Total rows: {len(results)}")
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"📊 {label}")
        print(f"{'='*60}")
        print(f"❌ Error: {e}")

db1 = connect_db(DB1_CONN)
db2 = connect_db(DB2_CONN)

# ===== DB1: Corrected queries using mps_id/mp_id/mla_id and mp_name/mla_name =====
print("\n" + "=" * 70)
print("📋 DB1 - CORRECTED MEMBER QUERIES")
print("=" * 70)

# Duplicate check in mps
run_query(db1, """
    SELECT mp_id, COUNT(*) as cnt FROM mps GROUP BY mp_id HAVING COUNT(*) > 1;
""", "Duplicate mp_id in mps")

# Duplicate check in mlas
run_query(db1, """
    SELECT mla_id, COUNT(*) as cnt FROM mlas GROUP BY mla_id HAVING COUNT(*) > 1;
""", "Duplicate mla_id in mlas")

# Same name different IDs in mps
run_query(db1, """
    SELECT mp_name, COUNT(DISTINCT mp_id) as id_count FROM mps 
    GROUP BY mp_name HAVING COUNT(DISTINCT mp_id) > 1 ORDER BY id_count DESC LIMIT 30;
""", "Same name different IDs in mps")

# Same name different IDs in mlas
run_query(db1, """
    SELECT mla_name, COUNT(DISTINCT mla_id) as id_count FROM mlas 
    GROUP BY mla_name HAVING COUNT(DISTINCT mla_id) > 1 ORDER BY id_count DESC LIMIT 30;
""", "Same name different IDs in mlas")

# Rahul Gandhi in mps
run_query(db1, """
    SELECT mp_id, mp_name, house_name, constituency_id FROM mps WHERE mp_name ILIKE '%rahul%gandhi%';
""", "Rahul Gandhi in mps")

# Rahul Gandhi in mlas
run_query(db1, """
    SELECT mla_id, mla_name, house_name, constituency_id FROM mlas WHERE mla_name ILIKE '%rahul%gandhi%';
""", "Rahul Gandhi in mlas")

# ===== DB2: Corrected member_metrics queries =====
print("\n" + "=" * 70)
print("📋 DB2 - CORRECTED MEMBER_METRICS QUERIES")
print("=" * 70)

# performance_classification distribution
run_query(db2, """
    SELECT performance_classification, COUNT(*) as cnt FROM member_metrics 
    GROUP BY performance_classification ORDER BY cnt DESC;
""", "performance_classification distribution")

# Rank nulls with correct column
run_query(db2, """
    SELECT 'mm_rank_nulls' as label, COUNT(*) as cnt FROM member_metrics WHERE rank IS NULL;
""", "mm_rank_nulls")

run_query(db2, """
    SELECT 'mm_national_rank_nulls' as label, COUNT(*) as cnt FROM member_metrics WHERE national_rank IS NULL;
""", "mm_national_rank_nulls")

run_query(db2, """
    SELECT 'mm_national_percentile_nulls' as label, COUNT(*) as cnt FROM member_metrics WHERE national_percentile IS NULL;
""", "mm_national_percentile_nulls")

run_query(db2, """
    SELECT 'mm_cluster_label_nulls' as label, COUNT(*) as cnt FROM member_metrics WHERE cluster_label IS NULL;
""", "mm_cluster_label_nulls")

# ===== DB1: Rahul Gandhi in work_analysis =====
print("\n" + "=" * 70)
print("📋 DB1 - RAHUL GANDHI IN WORK ANALYSIS")
print("=" * 70)

run_query(db1, """
    SELECT member_id, member_type, COUNT(*) as work_count 
    FROM work_analysis WHERE member_id = 144 GROUP BY member_id, member_type;
""", "Work analysis for member_id=144")

run_query(db1, """
    SELECT member_id, member_type, COUNT(*) as work_count 
    FROM work_analysis WHERE member_id = 355 GROUP BY member_id, member_type;
""", "Work analysis for member_id=355")

# ===== DB2: Full Rahul Gandhi profile =====
print("\n" + "=" * 70)
print("📋 DB2 - FULL RAHUL GANDHI PROFILE")
print("=" * 70)

run_query(db2, """
    SELECT member_id, member_type, member_name, performance_score_100, 
           completion_rate_pct, fund_utilization_pct, scale_score,
           national_rank, national_percentile, rank, performance_classification
    FROM member_metrics WHERE member_id = 355;
""", "Rahul Gandhi full profile (member_metrics)")

run_query(db2, """
    SELECT member_id, member_type, performance_score_100, performance_label,
           national_rank, national_percentile, peer_rank, peer_percentile,
           cluster_id, cluster_label, risk_level, risk_score
    FROM member_intelligence WHERE member_id = 355;
""", "Rahul Gandhi full profile (member_intelligence)")

# ===== DB2: MPIs not in member_intelligence =====
print("\n" + "=" * 70)
print("📋 DB2 - MEMBER METRICS vs INTELLIGENCE GAP")
print("=" * 70)

run_query(db2, """
    SELECT 'mm_total' as label, COUNT(*) as cnt FROM member_metrics
    UNION ALL
    SELECT 'mi_total', COUNT(*) FROM member_intelligence
    UNION ALL
    SELECT 'mm_mp', (SELECT COUNT(*) FROM member_metrics WHERE member_type='MP')
    UNION ALL
    SELECT 'mi_mp', (SELECT COUNT(*) FROM member_intelligence WHERE member_type='MP')
    UNION ALL
    SELECT 'mm_mla', (SELECT COUNT(*) FROM member_metrics WHERE member_type='MLA')
    UNION ALL
    SELECT 'mi_mla', (SELECT COUNT(*) FROM member_intelligence WHERE member_type='MLA');
""", "member_metrics vs member_intelligence counts")

# member_metrics without member_intelligence
run_query(db2, """
    SELECT COUNT(*) as mm_without_mi FROM member_metrics mm
    WHERE NOT EXISTS (SELECT 1 FROM member_intelligence mi WHERE mi.member_id = mm.member_id AND mi.member_type = mm.member_type);
""", "member_metrics without member_intelligence")

# member_intelligence without member_metrics
run_query(db2, """
    SELECT COUNT(*) as mi_without_mm FROM member_intelligence mi
    WHERE NOT EXISTS (SELECT 1 FROM member_metrics mm WHERE mm.member_id = mi.member_id AND mm.member_type = mi.member_type);
""", "member_intelligence without member_metrics")

# ===== DB2: Score formula verification (using performance_score_100) =====
print("\n" + "=" * 70)
print("📋 DB2 - SCORE FORMULA VERIFICATION (performance_score_100)")
print("=" * 70)

run_query(db2, """
    SELECT 
        member_id, member_name, member_type,
        completion_rate_pct,
        fund_utilization_pct,
        scale_score,
        performance_score_100 as stored_score_100,
        performance_score_weighted as stored_score_weighted,
        (0.40 * completion_rate_pct + 0.40 * fund_utilization_pct + 0.20 * scale_score) as expected_score,
        ABS(performance_score_100 - (0.40 * completion_rate_pct + 0.40 * fund_utilization_pct + 0.20 * scale_score)) as diff_100,
        ABS(performance_score_weighted - (0.40 * completion_rate_pct + 0.40 * fund_utilization_pct + 0.20 * scale_score)) as diff_weighted
    FROM member_metrics 
    WHERE member_id = 355;
""", "Rahul Gandhi dual-score verification")

run_query(db2, """
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN ABS(performance_score_100 - (0.40 * COALESCE(completion_rate_pct,0) + 0.40 * COALESCE(fund_utilization_pct,0) + 0.20 * COALESCE(scale_score,0))) > 0.01 THEN 1 ELSE 0 END) as mismatches_100,
        SUM(CASE WHEN ABS(performance_score_weighted - (0.40 * COALESCE(completion_rate_pct,0) + 0.40 * COALESCE(fund_utilization_pct,0) + 0.20 * COALESCE(scale_score,0))) > 0.01 THEN 1 ELSE 0 END) as mismatches_weighted
    FROM member_metrics;
""", "Overall mismatch check (both scores)")

# ===== DB2: Score distribution by performance_score_100 =====
run_query(db2, """
    SELECT 
        CASE 
            WHEN performance_score_100 BETWEEN 0 AND 10 THEN '0-10'
            WHEN performance_score_100 BETWEEN 10 AND 20 THEN '10-20'
            WHEN performance_score_100 BETWEEN 20 AND 30 THEN '20-30'
            WHEN performance_score_100 BETWEEN 30 AND 40 THEN '30-40'
            WHEN performance_score_100 BETWEEN 40 AND 50 THEN '40-50'
            WHEN performance_score_100 BETWEEN 50 AND 60 THEN '50-60'
            WHEN performance_score_100 BETWEEN 60 AND 70 THEN '60-70'
            WHEN performance_score_100 BETWEEN 70 AND 80 THEN '70-80'
            WHEN performance_score_100 BETWEEN 80 AND 90 THEN '80-90'
            WHEN performance_score_100 BETWEEN 90 AND 100 THEN '90-100'
            ELSE 'NULL/other'
        END as score_bucket,
        COUNT(*) as cnt
    FROM member_metrics
    GROUP BY score_bucket ORDER BY score_bucket;
""", "Score distribution (performance_score_100)")

db1.close()
db2.close()
print("\n✅ Final fix-up complete.")
