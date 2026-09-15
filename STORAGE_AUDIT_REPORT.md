# GovSense AI — DB1 / DB2 Storage Architecture Audit Report

**Scope:** READ-ONLY audit of DB1 and DB2 storage, classification, and cleanup/migration recommendations.  
**Date:** 2026-09-15  
**Auditor:** OpenCode  
**Repository:** `Yuvraj1954/Smart-India-Hackathon`  
**Rule:** No DELETE / DROP / TRUNCATE / ALTER / UPDATE / INSERT was performed.

---

## Executive Summary

| Database | Current Size | Limit | Headroom | Primary Role |
|---|---:|---:|---:|---|
| **DB1** | 381 MB | 500 MB | ~119 MB | Authoritative raw government data + operational tables + derived analytics |
| **DB2** | 31 MB | 500 MB | ~469 MB | Application analytics, intelligence, ML outputs |

**Headline finding:** DB1 stores roughly **157 MB of derived/ML data** inside the authoritative database (`work_analysis`, `mla_work_analysis`, `ml_work_anomaly`). These are reproducible from raw tables and are the strongest candidates to migrate to DB2 or remove after approval, which would restore ~40 % of DB1's current footprint.

---

## 1. DB1 Size Breakdown

### 1.1 Database-level

| Metric | Value |
|---|---|
| Total DB size | 381 MB (399,756,435 bytes) |
| User-table total | ~366 MB |
| Free headroom | ~119 MB |

### 1.2 Table-level (largest first)

| Table | Rows | Data Size | Index Size | Toast | Total | Category |
|---|---:|---:|---:|---:|---:|---|
| `work_analysis` | 108,431 | 79 MB | 22 MB | 56 kB | **101 MB** | Derived analytics + ML output |
| `works` | 108,661 | 43 MB | 14 MB | 48 kB | **57 MB** | Authoritative raw data |
| `work_expenditures` | 75,964 | 23 MB | 27 MB | 40 kB | **50 MB** | Authoritative raw data |
| `mla_work_analysis` | 25,470 | 27 MB | 5.3 MB | 40 kB | **32 MB** | Derived analytics + ML output |
| `work_recommendations` | 107,824 | 11 MB | 16 MB | 40 kB | **27 MB** | Authoritative raw data |
| `work_sanctions` | 108,661 | 11 MB | 16 MB | 40 kB | **26 MB** | Authoritative raw data |
| `ml_work_anomaly` | 132,070 | 15 MB | 9.1 MB | 40 kB | **24 MB** | ML output |
| `mla_works` | 25,587 | 12 MB | 2.7 MB | 40 kB | **14 MB** | Authoritative raw data |
| `mla_work_expenditures` | 24,830 | 7.3 MB | 3.8 MB | 40 kB | **11 MB** | Authoritative raw data |
| `work_completions` | 32,078 | 2.9 MB | 5.1 MB | 40 kB | **8.1 MB** | Authoritative raw data |
| `mla_work_sanctions` | 25,587 | 2.8 MB | 2.3 MB | 40 kB | **5.1 MB** | Authoritative raw data |
| `mla_work_recommendations` | 25,335 | 2.8 MB | 2.3 MB | 40 kB | **5.1 MB** | Authoritative raw data |
| `mla_work_completions` | 10,028 | 920 kB | 912 kB | 40 kB | **1.9 MB** | Authoritative raw data |
| `phase_a_evidence` | 774 | 1.3 MB | 120 kB | 8 kB | **1.4 MB** | Derived analytics (stale) |
| `ingestion_jobs` | 1,379 | 280 kB | 504 kB | 40 kB | **824 kB** | Operational |
| `phase_a_member_metrics` | 774 | 704 kB | 88 kB | 8 kB | **800 kB** | Derived analytics (stale) |
| `mp_allocations` | 543 | 104 kB | 80 kB | 40 kB | **224 kB** | Authoritative raw data |
| `constituencies` | 582 | 40 kB | 112 kB | 8 kB | **160 kB** | Authoritative raw data |
| `mla_allocations` | 231 | 48 kB | 64 kB | 40 kB | **152 kB** | Authoritative raw data |
| `mps` | 543 | 56 kB | 88 kB | 8 kB | **152 kB** | Authoritative raw data |
| `calamities` | 12 | 8 kB | 72 kB | 8 kB | **88 kB** | Authoritative raw data |
| `mlas` | 231 | 32 kB | 16 kB | 8 kB | **56 kB** | Authoritative raw data |
| `phase_a_state_metrics` | 36 | 16 kB | 32 kB | 8 kB | **56 kB** | Derived analytics (stale) |
| `states` | 36 | 8 kB | 32 kB | 8 kB | **48 kB** | Authoritative master data |
| `mla_calamities` | 20 | 8 kB | 32 kB | 8 kB | **48 kB** | Authoritative raw data |
| `data_updated` | — | 8 kB | 16 kB | 8 kB | **32 kB** | Operational |
| `phase_a_trends` | 7 | 8 kB | 0 | 8 kB | **16 kB** | Derived analytics (partially used) |
| `phase_a_statistics` | 8 | 8 kB | 0 | 8 kB | **16 kB** | Derived analytics (stale) |

