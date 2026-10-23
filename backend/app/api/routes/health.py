from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import AppSettings, DbSession
from app.schemas.api import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut, summary="Liveness and database readiness")
def health(session: DbSession, settings: AppSettings) -> HealthOut:
    try:
        session.execute(text("select 1"))
        database = "ok"
    except SQLAlchemyError:
        database = "unavailable"
    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        version=settings.app_version,
        environment=settings.environment,
        database=database,
        auth_mode=settings.auth_mode,
    )
