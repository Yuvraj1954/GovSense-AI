# GovSense AI — Missing Intelligence Generation Code Investigation Report

**Task:** Read-only investigation to locate the intelligence-generation implementation.  
**Date:** 2026-09-15  
**Scope:** Current repository, full git history, branches, tags, untracked files, databases, dependencies.  
**Constraint:** No database writes, no code changes, no deletions.

---

## Executive Finding

**The intelligence-generation implementation is definitively absent from this repository and its entire git history.**

Only the **consumers** of the persisted DB2 intelligence outputs exist in the codebase (API routes in `app/routes/dashboard.py`, frontend JS, and the rank/label reconciliation script added during finalization). The actual code that produced `performance_score_100`, clusters, Isolation Forest scores, XGBoost delay predictions, risk aggregation, and `model_registry` entries is not under version control.

---

## 1. Current Repository Search

### 1.1 Python files present

| Path | Purpose | Intelligence Generation? |
|---|---|---|
| `app/classification.py` | 200-point classification (`completion_rate_pct + fund_utilization_pct`) | ❌ No |
| `app/routes/dashboard.py` | Reads `member_intelligence`, `state_intelligence`, `model_registry`; serves `/api/intelligence/*` | ❌ Consumer only |
| `app/routes/classification.py` | Serves 200-point classification endpoints | ❌ No |
| `scripts/backfill_classification.py` | Backfills 200-point classification | ❌ No |
| `scripts/pipeline_run.py` | Runs classification + `data_updated` | ❌ No |
| `scripts/fix_allocations.py` | Matches DB1 allocations to DB2 `member_metrics` | ❌ No |
| `scripts/fix_ranks.py` | Recomputes ranks/labels from existing `performance_score_100` | ❌ No score generation |
| `automation/*.py` | Validation, integrity, reconciliation, pipeline orchestration | ❌ No generation |

### 1.2 Search results for intelligence terms in current repo

| Term | Found? | Location |
|---|---|---|
| `performance_score_100` | ✅ | `app/routes/dashboard.py`, `scripts/fix_ranks.py`, `STORAGE_AUDIT_REPORT.md` |
| `member_intelligence` | ✅ | Same as above |
| `state_intelligence` | ✅ | Same as above |
| `model_registry` | ✅ | Same as above |
| `cluster_id` | ✅ | Same as above |
| `risk_score` / `risk_level` | ✅ | Same as above + `work_analysis` reads |
| `isolation_forest` | ✅ | Only in comments/report |
| `xgboost` / `xgb` | ✅ | Only in comments/report |
| `wilson` | ❌ | Not found |
| `bayesian` | ❌ | Not found |
| `kmeans` / `KMeans` | ❌ | Not found |
| `performance_score_weighted` | ❌ | Not found |
| `scale_score` | ❌ | Not found |

**Conclusion:** Current repo only *reads* intelligence fields; it does not generate them.

---

## 2. Git History Investigation

### 2.1 Commit summary

- Total commits in history: **16**
- Branches: only `main` (local and remote)
- Tags: **none**
- Stashes: **none**
- Packed refs: **none**

### 2.2 Commits searched

All 16 commits were searched with `git log -S <term>` for every intelligence keyword. The only commit containing any intelligence-related strings is **`cc03e22`** (the recent finalization commit), and there the strings appear only in:

- `app/routes/dashboard.py` — SQL reading DB2 tables
- `scripts/fix_ranks.py` — rank/label reconciliation from existing scores
- `STORAGE_AUDIT_REPORT.md` — audit report text

### 2.3 Deleted files ever committed

Total deleted files: **27**

List:
- `api/index.py`, `api/requirements.txt`
- `back end/.gitignore`
- `back end/app/__init__.py`, `back end/app/classification.py`, `back end/app/config.py`, `back end/app/database.py`, `back end/app/main.py`
- `back end/app/routes/__init__.py`, `back end/app/routes/classification.py`, `back end/app/routes/dashboard.py`, `back end/app/routes/data_updated.py`
- `back end/requirements.txt`
- Old prototype HTML files (`explorestateproject.html`, `financialmps.html`, etc.)

**None of the deleted files are intelligence-generation files.** The `back end/app/*.py` files were simply moved to the repository root in later commits; their content is the same classification/dashboard code present today.

### 2.4 Git pickaxe search (`-S`) results

| Term | Commits containing it |
|---|---|
| `performance_score_100` | `cc03e22` only |
| `member_intelligence` | `cc03e22` only |
| `state_intelligence` | `cc03e22` only |
| `model_registry` | `cc03e22` only |
| `isolation_forest` | `cc03e22` only |
| `xgb` | `cc03e22` only |
| `cluster_id` | `cc03e22` only |
| `wilson` | **none** |
| `bayesian` | **none** |
| `kmeans` / `KMeans` | **none** |
| `performance_score_weighted` | **none** |
| `scale_score` | **none** |

### 2.5 Reflog and loose objects

- Reflog contains only the 16 known commits.
- 225 loose objects — normal for this history size; no unexpected objects found.

---

## 3. File System Investigation

### 3.1 Untracked / hidden files

- Untracked files at time of investigation:
  - `STORAGE_AUDIT_REPORT.md` (audit report from previous task)
  - `scripts/storage_audit_p1.py` (audit helper from previous task)
- No hidden directories except `.git` and `back end/.venv`.
- No Jupyter notebooks (`.ipynb`).
- No model artifacts (`.pkl`, `.joblib`, `.onnx`, `.pt`, `.h5`).
- No custom Python packages named `govsense`, `govesense`, `intelligence`, `mplads`, `sih`, or similar.

### 3.2 Virtual environment

Location: `back end/.venv/`

