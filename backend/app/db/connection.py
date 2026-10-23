"""Database engine/session management.

SQLite is used for zero-dependency local demos and unit tests; PostgreSQL
(Supabase) everywhere else. Queries are built with SQLAlchemy expressions —
never string concatenation — so user input is always bound as parameters.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


def build_engine(database_url: str, echo: bool = False, serverless: bool = False) -> Engine:
    if database_url.startswith("sqlite"):
        db_path = database_url.removeprefix("sqlite:///")
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(database_url, echo=echo, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    # Supabase's transaction pooler (port 6543) cannot keep prepared statements or startup options
    # between transactions; the session pooler (5432) and direct connections can.
    transaction_pooler = make_url(database_url).port == 6543
    connect_args: dict[str, object] = {"connect_timeout": 10}
    if transaction_pooler:
        connect_args["prepare_threshold"] = None
    else:
        connect_args["options"] = "-c statement_timeout=10000"  # guard against runaway queries (ms)
    if serverless:
        # Serverless instances are short-lived and numerous: holding idle pooled connections in each
        # one would exhaust the database's connection limit. Open per request, close afterwards.
        return create_engine(database_url, echo=echo, poolclass=NullPool, connect_args=connect_args)
    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        connect_args=connect_args,
    )


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return build_engine(settings.database_url, settings.database_echo, serverless=settings.is_serverless)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