### 1.3 Largest DB1 Indexes

| Index | Table | Size | Note |
|---|---:|---:|---|
| `work_expenditures_source_record_key_unique` | work_expenditures | 8.4 MB | Likely duplicate of `work_expenditures_source_record_key_uidx` |
| `work_expenditures_source_record_key_uidx` | work_expenditures | 8.4 MB | Same column as above |
| `idx_work_analysis_work_id` | work_analysis | 6.7 MB | Required by APIs |
| `work_sanctions_work_id_uidx` | work_sanctions | 4.8 MB | Duplicate of `work_sanctions_work_id_key`? |
| `work_sanctions_pkey` | work_sanctions | 4.8 MB | Primary key |
| `work_sanctions_work_id_key` | work_sanctions | 4.8 MB | Same column as `work_id_uidx` |
| `work_recommendations_work_id_key` | work_recommendations | 4.8 MB | — |
| `works_pkey` | works | 4.8 MB | Primary key |
| `works_work_recommendation_dtl_id_key` | works | 4.8 MB | — |
| `works_work_recommendation_dtl_id_uidx` | works | 4.8 MB | Likely duplicate of `works_work_recommendation_dtl_id_key` |
| `work_recommendations_work_id_uidx` | work_recommendations | 4.8 MB | Likely duplicate of `work_recommendations_work_id_key` |
| `work_recommendations_pkey` | work_recommendations | 4.8 MB | Primary key |

---

## 2. DB2 Size Breakdown

### 2.1 Database-level

| Metric | Value |
|---|---|
| Total DB size | 31 MB (32,222,355 bytes) |
| User-table total | ~20 MB |
| Free headroom | ~469 MB |

### 2.2 Table-level (largest first)

