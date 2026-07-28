"""FastAPI application factory. One origin serves UI, REST API and WebSockets."""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import get_settings
from app.logging_conf import configure_logging, get_logger

log = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="JobPilot",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if settings.cookies_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response

    from app.api import api_router, ws_router

    app.include_router(api_router, prefix="/api")
    app.include_router(ws_router)

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # --- static frontend (built by `make front-build`) --------------------
    assets = STATIC_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index_html = STATIC_DIR / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        # API/WS 404s are handled by their routers; everything else falls
        # through to the single-page app.
        if index_html.is_file():
            return FileResponse(index_html)
        return JSONResponse(
            status_code=200,
            content={
                "app": "JobPilot",
                "version": __version__,
                "note": "Frontend build not found. Run `make front-build` or use the Docker image.",
            },
        )

    @app.on_event("startup")
    async def startup() -> None:
        app.state.ws_relay_stop = asyncio.Event()
        from app.ws import redis_relay

        app.state.ws_relay_task = asyncio.create_task(redis_relay(app.state.ws_relay_stop))
        log.info("app.started", version=__version__, public=settings.is_public)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        app.state.ws_relay_stop.set()
        task = getattr(app.state, "ws_relay_task", None)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    return app


app = create_app()
