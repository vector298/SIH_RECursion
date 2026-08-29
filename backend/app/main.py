"""CASE//INTEL API.

    uvicorn app.main:app --reload

Interactive docs at /docs. Start with GET /api/health — it reports which model
backends are actually live, so you know before a demo whether you are running
on real ArcFace weights and a Gemini key or on the local fallbacks.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import analytics, cases, matching
from app.config import settings
from app.db.session import init_db

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
log = logging.getLogger("caseintel")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    from app.core import semantic
    from app.services import face, gemini

    log.info("database   : %s", "sqlite" if settings.is_sqlite else "postgresql")
    log.info("face model : %s%s", face.backend_name(),
             "" if face.is_real_arcface() else "  (fallback — not face recognition)")
    log.info("semantic   : %s", semantic.backend_name())
    log.info("language   : %s", gemini.backend_name())
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "AI-assisted case intelligence for missing and unidentified person "
        "investigations.\n\n"
        "**The system ranks and explains; it never asserts an identification.** "
        "Every match response carries per-source evidence scores and the officer "
        "decision endpoints are the only way a case status changes."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases.router)
app.include_router(cases.extract_router)
app.include_router(matching.router)
app.include_router(analytics.router)


@app.exception_handler(ValueError)
async def _value_error(_request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/", tags=["meta"])
def root():
    return {
        "name": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "health": "/api/health",
        "notice": (
            "AI prioritisation — officer verification required. This service produces "
            "ranked investigative leads, not identifications."
        ),
    }