| Table | Rows | Data Size | Index Size | Toast | Total | Category |
|---|---:|---:|---:|---:|---:|---|
| `entity_evidence` | 812 | 2.6 MB | 5.0 MB | 40 kB | **7.6 MB** | ML/AI output |
| `evidence_work_refs` | 10,155 | 1.5 MB | 2.8 MB | 40 kB | **4.4 MB** | ML/AI output |
| `ai_analysis` | 814 | 1.1 MB | 536 kB | 40 kB | **1.7 MB** | ML/AI output |
| `govsense_backup_entity_evidence_20260914` | 812 | 1.2 MB | 0 | 32 kB | **1.2 MB** | Backup / archival |
| `govsense_backup_evidence_work_refs_20260914` | 10,155 | 1.1 MB | 0 | 40 kB | **1.1 MB** | Backup / archival |
| `member_metrics` | 773 | 840 kB | 152 kB | 40 kB | **1.0 MB** | Derived analytics |
| `member_intelligence` | 773 | 912 kB | 56 kB | 40 kB | **1.0 MB** | ML/AI output |
| `govsense_backup_ai_analysis_20260914` | 1,049 | 888 kB | 0 | 40 kB | **928 kB** | Backup / archival |
| `govsense_backup_member_metrics_20260914` | 1,012 | 384 kB | 0 | 40 kB | **424 kB** | Backup / archival |
| `govsense_backup_member_intelligence_ranks` | 773 | 128 kB | 0 | 8 kB | **136 kB** | Backup / temporary |
| `national_statistics` | 129 | 32 kB | 32 kB | 40 kB | **104 kB** | Derived analytics |
| `state_metrics` | 36 | 32 kB | 32 kB | 40 kB | **104 kB** | Derived analytics |
| `state_intelligence` | 36 | 40 kB | 16 kB | 40 kB | **96 kB** | ML/AI output |
| `trends` | 7 | 8 kB | 32 kB | 40 kB | **80 kB** | Derived analytics |
| `govsense_backup_member_metrics_alloc_baseline` | 773 | 64 kB | 0 | 8 kB | **72 kB** | Backup / temporary |
| `overall_metrics` | 3 | 8 kB | 32 kB | 8 kB | **48 kB** | Derived analytics |
| `model_registry` | 2 | 8 kB | 32 kB | 8 kB | **48 kB** | ML/AI output |
| `evidence_pipeline_metadata` | 2 | 8 kB | 16 kB | 8 kB | **32 kB** | Operational |
| `govsense_backup_state_intelligence_ranks` | 36 | 8 kB | 0 | 8 kB | **16 kB** | Backup / temporary |

---

## 3. Classification of Every Table

### 3.1 DB1 Table Classification

| Table | Class | Reason |
|---|---|---|
| `works` | **A** | Authoritative raw works master from government source. |
| `work_recommendations` | **A** | Raw recommendation events. |
| `work_sanctions` | **A** | Raw sanction events. |
| `work_expenditures` | **A** | Raw expenditure events. |
| `work_completions` | **A** | Raw completion events. |
| `mla_works` | **A** | Raw MLA works master. |
| `mla_work_recommendations` | **A** | Raw MLA recommendation events. |
| `mla_work_sanctions` | **A** | Raw MLA sanction events. |
| `mla_work_expenditures` | **A** | Raw MLA expenditure events. |
| `mla_work_completions` | **A** | Raw MLA completion events. |
| `mps` | **A** | MP identity master from source. |
| `mlas` | **A** | MLA/Rajya Sabha identity master from source. |
| `states` | **A** | State/UT master. |
| `constituencies` | **A** | Constituency master. |
| `mp_allocations` | **A** | Raw MP allocation records. |
| `mla_allocations` | **A** | Raw MLA allocation records. |
| `calamities` | **A** | Raw calamity records. |
| `mla_calamities` | **A** | Raw MLA calamity records. |
| `work_analysis` | **C + D** | Large derived table joining raw events + computed percentiles + ML anomaly scores. Reproducible. |
| `mla_work_analysis` | **C + D** | Same as `work_analysis` for MLA population. Reproducible. |
| `ml_work_anomaly` | **D** | Per-work Isolation Forest scores/flags. ML output, reproducible, contains model-version history. |
| `phase_a_member_metrics` | **C** | Older Phase A member aggregation (2026-09-05). Superseded by `member_metrics` in DB2. |
| `phase_a_state_metrics` | **C** | Older Phase A state aggregation. Superseded by `state_metrics` in DB2. |
| `phase_a_evidence` | **C + D** | Older Phase A evidence JSON. Superseded by `entity_evidence` in DB2. |
| `phase_a_statistics` | **C** | Older Phase A national statistics. Superseded by `national_statistics` in DB2. |
| `phase_a_trends` | **C** | Older Phase A trends. Still referenced by `/api/trends` fallback path. |
| `ingestion_jobs` | **B** | Operational ingestion tracking. |
| `data_updated` | **B** | Operational last-update timestamp for frontend header. |

