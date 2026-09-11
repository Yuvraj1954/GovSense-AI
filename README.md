# CivicLens AI — MPLADS Monitoring Dashboard

Interactive dashboards and analytics for the MPLADS (Members of Parliament
Local Area Development Scheme) dataset: national overview, state/MP/MLA
profiles, project analytics, and an AI-assisted risk centre.

The project is a **static frontend** (HTML + Tailwind CDN + vanilla JS) backed
by a **FastAPI** service that reads from two Supabase Postgres databases.

---

## Repository layout

```
.
├── *.html                  # Static pages (dashboard, mps, mpdetail, state,
│                           # statedetail, project, airiskcentre, workdetail)
├── index.html              # Splash screen → dashboard.html
├── js/                     # Frontend logic (one data module per page)
│   ├── config.js           # Resolves the API base URL (local vs Vercel)
│   └── …
├── favicon/ · logo.png     # Static assets
├── vercel.json             # Vercel configuration
├── api/                    # Vercel serverless backend
│   ├── index.py            # FastAPI entrypoint (exposes `app`)
│   ├── app/                # FastAPI application (routers, config, db)
│   └── requirements.txt    # Function dependencies
└── back end/               # Local development copy of the backend
    ├── app/                # Same application code as api/app
    ├── scripts/            # Classification/pipeline helpers
    └── .env.example        # Environment variable template
```

> `api/app` and `back end/app` contain the same FastAPI application. `back end`
> is used by `run_all.py` for local development; `api` is what Vercel deploys.

---

## Local development

1. Create the environment file and fill in the Supabase credentials:

   ```bash
   cp "back end/.env.example" "back end/.env"
   ```

2. Install dependencies and start both servers:

   ```bash
   pip install -r "back end/requirements.txt"
   python run_all.py          # FastAPI on :8000, static server on :5500
   ```

3. Open <http://localhost:5500>.

`run_all.py` launches:
- **Backend** — `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
- **Frontend** — `python -m http.server 5500`

---

## Deploying to Vercel

The project deploys as a single Vercel project: the static pages are served
from the repository root and the FastAPI app runs as a serverless function
under `/api/*` (Vercel's `api/` directory convention).

1. **Import the repository** in the Vercel dashboard (framework preset:
   **Other**). No build command or output directory is required.

2. **Add Environment Variables** (Project → Settings → Environment Variables).
   These mirror `back end/.env` and are **never committed**:

   | Variable | Required | Purpose |
   |---|---|---|
   | `DATABASE_URL` | ✅ | DB1 Postgres connection string |
   | `DB2_DATABASE_URL` | ✅ | DB2 Postgres connection string |
   | `CORS_ORIGINS` | optional | Extra allowed origins |
   | `SUPABASE_URL` / `SUPABASE_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | optional | Supabase REST/storage |
   | `DB2_URL` / `DB2_SECRET_KEY` / `DB2_SERVICE_ROLE_KEY` | optional | DB2 REST/storage |

3. **Deploy.** The frontend loads from `https://<project>.vercel.app` and the
   JS calls the same-origin API at `/api/*`.

### How the API base works

`js/config.js` sets `window.API_BASE`:

- on `localhost` / `127.0.0.1` / `file:` → `http://127.0.0.1:8000`
- on any deployed host → `''` (relative), so every request targets
  `/api/...` on the same origin.

Because the frontend and API share an origin on Vercel, no CORS configuration
is needed in production.

---

## Notes

- `.DS_Store`, virtual environments, `__pycache__`, and `.env` files are
  excluded via `.gitignore`.
- Both databases are accessed over TLS by `asyncpg`; pool sizes are kept small
  (`min_size=1`, `max_size=5`) to suit serverless concurrency.
