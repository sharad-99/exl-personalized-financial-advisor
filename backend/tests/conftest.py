"""Shared fixtures.

Unit tests need no database. Integration and security tests run the real
FastAPI app against an in-memory SQLite database seeded with the synthetic
generator (fixed seed + fixed as_of date, so results are deterministic).
Set TEST_DATABASE_URL=postgresql://... to run the `postgres`-marked tests.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date

# Test configuration must be in place before the app module is imported.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ["AUTH_MODE"] = "local"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LOCAL_JWT_SECRET"] = "test-only-secret-value-that-is-long-enough-123456"
os.environ["LOCAL_DEMO_PASSWORD"] = "test-demo-password"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.api.routes.analytics import evaluation_date  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.security import rate_limiter  # noqa: E402
from app.db.connection import get_db  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.tables import Base  # noqa: E402
from app.synthetic_data.generator import SyntheticDataset, generate_dataset  # noqa: E402
from app.synthetic_data.seed import seed_database  # noqa: E402

AS_OF = date(2026, 10, 24)
SEED = 42
PASSWORD = "test-demo-password"


@pytest.fixture(scope="session")
def dataset() -> SyntheticDataset:
    return generate_dataset(seed=SEED, as_of=AS_OF)


def _memory_engine():  # type: ignore[no-untyped-def]
    from sqlalchemy import event

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


@pytest.fixture(scope="session")
def template_engine(dataset: SyntheticDataset):  # type: ignore[no-untyped-def]
    """Seed once per test session; each test gets a fresh copy (see `engine`)."""
    engine = _memory_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, dataset, reset=False)
    yield engine
    engine.dispose()


@pytest.fixture()
def engine(template_engine):  # type: ignore[no-untyped-def]
    engine = _memory_engine()
    source = template_engine.raw_connection()
    target = engine.raw_connection()
    try:
        source.driver_connection.backup(target.driver_connection)
    finally:
        source.close()
        target.close()
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(engine) -> sessionmaker[Session]:  # type: ignore[no-untyped-def]
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(get_settings())

    def _db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[evaluation_date] = lambda: AS_OF
    rate_limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    rate_limiter.reset()


def login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/local/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def customer_email(index: int) -> str:
    return f"customer{index:02d}@demo.exl.test"


@pytest.fixture()
def customer_a(client: TestClient, dataset: SyntheticDataset) -> tuple[str, dict[str, str]]:
    profile = next(p for p in dataset.profiles if p["email"] == customer_email(1))
    return str(profile["id"]), login(client, customer_email(1))


@pytest.fixture()
def customer_b(client: TestClient, dataset: SyntheticDataset) -> tuple[str, dict[str, str]]:
    profile = next(p for p in dataset.profiles if p["email"] == customer_email(2))
    return str(profile["id"]), login(client, customer_email(2))


@pytest.fixture()
def advisor(client: TestClient) -> dict[str, str]:
    return login(client, "advisor@demo.exl.test")