### 3.2 DB2 Table Classification

| Table | Class | Reason |
|---|---|---|
| `member_metrics` | **C** | Application member aggregations; derived from DB1. |
| `state_metrics` | **C** | Application state aggregations; derived from DB1. |
| `national_statistics` | **C** | National benchmark statistics; derived. |
| `overall_metrics` | **C** | Overall dashboard aggregates; derived. |
| `trends` | **C** | FY/annual trend aggregations; derived. |
| `member_intelligence` | **D** | ML-driven performance scores, ranks, clusters, risk. |
| `state_intelligence` | **D** | ML-driven state performance/risk. |
| `ai_analysis` | **D** | Generated LLM analysis text. |
| `entity_evidence` | **D** | Structured evidence JSON used by AI/frontend. |
| `evidence_work_refs` | **D** | Work-to-evidence linkage. |
| `model_registry` | **D** | ML model metadata and versioning. |
| `evidence_pipeline_metadata` | **B** | Operational pipeline metadata. |
| `govsense_backup_*` | **E / G** | Backup / temporary / archival tables. |

---

## 4. DB1 Cleanup / Migration Candidates

### 4.1 High-impact derived tables

| Table | Size | Rows | What it contains | Why it may be unnecessary | References | Recommendation | Risk |
|---|---:|---:|---|---|---|---|---|
| `work_analysis` | 101 MB | 108,431 | Denormalized MP works + derived percentiles + ML anomaly labels | Fully reproducible from `works` + event tables + `ml_work_anomaly` | Heavily used by `/api/members/detail/*/works`, `/api/works`, `/api/states/detail/*/works`, `/api/works/risk`, state works, constituency APIs | **MIGRATE TO DB2** or keep but compress/archival | High if removed without API rewrite; current API depends on it |
| `mla_work_analysis` | 32 MB | 25,470 | Same as `work_analysis` for MLA/Rajya Sabha | Fully reproducible | Used alongside `work_analysis` in works/state APIs | **MIGRATE TO DB2** | High if removed without API rewrite |
| `ml_work_anomaly` | 24 MB | 132,070 | Per-work Isolation Forest scores, flags, model version | Reproducible by re-running Isolation Forest; not directly queried by current API | 0 code references found | **MIGRATE TO DB2** (ML audit) / archive | Medium — contains model-version audit trail |
| `phase_a_evidence` | 1.4 MB | 774 | Old evidence JSON (2026-09-05) | Superseded by DB2 `entity_evidence` | 0 code references | **ARCHIVE** / **REMOVE AFTER APPROVAL** | Low |
| `phase_a_member_metrics` | 800 kB | 774 | Old member aggregations | Superseded by DB2 `member_metrics` | 0 code references | **ARCHIVE** / **REMOVE AFTER APPROVAL** | Low |
| `phase_a_state_metrics` | 56 kB | 36 | Old state aggregations | Superseded by DB2 `state_metrics` | Referenced only in a comment | **ARCHIVE** / **REMOVE AFTER APPROVAL** | Low |
| `phase_a_statistics` | 16 kB | 8 | Old national statistics | Superseded by DB2 `national_statistics` | 0 code references | **ARCHIVE** / **REMOVE AFTER APPROVAL** | Low |
| `phase_a_trends` | 16 kB | 7 | Old trend rows | Still used by `/api/trends` | `dashboard.py` `/api/trends` | **KEEP** until `/api/trends` is rewired to DB2 `trends` | Low-Medium |

### 4.2 Index cleanup candidates (DB1)