Installed ML-related packages:
- `xgboost==3.4.1`
- `scikit-learn==1.9.1`
- `scipy==1.18.1`
- `numpy==2.5.3`

**Critical observation:** These packages exist in the local virtual environment but are **NOT declared** in `requirements.txt` or `pyproject.toml`:

```text
# requirements.txt
fastapi>=0.115.0
uvicorn>=0.30.0
asyncpg>=0.29.0
pydantic-settings>=2.0.0
```

This strongly indicates that the intelligence code was executed from this environment (or a similar one) but the scripts/notebooks that used these libraries were never committed.

---

## 4. Database Investigation

### 4.1 Stored procedures / functions / triggers

| Database | Stored Procedures | Functions | Triggers |
|---|---:|---:|---:|
| DB1 | 0 | 0 | 0 |
| DB2 | 0 | 0 | 0 |

No generation logic is embedded in the databases.

### 4.2 DB2 `model_registry` contents

The registry records confirm models were trained, but the training code is absent:

| model_name | model_version | status | training_date | observations |
|---|---|---|---|---:|
| `isolation_forest` | `if-20260914` | READY | 2026-09-14 19:47:42 UTC | 133,901 |
| `project_delay_xgb` | `xgb-20260914` | NOT_READY | 2026-09-14 19:47:42 UTC | 43,276 |

Features and targets are documented in the registry, but no code implements them.

---

## 5. External / Private Dependency Investigation

### 5.1 Configuration files

- `.env` and `.env.example` only contain Supabase Postgres/REST URLs.
- No references to S3 buckets, external script repositories, GitHub submodules, cron endpoints, or remote compute services.

### 5.2 Remote repository

- GitHub remote: `https://github.com/Yuvraj1954/Smart-India-Hackathon`
- Remote branches: only `refs/heads/main` at `cc03e22`
- Remote tags: none
- No submodules.

---

## 6. Recovery Map: What Exists vs. What Is Missing

### 6.1 What exists in the repo

| Component | Status | Evidence |
|---|---|---|
| 200-point classification | ✅ Exists | `app/classification.py`, `scripts/backfill_classification.py` |
| DB2 intelligence table readers | ✅ Exists | `app/routes/dashboard.py` (`/api/intelligence/*`) |
| Rank/label reconciler | ✅ Exists | `scripts/fix_ranks.py` (works from existing scores) |
| Allocation matcher | ✅ Exists | `scripts/fix_allocations.py` |
| Validation scripts | ✅ Exists | `automation/validate_intelligence.py`, `automation/ml_readiness.py` |
| API consumers (frontend) | ✅ Exist | `public/js/mpdetail-data.js`, `public/js/statedetail-data.js` |

### 6.2 What is missing

| Component | Missing? | Notes |
|---|---|---|
| `performance_score_100` generation | ❌ Missing | No Wilson/Bayesian/shrinkage code found |
| Member scoring | ❌ Missing | No 0–100 member score calculation |
| State scoring | ❌ Missing | No 0–100 state score calculation |
| Member K-Means profiling | ❌ Missing | No `KMeans` import or cluster training code |
| State K-Means profiling | ❌ Missing | No state clustering code |
| Cluster selection/stability metrics | ❌ Missing | No silhouette/ARI computation |
| Isolation Forest training | ❌ Missing | No `IsolationForest` import or fit/predict code |
| Project delay XGBoost training | ❌ Missing | No `XGBClassifier` import or training code |
| Project delay predictions | ❌ Missing | No `delay_probability` inference code |
| Risk aggregation | ❌ Missing | No function combining anomaly + exposure signals |
| Risk evidence generation | ❌ Missing | No JSON evidence builder for risk |
| `model_registry` writes | ❌ Missing | No INSERT/UPDATE into `model_registry` |
| Intelligence backfill | ❌ Missing | No script to populate `member_intelligence` / `state_intelligence` from scratch |
| Daily intelligence regeneration | ❌ Missing | `automation/daily_pipeline.py` does not regenerate scores/clusters/risk/models |

---

## 7. Definitive Absence Report

After examining:
- ✅ All current Python/JS/HTML/SQL files in the repository
- ✅ All 16 commits in git history
- ✅ All 27 files ever deleted from the repository
- ✅ Full `git log -S` pickaxe search for every intelligence keyword
- ✅ Git reflog, stashes, packed refs, and loose objects
- ✅ Remote branches and tags
- ✅ Untracked and hidden files
- ✅ Virtual environment packages
- ✅ Database stored procedures/functions/triggers
- ✅ Configuration and dependency files
- ✅ GitHub remote state

**It is definitively concluded that the intelligence-generation implementation does not exist in this repository or its history.**

The persisted DB2 intelligence outputs (`member_intelligence`, `state_intelligence`, `model_registry`, `ml_work_anomaly`) were produced by code that was executed outside of version control — likely from a local script/notebook using the installed `scikit-learn` and `xgboost` libraries in `back end/.venv`, but that source code was never added to the repository.

---

## 8. Recommendations for Recovery

Since the code cannot be located in the repository, the following recovery options remain:

1. **Check other machines / developers** — The original author (or teammate) may have the generation script/notebook locally.
2. **Check Supabase storage / buckets** — If the intelligence layer was run from a cloud environment, scripts may be stored in Supabase Storage or another cloud location.
3. **Check CI/CD or notebook environments** — Look for Google Colab, Kaggle, Databricks, or local Jupyter notebooks associated with the project.
4. **Reconstruct from DB2 outputs** — The registry, cluster labels, and score distribution provide clues to reverse-engineer the methodology, but this is not a true recovery.
5. **Implement fresh** — Create a new, version-controlled intelligence pipeline based on the documented methodology in the finalization requirements.

---

## 9. No Modifications Made

No database writes, code changes, deletions, migrations, commits, or pushes were performed during this investigation.
