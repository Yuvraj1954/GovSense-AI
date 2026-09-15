# GovSense AI — DB1 → DB2 Migration Design Audit

**Objective:** Design the migration of all derived/analytical/ML data from DB1 to DB2 while keeping only authoritative raw government data and necessary operational state in DB1.  
**Constraint:** READ-ONLY. No data modification, deletion, or migration executed.  
**Date:** 2026-09-15

---

## Executive Summary

| Database | Current Size | After Proposed Migration |
|---|---:|---:|
| **DB1** | 381 MB | ~202 MB (keep raw + operational) |
| **DB2** | 31 MB | ~210 MB (all derived + analytical + ML) |

**Estimated DB1 space recovered:** ~160 MB (~42 % of current DB1).  
**Tables recommended to migrate:** `work_analysis`, `mla_work_analysis`, `ml_work_anomaly`, `category_metrics`, `fy_metrics`, `phase_a_evidence`, `phase_a_member_metrics`, `phase_a_state_metrics`, `phase_a_statistics`, `phase_a_trends`.

**Tables that MUST stay in DB1:** All raw government tables (`works`, `mla_works`, event tables, identity masters, allocations, calamities) plus operational tables (`data_updated`, `ingestion_jobs`).

---

## 1. Derived DB1 Tables — Detailed Migration Assessment

### 1.1 `work_analysis`

| Attribute | Value |
|---|---|
| **Size** | 101 MB |
| **Rows** | 108,431 |
| **Authoritative vs Derived** | Derived + ML-enriched |
| **Operational dependency** | None for ingestion; required by current API |
| **Pipeline writer** | External/uncommitted intelligence pipeline (not in repo) |
| **Pipeline reader** | `automation/final_reconciliation.py` (counts only) |
| **API readers** | `app/routes/dashboard.py`: `/api/members/detail/{id}/works`, `/api/states/detail/{id}/works`, `/api/works`, `/api/works/risk`, `/api/states/detail/{id}/constituencies`, works-by-status/risk/category filters |
| **Frontend dependency** | `public/project.html`, `public/workdetail.html`, member detail Works tab, state detail Works tab, Risk Centre works list |
| **ML dependency** | Contains `isolation_score`, `isolation_level`, `risk_level`, `risk_flags`, `cost_percentile`, `duration_percentile`, `delay_probability` (NULL), `delay_risk_band` (NULL) |
| **FK dependencies** | Logical FKs to `works.work_id`, `mps.mp_id` / `mlas.mla_id` (not enforced) |
| **Regenerable from DB1 raw?** | Yes — from `works` + `work_recommendations` + `work_sanctions` + `work_expenditures` + `work_completions` + `ml_work_anomaly` + percentile/risk computations |
| **Must remain in DB1?** | No under target architecture, but current API requires it |
| **Target DB2 table** | `public.work_analysis` |
| **Estimated DB1 space recovered** | 101 MB |
| **Migration risk** | **HIGH** — many API endpoints must be retargeted; fallback to raw `works` already exists but loses enriched fields |

**Regeneration path:**
1. Join `works` + `work_recommendations` + `work_sanctions` + `work_expenditures` + `work_completions` on `work_id`.
2. Compute status, amounts, dates, delays, execution days, project age.
3. Compute cost/duration percentiles and benchmarks.
4. Merge `ml_work_anomaly` scores/levels.
5. Compute `risk_level` and `risk_flags` from anomaly + deviation rules.
6. Insert into DB2 `public.work_analysis`.

---

### 1.2 `mla_work_analysis`

| Attribute | Value |
|---|---|
| **Size** | 32 MB |
| **Rows** | 25,470 |
| **Authoritative vs Derived** | Derived + ML-enriched |
| **Operational dependency** | None |
| **Pipeline writer** | External/uncommitted intelligence pipeline |
| **Pipeline reader** | `automation/final_reconciliation.py` (counts only) |
| **API readers** | Same as `work_analysis`; queried in `UNION ALL` patterns for combined MP+MLA views |
| **Frontend dependency** | Same as `work_analysis` |
| **ML dependency** | Same pattern as `work_analysis` |
| **FK dependencies** | Logical FKs to `mla_works.mla_work_id` / `mla_works.work_id`, `mlas.mla_id` |
| **Regenerable from DB1 raw?** | Yes — from `mla_works` + `mla_work_recommendations` + `mla_work_sanctions` + `mla_work_expenditures` + `mla_work_completions` |
| **Must remain in DB1?** | No |
| **Target DB2 table** | `public.mla_work_analysis` |
| **Estimated DB1 space recovered** | 32 MB |
| **Migration risk** | **HIGH** — same API retargeting as `work_analysis` |

