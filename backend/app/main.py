"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import analytics, auth, customers, feedback, goals, health, recommendations, transactions
from app.core.config import Settings, get_settings
from app.core.errors import error_body, install_error_handlers
from app.core.logging import configure_logging, get_logger, request_id_var

logger = get_logger("app.access")

DESCRIPTION = """
Personalised, explainable financial-wellness insights for bank customers.

**All data served by this API is SYNTHETIC.** Recommendations are produced by
deterministic, versioned rules; every recommendation includes its inputs,
calculations, assumptions and data-confidence indicator. The service does not
recommend securities or specific investment products, does not recommend
borrowing, and never executes transactions.

Money values are JSON strings with two decimal places (exact decimals).
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        docs_url="/docs" if settings.environment != "production" else None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
    )
    install_error_handlers(app)
    # Routes read settings through this dependency; make them see the settings this app was built with.
    app.dependency_overrides[get_settings] = lambda: settings

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if 8 <= len(incoming) <= 64 and incoming.replace("-", "").isalnum() else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            length = int(request.headers.get("content-length") or 0)
        except ValueError:
            length = settings.max_request_body_bytes + 1
        try:
            if length > settings.max_request_body_bytes:
                response: Response = JSONResponse(error_body(413, "Request body too large"), status_code=413)
            else:
                try:
                    response = await asyncio.wait_for(call_next(request), timeout=settings.request_timeout_seconds)
                except TimeoutError:
                    response = JSONResponse(error_body(504, "The request took too long"), status_code=504)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            if request.url.path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-store"
            if settings.environment == "production":
                response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            # Path only — no query string, headers, bodies or tokens.
            logger.info(
                "request",
                extra={
                    "fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )
            return response
        finally:
            request_id_var.reset(token)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,  # bearer tokens, not cookies, are sent to the API
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
        max_age=600,
    )

    for router in (
        health.router,
        auth.router,
        customers.router,
        transactions.router,
        analytics.router,
        goals.router,
        recommendations.router,
        feedback.router,
    ):
        app.include_router(router)
    return app


app = create_app()
