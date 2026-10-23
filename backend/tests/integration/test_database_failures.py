"""The API must fail safely (503 + error envelope, no internals) when the database is down."""

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.analytics import evaluation_date
from app.core.config import get_settings
from app.db.connection import get_db
from app.main import create_app
from tests.conftest import AS_OF


def broken_client() -> TestClient:
    # A database file in a directory that does not exist -> OperationalError on first use.
    engine = create_engine("sqlite:////nonexistent-dir/for-tests/db.sqlite")
    app = create_app(get_settings())

    def _db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[evaluation_date] = lambda: AS_OF
    return TestClient(app, raise_server_exceptions=False)


def test_health_reports_degraded_database() -> None:
    body = broken_client().get("/health").json()
    assert body["status"] == "degraded" and body["database"] == "unavailable"


def test_protected_route_returns_503_without_leaking_details() -> None:
    import uuid

    from app.core.security import issue_local_token

    token, _ = issue_local_token(get_settings(), uuid.uuid4(), "customer")
    response = broken_client().get("/api/v1/customers", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "service_unavailable"
    assert "sqlite" not in response.text.lower() and "nonexistent" not in response.text