| Index | Table | Size | Issue | Recommendation | Risk |
|---|---:|---:|---|---|---|
| `work_expenditures_source_record_key_unique` | work_expenditures | 8.4 MB | Exact duplicate of `work_expenditures_source_record_key_uidx` | **REMOVE AFTER APPROVAL** | Verify no query planner preference for the `_unique` name |
| `work_expenditures_source_record_key_uidx` | work_expenditures | 8.4 MB | Pair of the above | Keep one | — |
| `work_sanctions_work_id_uidx` | work_sanctions | 4.8 MB | Same column as `work_sanctions_work_id_key` + pkey | **REMOVE AFTER APPROVAL** | Low |
| `work_recommendations_work_id_uidx` | work_recommendations | 4.8 MB | Same column as `work_recommendations_work_id_key` + pkey | **REMOVE AFTER APPROVAL** | Low |
| `works_work_recommendation_dtl_id_uidx` | works | 4.8 MB | Same column as `works_work_recommendation_dtl_id_key` | **REMOVE AFTER APPROVAL** | Low |

Potential index savings from duplicate removal: **~22 MB**.

---

## 5. DB2 Cleanup Candidates

| Table | Size | Rows | Status | Recommendation | Risk |
|---|---:|---:|---|---|---|
| `govsense_backup_ai_analysis_20260914` | 928 kB | 1,049 | Pre-existing backup | **ARCHIVE** / **REMOVE AFTER APPROVAL** | Low if current `ai_analysis` is trusted |
| `govsense_backup_entity_evidence_20260914` | 1.2 MB | 812 | Pre-existing backup | **ARCHIVE** / **REMOVE AFTER APPROVAL** | Low if current `entity_evidence` is trusted |
| `govsense_backup_evidence_work_refs_20260914` | 1.1 MB | 10,155 | Pre-existing backup | **ARCHIVE** / **REMOVE AFTER APPROVAL** | Low |
| `govsense_backup_member_metrics_20260914` | 424 kB | 1,012 | Pre-existing backup | **ARCHIVE** / **REMOVE AFTER APPROVAL** | Low |
| `govsense_backup_member_intelligence_ranks` | 136 kB | 773 | Created during recent finalization | **REMOVE AFTER APPROVAL** (temporary) | Very low |
| `govsense_backup_state_intelligence_ranks` | 16 kB | 36 | Created during recent finalization | **REMOVE AFTER APPROVAL** (temporary) | Very low |
| `govsense_backup_member_metrics_alloc_baseline` | 72 kB | 773 | Created during recent finalization | **REMOVE AFTER APPROVAL** (temporary) | Very low |
| `ai_analysis` | 1.7 MB | 814 | Active generated summaries | **KEEP** with retention policy | — |
| `entity_evidence` | 7.6 MB | 812 | Active evidence JSON | **KEEP** with retention policy | — |
| `evidence_work_refs` | 4.4 MB | 10,155 | Active evidence linkages | **KEEP** | — |

Backup-table savings in DB2: **~4 MB**.

---

## 6. DB1 → DB2 Migration Candidates

| Table | Size | Destination | Why | Complexity | Dependencies |
|---|---:|---|---|---|---|
| `work_analysis` | 101 MB | DB2 `work_analysis` or equivalent | Derived/ML-enriched analytics used by API | High | API queries must be retargeted; pipeline must write to DB2 |
| `mla_work_analysis` | 32 MB | DB2 `mla_work_analysis` | Same as above | High | Same as above |
| `ml_work_anomaly` | 24 MB | DB2 `ml_work_anomaly` | ML output, reproducible, audit trail | Medium | ML training/inference pipeline must write to DB2 |
| `phase_a_evidence` | 1.4 MB | DB2 archive or remove | Superseded by `entity_evidence` | Low | None |
| `phase_a_member_metrics` | 800 kB | DB2 archive or remove | Superseded by `member_metrics` | Low | None |
| `phase_a_state_metrics` | 56 kB | DB2 archive or remove | Superseded by `state_metrics` | Low | None |
| `phase_a_statistics` | 16 kB | DB2 archive or remove | Superseded by `national_statistics` | Low | None |

**Expected DB1 savings if approved:** ~160 MB logical (40 % of current DB1).  
**Expected DB2 increase if all moved:** ~160 MB (DB2 would still be <200 MB / 500 MB).  
**Recoverable physical space:** PostgreSQL may not release disk to OS without `VACUUM FULL` / re-index; logical deletion/migration is required first.