**Regeneration path:** Mirror of `work_analysis` using `mla_*` raw tables.

---

### 1.3 `ml_work_anomaly`

| Attribute | Value |
|---|---|
| **Size** | 24 MB |
| **Rows** | 132,070 |
| **Authoritative vs Derived** | ML output |
| **Operational dependency** | None |
| **Pipeline writer** | External/uncommitted Isolation Forest training script |
| **Pipeline reader** | None in current repo (`work_analysis` already contains merged `isolation_score`) |
| **API readers** | None |
| **Frontend dependency** | None |
| **ML dependency** | Source of `work_analysis.isolation_score` / `isolation_level`; contains `model_name`, `model_version`, `feature_version`, `calculated_at` for audit |
| **FK dependencies** | Logical FK to `works.work_id` |
| **Regenerable from DB1 raw?** | Yes — by re-running Isolation Forest on `work_analysis` features |
| **Must remain in DB1?** | No |
| **Target DB2 table** | `public.ml_work_anomaly` |
| **Estimated DB1 space recovered** | 24 MB |
| **Migration risk** | **MEDIUM** — must ensure ML pipeline writes to DB2 and keeps model-version audit trail; no API changes needed today |

**Regeneration path:**
1. Train/load Isolation Forest model.
2. Score each work using features from raw event tables.
3. Store `work_id`, `member_type`, `ml_anomaly_score`, `ml_anomaly_flag`, model metadata, timestamp.

---

### 1.4 `category_metrics`

| Attribute | Value |
|---|---|
| **Size** | ~0 bytes (very small, 2,120 rows) |
| **Rows** | 2,120 |
| **Authoritative vs Derived** | Derived |
| **Operational dependency** | None |
| **Pipeline writer** | External/uncommitted analytics pipeline |
| **Pipeline reader** | None |
| **API readers** | `app/routes/dashboard.py` `/api/categories` |
| **Frontend dependency** | Likely dashboard category section |
| **ML dependency** | Includes `cost_anomaly_rate_pct`, `duration_anomaly_rate_pct`, `risk_rate_pct` |
| **FK dependencies** | None |
| **Regenerable from DB1 raw?** | Yes — from `work_analysis` / `mla_work_analysis` `normalized_activity`/`work_category` aggregations |
| **Must remain in DB1?** | No |
| **Target DB2 table** | `public.category_metrics` |
| **Estimated DB1 space recovered** | Negligible |
| **Migration risk** | **LOW** — single API endpoint retarget; table is tiny |

**Regeneration path:** Aggregate works by `normalized_activity` / `work_category` and `scope`/`state_id`, computing counts, amounts, rates, and confidence.

---

### 1.5 `fy_metrics`

| Attribute | Value |
|---|---|
| **Size** | ~0 bytes (7 rows) |
| **Rows** | 7 |
| **Authoritative vs Derived** | Derived |
| **Operational dependency** | None |
| **Pipeline writer** | External/uncommitted analytics pipeline |
| **Pipeline reader** | None |
| **API readers** | `app/routes/dashboard.py` `/api/fy` |
| **Frontend dependency** | Likely dashboard FY trends chart |
| **ML dependency** | None |
| **FK dependencies** | None |
| **Regenerable from DB1 raw?** | Yes — from raw event dates in `works`/`mla_works` |
| **Must remain in DB1?** | No |
| **Target DB2 table** | `public.fy_metrics` |
| **Estimated DB1 space recovered** | Negligible |
| **Migration risk** | **LOW** — single API endpoint retarget; table is tiny |

**Regeneration path:** Bucket raw recommendation/sanction/completion/expenditure events by April–March fiscal year and `member_type`.

---

### 1.6 `phase_a_evidence`

