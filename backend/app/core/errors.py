"""Consistent error envelope and exception handlers.

Every error response looks like:
    {"error": {"code": "not_found", "message": "...", "request_id": "...", "details": [...]}}
Internal exception details are logged server-side, never returned.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from app.core.logging import get_logger, request_id_var

logger = get_logger("app.errors")

STATUS_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
    504: "timeout",
}


class ApiError(HTTPException):
    def __init__(
        self, status_code: int, message: str, code: str | None = None, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code or STATUS_CODES.get(status_code, "error")


def error_body(
    status_code: int, message: str, code: str | None = None, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": code or STATUS_CODES.get(status_code, "error"),
        "message": message,
        "request_id": request_id_var.get(),
    }
    if details:
        body["details"] = details
    return {"error": body}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = getattr(exc, "code", None)
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(
            error_body(exc.status_code, message, code),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Echo location/message/type only — never the submitted input values.
        details = [
            {"loc": [str(p) for p in err.get("loc", ())], "msg": err.get("msg", ""), "type": err.get("type", "")}
            for err in exc.errors()
        ]
        return JSONResponse(error_body(422, "Request validation failed", details=details), status_code=422)

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("integrity_error", extra={"fields": {"error": type(exc.orig).__name__}})
        return JSONResponse(error_body(409, "The request conflicts with existing data"), status_code=409)

    @app.exception_handler(OperationalError)
    async def db_unavailable(_: Request, exc: OperationalError) -> JSONResponse:
        logger.error("database_unavailable", extra={"fields": {"error": type(exc.orig).__name__}})
        return JSONResponse(error_body(503, "The database is temporarily unavailable"), status_code=503)

    @app.exception_handler(SQLAlchemyError)
    async def db_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("database_error", extra={"fields": {"error": type(exc).__name__}})
        return JSONResponse(error_body(503, "A database error occurred"), status_code=503)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"fields": {"error": type(exc).__name__}})
        return JSONResponse(error_body(500, "An unexpected error occurred"), status_code=500)