---

## 7. Redundant-Column Candidates

Focus on the largest table, `work_analysis`:

| Column | Type | Null % | Distinct % | Observation |
|---|---:|---:|---:|---|
| `first_expenditure_date` | date | 100 % | 0 % | Permanently NULL; no value |
| `delay_probability` | numeric | 100 % | 0 % | XGBoost NOT_READY; permanently NULL |
| `delay_risk_band` | text | 100 % | 0 % | XGBoost NOT_READY; permanently NULL |
| `duration_percentile` | numeric | 67.7 % | 0 % | All identical value; redundant |
| `cost_percentile` | numeric | 0 % | 0 % | All identical value; redundant |
| `benchmark_peer_group` | text | 0 % | 0 % | Single value; redundant |
| `benchmark_quality` | text | 0 % | 0 % | Single value; redundant |
| `work_description` | text | 0 % | 0 % | Empty for every row; could be dropped if permanently empty |

Similar patterns likely exist in `mla_work_analysis`.

**Recommendation:** Mark permanently-NULL / single-value columns for removal **after approval** and after confirming API/frontend do not reference them. Potential additional savings: several MB.

---

## 8. Pipeline Regeneration Analysis

Current pipeline (`automation/daily_pipeline.py`) only runs:
1. Classification (DB2)
2. Allocation reconciliation
3. Rank/label reconciliation
4. `data_updated` timestamp

It does **not** currently regenerate `work_analysis`, `mla_work_analysis`, or `ml_work_anomaly`. Therefore:

| Candidate | Regenerated by current pipeline? | Code that would need changing if removed |
|---|---|---|
| `work_analysis` | No | Pipeline would need a new step or raw-event joins in API |
| `mla_work_analysis` | No | Same as above |
| `ml_work_anomaly` | No | ML inference pipeline would need to write to DB2 or skip |
| `phase_a_*` | No | Nothing; safe to archive |
| DB2 backup tables | No | Nothing; safe to archive |

If `work_analysis` / `mla_work_analysis` are approved for migration to DB2, the API routes in `app/routes/dashboard.py` must be updated to read from DB2, and the pipeline must be extended to populate them.

---

## 9. Application Dependency Audit

| Table | Code refs | API refs | Frontend refs | Pipeline refs |
|---|---:|---:|---:|---:|
| `work_analysis` | Many (`dashboard.py`) | `/api/works`, `/api/members/detail/*/works`, `/api/states/detail/*`, `/api/works/risk` | Indirect via API | None |
| `mla_work_analysis` | Many (`dashboard.py`) | Same as above | Indirect via API | None |
| `works` | Many | `/api/works` fallback | Indirect | None |
| `ml_work_anomaly` | 0 | 0 | 0 | None |
| `phase_a_evidence` | 0 | 0 | 0 | None |
| `phase_a_member_metrics` | 0 | 0 | 0 | None |
| `phase_a_state_metrics` | 1 (comment) | 0 | 0 | None |
| `phase_a_statistics` | 0 | 0 | 0 | None |
| `phase_a_trends` | 1 (`dashboard.py`) | `/api/trends` | `dashboard.html` | None |
| DB2 `member_metrics` | Many | Many | Many | `daily_pipeline.py` |
| DB2 `member_intelligence` | Many | `/api/intelligence/members`, `/api/members/detail/*` | `mpdetail.html` | `fix_ranks.py` |

---

## 10. Raw Data Protection List (MUST stay in DB1)

The following tables are authoritative government source data and must **NOT** be migrated or deleted:

- `works`, `work_recommendations`, `work_sanctions`, `work_expenditures`, `work_completions`
- `mla_works`, `mla_work_recommendations`, `mla_work_sanctions`, `mla_work_expenditures`, `mla_work_completions`
- `mps`, `mlas`, `states`, `constituencies`
- `mp_allocations`, `mla_allocations`
- `calamities`, `mla_calamities`
- `ingestion_jobs`, `data_updated` (operational but tied to DB1 raw ingestion)