| Attribute | Value |
|---|---|
| **Size** | 1.4 MB |
| **Rows** | 774 |
| **Authoritative vs Derived** | Derived evidence JSON |
| **Operational dependency** | None |
| **Pipeline writer** | External Phase A pipeline (2026-09-05) |
| **Pipeline reader** | None |
| **API readers** | None |
| **Frontend dependency** | None |
| **ML dependency** | Superseded by DB2 `entity_evidence` |
| **FK dependencies** | Logical FK to `member_metrics` |
| **Regenerable from DB1 raw?** | Partially — from DB2 `member_metrics` + `work_analysis`, but the exact Phase A evidence structure is not reproduced by current code |
| **Must remain in DB1?** | No |
| **Target DB2 table** | Archive or `public.phase_a_evidence` if historical audit required |
| **Estimated DB1 space recovered** | 1.4 MB |
| **Migration risk** | **LOW** — no current consumers |

---

### 1.7 `phase_a_member_metrics`

| Attribute | Value |
|---|---|
| **Size** | 800 kB |
| **Rows** | 774 |
| **Authoritative vs Derived** | Derived member aggregations |
| **Operational dependency** | None |
| **Pipeline writer** | External Phase A pipeline |
| **Pipeline reader** | None |
| **API readers** | None |
| **Frontend dependency** | None |
| **ML dependency** | Superseded by DB2 `member_metrics` |
| **FK dependencies** | Logical FK to `mps`/`mlas` |
| **Regenerable from DB1 raw?** | Yes — from raw event tables; current DB2 `member_metrics` already supersedes it |
| **Must remain in DB1?** | No |
| **Target DB2 table** | Archive or `public.phase_a_member_metrics` |
| **Estimated DB1 space recovered** | 800 kB |
| **Migration risk** | **LOW** — no current consumers |

---

### 1.8 `phase_a_state_metrics`

| Attribute | Value |
|---|---|
| **Size** | 56 kB |
| **Rows** | 36 |
| **Authoritative vs Derived** | Derived state aggregations |
| **Operational dependency** | None |
| **Pipeline writer** | External Phase A pipeline |
| **Pipeline reader** | None |
| **API readers** | Referenced only in a code comment about `state_id` numbering |
| **Frontend dependency** | None |
| **ML dependency** | Superseded by DB2 `state_metrics` |
| **FK dependencies** | Logical FK to `states` |
| **Regenerable from DB1 raw?** | Yes |
| **Must remain in DB1?** | No |
| **Target DB2 table** | Archive or `public.phase_a_state_metrics` |
| **Estimated DB1 space recovered** | 56 kB |
| **Migration risk** | **LOW** — only a comment reference |

---

### 1.9 `phase_a_statistics`

| Attribute | Value |
|---|---|
| **Size** | 16 kB |
| **Rows** | 8 |
| **Authoritative vs Derived** | Derived national statistics |
| **Operational dependency** | None |
| **Pipeline writer** | External Phase A pipeline |
| **Pipeline reader** | None |
| **API readers** | None |
| **Frontend dependency** | None |
| **ML dependency** | Superseded by DB2 `national_statistics` |
| **FK dependencies** | None |
| **Regenerable from DB1 raw?** | Yes |
| **Must remain in DB1?** | No |
| **Target DB2 table** | Archive or `public.phase_a_statistics` |
| **Estimated DB1 space recovered** | 16 kB |
| **Migration risk** | **LOW** |

---

### 1.10 `phase_a_trends`

| Attribute | Value |
|---|---|
| **Size** | 16 kB |
| **Rows** | 7 |
| **Authoritative vs Derived** | Derived trend rows |
| **Operational dependency** | None |
| **Pipeline writer** | External Phase A pipeline |
| **Pipeline reader** | `automation/final_reconciliation.py` (counts only) |
| **API readers** | `app/routes/dashboard.py` `/api/trends` |
| **Frontend dependency** | Dashboard trends chart (`public/dashboard.html`) |
| **ML dependency** | None |
| **FK dependencies** | None |
| **Regenerable from DB1 raw?** | Yes — from raw event dates |
| **Must remain in DB1?** | No, but API must be rewired to DB2 `trends` or `fy_metrics` |
| **Target DB2 table** | `public.trends` (extend schema if needed) or `public.phase_a_trends` |
| **Estimated DB1 space recovered** | 16 kB |
| **Migration risk** | **MEDIUM** — `/api/trends` is active; DB2 `trends` already exists but has different schema (7 rows, no `flagged_works`/`high_risk_works`) |

