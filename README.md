# Govesense AI — MPLADS Monitoring Dashboard

Interactive dashboards and analytics for the MPLADS (Members of Parliament
Local Area Development Scheme) dataset: national overview, state/MP/MLA
profiles, project analytics, and an AI-assisted risk centre.

The project is a **static frontend** (HTML + Tailwind CDN + vanilla JS) backed
by a **FastAPI** service that reads from two Supabase Postgres databases.

---

## Repository layout

```
.
├── app/                    # FastAPI application
│   ├── main.py             # ASGI entrypoint (exposes `app`) — Vercel entrypoint
│   ├── config.py           # Settings (reads environment / .env)
│   ├── database.py         # asyncpg connection pools (DB1 + DB2)
│   └── routes/             # dashboard / classification / data_updated routers
├── public/                 # Static frontend, served from the CDN at the root URL
│   ├── *.html              # dashboard, mps, mpdetail, state, statedetail, …
│   ├── index.html          # Splash screen → dashboard.html
│   ├── js/                 # Frontend logic (config.js resolves the API base)
│   └── favicon/ · logo.png # Static assets
├── scripts/                # Classification / pipeline helpers
├── requirements.txt        # Python dependencies
├── vercel.json             # Vercel configuration
├── run_all.py              # Local dev launcher (API + static server)
└── .env.example            # Environment variable template
```

---

## Local development

1. Create the environment file and fill in the Supabase credentials:

   ```bash
   cp .env.example .env
   ```

2. Install dependencies and start both servers:

   ```bash
   pip install -r requirements.txt
   python run_all.py          # FastAPI on :8000, static server on :5500
   ```

3. Open <http://localhost:5500>.

`run_all.py` launches:
- **Backend** — `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`
- **Frontend** — `python -m http.server 5500`

---

## Deploying to Vercel

The project deploys as a single Vercel project. Vercel auto-detects the
FastAPI app at `app/main.py` (a supported entrypoint) and turns it into one
serverless function; the static pages in `public/` are served from the CDN at
their root paths.

1. **Import the repository** in the Vercel dashboard. No build command or
   output directory is required.

2. **Add Environment Variables** (Project → Settings → Environment Variables).
   These mirror the local `.env` and are **never committed**:

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

`public/js/config.js` sets `window.API_BASE`:

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
