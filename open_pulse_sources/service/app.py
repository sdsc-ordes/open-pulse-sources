"""FastAPI entrypoint for the open-pulse-sources index service.

Serve with::

    uvicorn open_pulse_sources.service.app:app --host 0.0.0.0 --port 8080

Auth mirrors the monolith: every route (except ``/`` and ``/health``)
requires ``Authorization: Bearer <API_TOKEN>`` and fails closed when
``API_TOKEN`` is unset.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from open_pulse_sources.service.api import router

try:
    _VERSION = package_version("open-pulse-sources")
except PackageNotFoundError:
    _VERSION = "unknown"

app = FastAPI(
    title="Open Pulse Sources",
    description=(
        "RAG source-index service: ingest / search / stats / compact / reset "
        "for every index, plus the federated store manifest. Extracted from "
        "git-metadata-extractor's /v2/indices surface — routes keep the /v2 "
        "prefix for drop-in compatibility."
    ),
    version=_VERSION,
)
app.include_router(router)


@app.get("/health", tags=["Service"])
async def health() -> dict[str, str]:
    """Liveness probe (open, no auth)."""
    return {"status": "healthy", "service": "open-pulse-sources"}


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "service": "open-pulse-sources",
        "docs": "/docs",
        "health": "/health",
    }


@app.exception_handler(ValueError)
async def missing_env_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Map missing-credential config errors to a clean 503.

    Every index config raises ``ValueError("Missing required environment
    variable: <NAME>")`` when a required credential is absent
    (``require_rcp()`` and friends). Without this handler those surfaced as
    raw 500s on the search/ingest routes (found in the 2026-07-14 live
    smoke tests — GME task brief 04). Other ValueErrors keep the default
    500 shape.
    """
    if "Missing required environment variable" in str(exc):
        return JSONResponse(status_code=503, content={"detail": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