---

## 2. Operational DB1 Tables — KEEP Assessment

### 2.1 `data_updated`

| Attribute | Value |
|---|---|
| **Size** | 32 kB |
| **Class** | Operational |
| **Must stay in DB1?** | **YES** — tied to DB1 ingestion completion; frontend header reads it |
| **API readers** | `app/routes/data_updated.py` `/api/data-updated` |
| **Pipeline writer** | `automation/daily_pipeline.py`, `scripts/pipeline_run.py` |

**Note:** The frontend header depends on `/api/data-updated`, which reads from DB1. Moving this to DB2 would require frontend change and is not recommended.

---

### 2.2 `ingestion_jobs`

| Attribute | Value |
|---|---|
| **Size** | 824 kB |
| **Class** | Operational |
| **Must stay in DB1?** | **YES** — tracks raw ingestion runs into DB1 |
| **API readers** | None in current code |
| **Pipeline writer** | External ingestion pipeline (not in repo) |

---

## 3. Authoritative Raw DB1 Tables — KEEP

The following tables are authoritative government source data and MUST remain in DB1:

| Table | Size | Purpose |
|---|---:|---|
| `works` | 57 MB | Raw MP works master |
| `work_recommendations` | 27 MB | Raw recommendation events |
| `work_sanctions` | 26 MB | Raw sanction events |
| `work_expenditures` | 50 MB | Raw expenditure events |
| `work_completions` | 8.1 MB | Raw completion events |
| `mla_works` | 14 MB | Raw MLA works master |
| `mla_work_recommendations` | 5.1 MB | Raw MLA recommendation events |
| `mla_work_sanctions` | 5.1 MB | Raw MLA sanction events |
| `mla_work_expenditures` | 11 MB | Raw MLA expenditure events |
| `mla_work_completions` | 1.9 MB | Raw MLA completion events |
| `mps` | 152 kB | MP identity master |
| `mlas` | 56 kB | MLA/Rajya Sabha identity master |
| `states` | 48 kB | State/UT master |
| `constituencies` | 160 kB | Constituency master |
| `mp_allocations` | 224 kB | MP allocation records |
| `mla_allocations` | 152 kB | MLA allocation records |
| `calamities` | 88 kB | Calamity records |
| `mla_calamities` | 48 kB | MLA calamity records |

**Total authoritative raw data in DB1 after migration:** ~202 MB.

---

## 4. Derived Columns Inside Authoritative DB1 Tables

Some authoritative tables contain derived columns that could be removed later, but they are currently required by the API/pipeline:

### 4.1 `works` / `mla_works`

| Column | Observation | Current Need | Recommendation |
|---|---|---|---|
| `work_recommendation_dtl_id` | Used for unique indexing; may be source key | API/pipeline may use it | Keep for now |

### 4.2 `work_expenditures`

| Column | Observation | Current Need | Recommendation |
|---|---|---|---|
| `source_record_key` | Source key; duplicate unique indexes exist | Ingestion deduplication | Keep; remove duplicate index only |

### 4.3 `work_analysis` (when migrated)

Derived columns like `expenditure_percentage`, `completion_percentage`, `cost_percentile`, `duration_percentile`, `risk_level`, `isolation_score`, `isolation_level` will move with the table to DB2.

---

## 5. DB2 Existing Intelligence List

Tables already correctly in DB2:

| Table | Class | Status |
|---|---|---|
| `member_metrics` | Derived analytics | Keep in DB2 |
| `state_metrics` | Derived analytics | Keep in DB2 |
| `member_intelligence` | ML/AI output | Keep in DB2 |
| `state_intelligence` | ML/AI output | Keep in DB2 |
| `national_statistics` | Derived analytics | Keep in DB2 |
| `overall_metrics` | Derived analytics | Keep in DB2 |
| `trends` | Derived analytics | Keep in DB2; may need schema extension to replace `phase_a_trends` |
| `ai_analysis` | ML/AI output | Keep in DB2 |
| `entity_evidence` | ML/AI output | Keep in DB2 |
| `evidence_work_refs` | ML/AI output | Keep in DB2 |
| `model_registry` | ML/AI output | Keep in DB2 |
| `evidence_pipeline_metadata` | Operational | Keep in DB2 |

