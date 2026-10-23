"""Database engine configuration for long-running servers vs serverless (Vercel)."""

from sqlalchemy.pool import NullPool, QueuePool

from app.core.config import Settings
from app.db.connection import build_engine

SESSION_POOLER = "postgresql://user:pw@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
TRANSACTION_POOLER = "postgresql://user:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"


def test_server_mode_pools_connections() -> None:
    engine = build_engine(SESSION_POOLER)
    assert isinstance(engine.pool, QueuePool)
    assert engine.url.drivername == "postgresql+psycopg"


def test_serverless_mode_opens_a_connection_per_request() -> None:
    assert isinstance(build_engine(SESSION_POOLER, serverless=True).pool, NullPool)


def test_pooler_specific_connect_args(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: list[dict] = []
    import app.db.connection as connection

    real = connection.create_engine

    def spy(url, **kwargs):  # type: ignore[no-untyped-def]
        captured.append(kwargs.get("connect_args", {}))
        return real(url, **kwargs)

    monkeypatch.setattr(connection, "create_engine", spy)
    build_engine(SESSION_POOLER)
    build_engine(TRANSACTION_POOLER, serverless=True)
    session_args, transaction_args = captured
    assert session_args["options"] == "-c statement_timeout=10000"
    assert "prepare_threshold" not in session_args
    assert transaction_args["prepare_threshold"] is None  # prepared statements break transaction pooling
    assert "options" not in transaction_args


def test_vercel_environment_enables_serverless(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    base = {"auth_mode": "supabase", "supabase_url": "https://abc.supabase.co", "database_url": "sqlite:///:memory:"}
    monkeypatch.delenv("VERCEL", raising=False)
    assert Settings(_env_file=None, **base).is_serverless is False  # type: ignore[call-arg]
    monkeypatch.setenv("VERCEL", "1")
    assert Settings(_env_file=None, **base).is_serverless is True  # type: ignore[call-arg]
    monkeypatch.delenv("VERCEL")
    assert Settings(_env_file=None, serverless=True, **base).is_serverless is True  # type: ignore[call-arg]
