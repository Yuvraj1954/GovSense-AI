"""Vercel serverless entrypoint for the Govsense AI FastAPI backend.

Vercel routes every request under ``/api/*`` to this function (the ``api/``
directory convention). The FastAPI application already declares all of its
routes with the ``/api`` prefix, so no additional rewrite is required.

Environment variables (set these in the Vercel project settings — the local
``.env`` file is git-ignored and never deployed):

    DATABASE_URL          Supabase Postgres (DB1) connection string
    DB2_DATABASE_URL      Supabase Postgres (DB2) connection string
    CORS_ORIGINS          comma-separated allowed origins (optional)
"""

from app.main import app  # noqa: F401  (Vercel loads the ASGI app named `app`)