---

## 6. Pipeline Changes Required

### 6.1 New pipeline steps needed

1. **Work analysis builder** — create `work_analysis` in DB2 from DB1 raw tables.
2. **MLA work analysis builder** — create `mla_work_analysis` in DB2 from DB1 `mla_*` raw tables.
3. **ML anomaly scorer** — run Isolation Forest and write to DB2 `ml_work_anomaly`.
4. **Category metrics builder** — aggregate and write to DB2 `category_metrics`.
5. **FY metrics builder** — aggregate and write to DB2 `fy_metrics`.
6. **Trends builder** — extend or replace DB2 `trends` to match `/api/trends` needs.

### 6.2 Existing pipeline updates

- `automation/daily_pipeline.py`: Add new steps above after classification.
- `scripts/fix_allocations.py`: Already operates on DB2; no change needed.
- `scripts/fix_ranks.py`: Already operates on DB2; no change needed.

### 6.3 Removed pipeline steps

- None initially. After migration is verified, drop any DB1 write steps for derived tables.

---

## 7. API Changes Required

### 7.1 `app/routes/dashboard.py`

All references to DB1 `work_analysis` and `mla_work_analysis` must be retargeted to DB2 equivalents:

| Current | Target |
|---|---|
| `public.work_analysis` | `public.work_analysis` in DB2 |
| `public.mla_work_analysis` | `public.mla_work_analysis` in DB2 |
| `public.category_metrics` | `public.category_metrics` in DB2 |
| `public.fy_metrics` | `public.fy_metrics` in DB2 |
| `public.phase_a_trends` | `public.trends` in DB2 (after schema alignment) |

Endpoints affected:
- `/api/members/detail/{id}/works`
- `/api/states/detail/{id}/works`
- `/api/states/detail/{id}/constituencies`
- `/api/works`
- `/api/works/risk`
- `/api/categories`
- `/api/fy`
- `/api/trends`

### 7.2 `app/routes/classification.py`

No DB1 references; no change.

### 7.3 `app/routes/data_updated.py`

Keep reading DB1 `public.data_updated`.

---

## 8. Frontend Changes Required

The frontend already consumes APIs, so **no direct frontend changes are required** if API response schemas remain identical.

However, if the migration changes any field names or schema (e.g., `phase_a_trends` → `trends`), the frontend may need updates:

| API | Frontend File | Risk |
|---|---|---|
| `/api/trends` | `public/dashboard.html` / `public/js/dashboard-data.js` | Medium — DB2 `trends` schema differs |
| `/api/works` | `public/project.html` / `public/workdetail.html` | Low if schema preserved |
| `/api/categories` | Dashboard category section | Low |
| `/api/fy` | Dashboard FY chart | Low |

---

## 9. Migration Order

### Phase 1: Safe, low-risk moves (no API disruption)
1. Create `public.phase_a_evidence`, `public.phase_a_member_metrics`, `public.phase_a_state_metrics`, `public.phase_a_statistics` in DB2 as archive tables.
2. Copy current DB1 `phase_a_*` data to DB2.
3. Verify no consumers break.
4. Later, drop DB1 `phase_a_*` tables.

### Phase 2: Small derived tables
5. Create `public.category_metrics` and `public.fy_metrics` in DB2.
6. Build pipeline step to populate them from DB1 raw data.
7. Retarget `/api/categories` and `/api/fy` to DB2.
8. Drop DB1 `category_metrics` and `fy_metrics`.

### Phase 3: Trends
9. Align DB2 `trends` schema with `/api/trends` requirements (add flagged/high-risk columns if needed) OR keep `phase_a_trends` as a separate DB2 table.
10. Retarget `/api/trends` to DB2.
11. Drop DB1 `phase_a_trends`.

