"""Vercel serverless entrypoint for the Govsense AI FastAPI backend.

Vercel routes every request under ``/api/*`` to this function (see the
``rewrites`` entry in ``vercel.json``). The FastAPI application declares all of
its routes with the ``/api`` prefix, so no route changes are required.

Environment variables (set these in the Vercel project settings — the local
``back end/.env`` file is git-ignored and never deployed):

    DATABASE_URL          Supabase Postgres (DB1) connection string
    DB2_DATABASE_URL      Supabase Postgres (DB2) connection string
    CORS_ORIGINS          comma-separated allowed origins (optional)
"""

import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)

# The `app` package may end up in different locations depending on how Vercel
# bundles the function (includeFiles preserves the project-relative path, but
# the working directory varies). Register every plausible parent so the import
# succeeds regardless.
for _cand in (
    _HERE,                              # function dir  -> api/app
    os.path.join(_HERE, "api"),         # bundled as    -> <fn>/api/app
    _PARENT,                            # project root  -> back end/app (local)
    os.path.join(_PARENT, "api"),       # project root  -> api/app
    os.path.join(_PARENT, "back end"),  # local layout  -> back end/app
):
    if _cand and os.path.isdir(os.path.join(_cand, "app")) and _cand not in sys.path:
        sys.path.insert(0, _cand)

try:
    from app.main import app  # noqa: F401  (ASGI app; Vercel loads `app`)
except Exception:  # pragma: no cover - deployment diagnostics
    # Surface the import failure as JSON (via /api/health) instead of an opaque
    # FUNCTION_INVOCATION_FAILED, so deployment issues are diagnosable.
    from fastapi import FastAPI

    _BOOT_ERROR = traceback.format_exc()
    app = FastAPI(title="Govsense AI - backend import failed")

    @app.get("/{path:path}")
    async def _boot_error(path: str):
        return {
            "error": "backend import failed",
            "sys_path": sys.path,
            "traceback": _BOOT_ERROR,
        }