---

## 11. ML Data Protection List

Data that should be preserved for reproducibility/auditability:

- `ml_work_anomaly` — model version, feature version, calculated_at, scores/flags
- DB2 `model_registry` — model metadata, thresholds, metrics
- DB2 `member_intelligence` / `state_intelligence` — persisted intelligence outputs
- DB2 `entity_evidence` / `evidence_work_refs` / `ai_analysis` — generated explanations and audit trail

Do not delete these without establishing a retention policy.

---

## 12. Storage Projection

| Scenario | DB1 Size | DB2 Size | DB1 Headroom |
|---|---:|---:|---:|
| **Current** | 381 MB | 31 MB | ~119 MB |
| **After removing DB2 backup tables only** | 381 MB | ~27 MB | ~119 MB |
| **After archiving/removing `phase_a_*` except trends** | ~379 MB | ~27 MB | ~121 MB |
| **After migrating `work_analysis` + `mla_work_analysis` + `ml_work_anomaly` to DB2** | ~224 MB | ~187 MB | ~276 MB |
| **After also removing duplicate indexes** | ~202 MB | ~187 MB | ~298 MB |

**Note:** Physical recovery in PostgreSQL requires `VACUUM` / `VACUUM FULL` / re-index after large deletions. Logical size reduction is the first step.

---

## 13. Recommended Order of Operations

1. **Remove temporary DB2 backup tables** created during finalization (`govsense_backup_member_intelligence_ranks`, `govsense_backup_state_intelligence_ranks`, `govsense_backup_member_metrics_alloc_baseline`). Risk: very low.
2. **Archive or remove pre-existing DB2 backup tables** (`govsense_backup_*_20260914`) after confirming current tables are trusted. Risk: low.
3. **Archive or remove stale `phase_a_*` tables** except `phase_a_trends`. Risk: low.
4. **Investigate duplicate indexes** in DB1 (`work_expenditures`, `work_sanctions`, `work_recommendations`, `works`) and drop one of each pair after approval. Risk: low.
5. **Plan migration of `work_analysis` / `mla_work_analysis` to DB2**: update API routes and extend pipeline. Risk: high; requires development and testing.
6. **Decide fate of `ml_work_anomaly`**: migrate to DB2 for ML audit or archive old versions. Risk: medium.
7. **Establish retention policy** for `ai_analysis` / `entity_evidence` / `evidence_work_refs`. Risk: low.
8. **Run `VACUUM FULL` / re-index** after significant deletions to reclaim physical space. Risk: requires downtime/care.

---

## 14. Risk Assessment

| Action | Risk Level | Mitigation |
|---|---|---|
| Remove DB2 temporary backups | Very Low | Created by finalization scripts; current data verified |
| Remove pre-existing DB2 backups | Low | Verify current tables first; keep external archive if needed |
| Remove `phase_a_*` stale tables | Low | Not referenced by code; keep archive if regulatory need |
| Drop duplicate indexes | Low | Test query plans; recreate if regression |
| Migrate `work_analysis` to DB2 | High | Full API + pipeline rewrite; thorough testing required |
| Migrate `ml_work_anomaly` to DB2 | Medium | Ensure ML pipeline writes to DB2; keep model history |
| `VACUUM FULL` | Medium | Run during low-traffic window; monitor locks |

---

## 15. Conclusion

DB1 is at ~76 % capacity (381 MB / 500 MB). The most impactful, safe actions are:

1. Clean up DB2 backup tables (~4 MB saved, mostly symbolic).
2. Archive/remove stale `phase_a_*` tables (~2.3 MB saved in DB1).
3. Drop duplicate DB1 indexes (~22 MB estimated savings).

The **transformational** savings come from migrating the large derived/ML tables (`work_analysis`, `mla_work_analysis`, `ml_work_anomaly`, ~157 MB) out of DB1 into DB2, but this requires API and pipeline changes and should be treated as a development project, not a simple cleanup.

No data modification has been performed. All recommendations require explicit human approval before execution.