### Phase 4: Large derived work tables (highest impact)
12. Create `public.ml_work_anomaly` in DB2.
13. Update ML pipeline to write anomaly scores to DB2.
14. Create `public.work_analysis` and `public.mla_work_analysis` in DB2.
15. Build/extend pipeline to populate them from DB1 raw tables + DB2 `ml_work_anomaly`.
16. Retarget all dashboard.py work queries to DB2.
17. Run full API regression tests.
18. Drop DB1 `work_analysis`, `mla_work_analysis`, `ml_work_anomaly`.

### Phase 5: Cleanup
19. Remove duplicate DB1 indexes after monitoring confirms no regressions.
20. Run `VACUUM FULL` / re-index to reclaim physical space.

---

## 10. Rollback Strategy

For each phase:

1. **Keep DB1 tables until DB2 tables are verified** and API regression tests pass.
2. **Use schema-level rename instead of drop initially** (e.g., `work_analysis` → `z_deprecated_work_analysis`) so data can be restored instantly.
3. **Maintain dual-write option** during transition: write derived data to both DB1 and DB2, then switch reads to DB2.
4. **DB2 backups:** Before large migrations, create `govsense_backup_work_analysis_YYYYMMDD` etc. in DB2.
5. **Revert path:** If API regressions occur, switch endpoints back to DB1 tables; DB2 writes can continue in parallel until stability is proven.

---

## 11. Projected DB1 / DB2 Sizes

| Scenario | DB1 Size | DB2 Size | DB1 Headroom |
|---|---:|---:|---:|
| **Current** | 381 MB | 31 MB | ~119 MB |
| **After Phase 1 (phase_a_* archive)** | ~379 MB | ~33 MB | ~121 MB |
| **After Phase 2 (category/fy metrics)** | ~379 MB | ~33 MB | ~121 MB |
| **After Phase 3 (trends)** | ~379 MB | ~33 MB | ~121 MB |
| **After Phase 4 (work_analysis + mla_work_analysis + ml_work_anomaly)** | ~224 MB | ~188 MB | ~276 MB |
| **After Phase 5 (duplicate index cleanup + VACUUM)** | ~202 MB | ~188 MB | ~298 MB |

**Note:** Physical space recovery depends on PostgreSQL `VACUUM` behavior. Logical size reduction is guaranteed; physical disk release requires `VACUUM FULL` or re-indexing.

---

## 12. Final Lists

### 12.1 DB1 KEEP List

- `works`, `work_recommendations`, `work_sanctions`, `work_expenditures`, `work_completions`
- `mla_works`, `mla_work_recommendations`, `mla_work_sanctions`, `mla_work_expenditures`, `mla_work_completions`
- `mps`, `mlas`, `states`, `constituencies`
- `mp_allocations`, `mla_allocations`
- `calamities`, `mla_calamities`
- `data_updated`, `ingestion_jobs`

### 12.2 DB1 MIGRATE TO DB2 List

| DB1 Table | Target DB2 Table | Space Recovered | Risk |
|---|---|---:|---|
| `work_analysis` | `public.work_analysis` | 101 MB | HIGH |
| `mla_work_analysis` | `public.mla_work_analysis` | 32 MB | HIGH |
| `ml_work_anomaly` | `public.ml_work_anomaly` | 24 MB | MEDIUM |
| `category_metrics` | `public.category_metrics` | ~0 MB | LOW |
| `fy_metrics` | `public.fy_metrics` | ~0 MB | LOW |
| `phase_a_trends` | `public.trends` (aligned) or `public.phase_a_trends` | 16 kB | MEDIUM |
| `phase_a_evidence` | `public.phase_a_evidence` (archive) | 1.4 MB | LOW |
| `phase_a_member_metrics` | `public.phase_a_member_metrics` (archive) | 800 kB | LOW |
| `phase_a_state_metrics` | `public.phase_a_state_metrics` (archive) | 56 kB | LOW |
| `phase_a_statistics` | `public.phase_a_statistics` (archive) | 16 kB | LOW |

### 12.3 DB1 REMOVE AFTER MIGRATION List

Same as the migrate list. These tables should be renamed to `z_deprecated_*` immediately after migration verification, then dropped after a stabilization period.

### 12.4 DB1 UNKNOWN List

None. All DB1 tables have been classified.

---

## 13. No Data Modified

This report is purely a design audit. No tables were dropped, truncated, deleted, altered, updated, or migrated.
