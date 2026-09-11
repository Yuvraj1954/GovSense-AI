from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import close_pool
from app.routes.data_updated import router as data_updated_router
from app.routes.classification import router as classification_router
from app.routes.dashboard import router as dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_pool()


app = FastAPI(title="MPLADS Backend", version="0.1.0", lifespan=lifespan)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(data_updated_router, prefix="/api")
app.include_router(classification_router, prefix="/api")
app.include_router(dashboard_router)


@app.get("/api/health")
async def api_health():
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Serve the static frontend. On Vercel the `public/` directory is served by the
# CDN, but mounting it here is a safety net so the app also works when it is
# reached as a single function (and during local runs with uvicorn).
# ---------------------------------------------------------------------------
import os as _os
from fastapi.staticfiles import StaticFiles as _StaticFiles

_APP_DIR = _os.path.dirname(_os.path.abspath(__file__))
for _cand in (
    _os.path.normpath(_os.path.join(_APP_DIR, "..", "..", "public")),
    _os.path.normpath(_os.path.join(_APP_DIR, "..", "public")),
    _os.path.normpath(_os.path.join(_APP_DIR, "public")),
):
    if _os.path.isdir(_cand):
        app.mount("/", _StaticFiles(directory=_cand, html=True), name="static")
        break
