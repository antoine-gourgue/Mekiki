"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from mekiki_engine import __version__
from mekiki_engine.auth import SignInThrottle
from mekiki_engine.browser.service import Browsers
from mekiki_engine.config import EngineConfig, load_config
from mekiki_engine.db import create_db_engine, session_factory
from mekiki_engine.resale.ebay import EbayBrowse
from mekiki_engine.routes import (
    auth,
    browser,
    items,
    lots,
    reports,
    resale,
    scanner,
    settings,
    system,
)
from mekiki_engine.scanner.discovery import DiscoveryJobs
from mekiki_engine.scanner.runner import ScannerWorker, SourceFactory
from mekiki_engine.scanner.sources.base import PoliteClient
from mekiki_engine.scanner.sources.registry import build_source
from mekiki_engine.services.portfolio import NotFoundError

BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


def create_app(
    config: EngineConfig | None = None,
    *,
    http_transport: httpx.BaseTransport | None = None,
    source_factory: SourceFactory = build_source,
) -> FastAPI:
    """Build the app; the database is created and migrated before the first request.

    ``http_transport`` and ``source_factory`` let tests replace the marketplaces and
    Cardmarket with fakes.
    """
    config = config or load_config()
    engine = create_db_engine(config.database_url)
    sessions = session_factory(engine)
    http = PoliteClient(transport=http_transport)
    worker = ScannerWorker(sessions, http, source_factory=source_factory)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if config.background_jobs:
            worker.start()
        yield
        worker.stop()
        app.state.browsers.stop_all()
        http.close()
        engine.dispose()

    app = FastAPI(title="Mekiki engine", version=__version__, lifespan=lifespan)
    app.state.config = config
    app.state.session_factory = sessions
    app.state.http = http
    app.state.scanner = worker
    app.state.source_factory = source_factory
    app.state.discovery = DiscoveryJobs(sessions, http, source_factory=source_factory)
    app.state.sign_in_throttle = SignInThrottle()
    app.state.browsers = Browsers(config.data_dir)
    app.state.ebay = (
        EbayBrowse(http, config.ebay_client_id, config.ebay_client_secret, config.ebay_marketplace)
        if config.ebay_client_id and config.ebay_client_secret
        else None
    )

    for module in (system, auth, settings, lots, items, reports, scanner, resale, browser):
        app.include_router(module.router)

    @app.exception_handler(NotFoundError)
    async def _not_found(_request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.middleware("http")
    async def _json_bodies_only(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Browsers send text/plain or form bodies cross-origin without a CORS preflight;
        # requiring JSON forces one, so only the allowed origins can send data.
        content_type = request.headers.get("content-type", "")
        has_body = request.headers.get("content-length", "0") != "0" or (
            "transfer-encoding" in request.headers
        )
        is_json = content_type.startswith("application/json")
        if request.method in BODY_METHODS and has_body and not is_json:
            return JSONResponse(
                status_code=415, content={"detail": "request bodies must be application/json"}
            )
        return await call_next(request)

    # Rejecting any other Host header defeats DNS rebinding: a web page cannot reach the
    # engine through a hostname it controls that happens to resolve to 127.0.0.1.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.allowed_hosts))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )
    return app
