"""Tests against real PostgreSQL. Skipped unless TEST_DATABASE_URL is set, e.g.

    TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54329/exl_test pytest -m postgres

The database is wiped (public schema dropped) — never point this at a real environment.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.routes.analytics import evaluation_date
from app.core.config import get_settings
from app.core.security import rate_limiter
from app.db.connection import build_engine, get_db
from app.db.migrate import apply_migrations
from app.main import create_app
from app.synthetic_data.seed import seed_database
from tests.conftest import AS_OF, PASSWORD, customer_email

URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not URL.startswith("postgres"), reason="TEST_DATABASE_URL not set to PostgreSQL"),
]


def _dsn() -> str:
    return URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture(scope="module")
def pg_engine(dataset):  # type: ignore[no-untyped-def]
    with psycopg.connect(_dsn(), autocommit=True) as conn:
        conn.execute("drop schema if exists public cascade")
        conn.execute("create schema public")
        conn.execute("grant usage on schema public to public")
    applied = apply_migrations(URL)
    assert len(applied) >= 3
    assert apply_migrations(URL) == []  # second run is a no-op
    engine = build_engine(URL)
    with Session(engine) as session:
        seed_database(session, dataset, reset=False)
    yield engine
    engine.dispose()


@pytest.fixture()
def pg_client(pg_engine) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    app = create_app(get_settings())
    factory = sessionmaker(bind=pg_engine, expire_on_commit=False, autoflush=False)

    def _db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[evaluation_date] = lambda: AS_OF
    rate_limiter.reset()
    with TestClient(app) as client:
        yield client


def test_migrations_re_runnable(pg_engine) -> None:  # type: ignore[no-untyped-def]
    with psycopg.connect(_dsn(), autocommit=True) as conn:
        for name in [
            "20261024000100_initial_schema.sql",
            "20261024000200_row_level_security.sql",
            "20261024000300_reference_data.sql",
        ]:
            sql = (Path(__file__).resolve().parents[3] / "supabase" / "migrations" / name).read_text(encoding="utf-8")
            conn.execute(sql)  # idempotent re-application must not fail


def test_constraints_enforced(pg_engine) -> None:  # type: ignore[no-untyped-def]
    with psycopg.connect(_dsn(), autocommit=True) as conn:
        account = conn.execute("select id, customer_id from accounts limit 1").fetchone()
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "insert into transactions (account_id, customer_id, external_ref, posted_on, amount, direction, "
                "transaction_type, category, description) values (%s, %s, 'X1', '2026-01-01', -5, 'debit', "
                "'purchase', 'dining', 'bad')",
                account,
            )
        other = conn.execute(
            "select id from profiles where id <> %s and role = 'customer' limit 1", (account[1],)
        ).fetchone()
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(
                "insert into transactions (account_id, customer_id, external_ref, posted_on, amount, direction, "
                "transaction_type, category, description) values (%s, %s, 'X2', '2026-01-01', 5, 'debit', "
                "'purchase', 'dining', 'wrong owner')",
                (account[0], other[0]),
            )


def test_audit_events_are_append_only(pg_engine) -> None:  # type: ignore[no-untyped-def]
    with psycopg.connect(_dsn(), autocommit=True) as conn:
        conn.execute("insert into audit_events (action, entity_type) values ('test.event', 'test')")
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("delete from audit_events where action = 'test.event'")


def test_row_level_security_isolates_customers(pg_engine, dataset) -> None:  # type: ignore[no-untyped-def]
    a = next(p for p in dataset.profiles if p["email"] == customer_email(1))
    b = next(p for p in dataset.profiles if p["email"] == customer_email(2))
    with psycopg.connect(_dsn()) as conn:
        conn.execute("set role authenticated")
        conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (str(a["auth_user_id"]),))
        owners = {r[0] for r in conn.execute("select distinct customer_id from transactions")}
        assert owners == {a["id"]}
        assert conn.execute("select count(*) from accounts where customer_id = %s", (b["id"],)).fetchone()[0] == 0
        profiles = conn.execute("select id from profiles").fetchall()
        assert [r[0] for r in profiles] == [a["id"]]
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("update financial_goals set saved_amount = 0")
        conn.rollback()
    with psycopg.connect(_dsn()) as conn:
        conn.execute("set role anon")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("select * from transactions limit 1")


def test_money_is_exact_numeric(pg_engine) -> None:  # type: ignore[no-untyped-def]
    with psycopg.connect(_dsn()) as conn:
        dtype = conn.execute(
            "select data_type, numeric_precision, numeric_scale from information_schema.columns "
            "where table_name = 'transactions' and column_name = 'amount'"
        ).fetchone()
        assert dtype == ("numeric", 14, 2)


def test_api_against_postgres(pg_client: TestClient, dataset) -> None:  # type: ignore[no-untyped-def]
    login = pg_client.post("/api/v1/auth/local/login", json={"email": customer_email(1), "password": PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = pg_client.get("/api/v1/me", headers=headers).json()
    customer_id = me["customer_id"]
    assert pg_client.get(f"/api/v1/customers/{customer_id}/analytics", headers=headers).status_code == 200
    recs = pg_client.get(f"/api/v1/customers/{customer_id}/recommendations", headers=headers).json()["items"]
    assert recs
    again = pg_client.post(f"/api/v1/customers/{customer_id}/recommendations/refresh", headers=headers).json()
    assert again["created"] == 0
    feedback = pg_client.post(
        f"/api/v1/recommendations/{recs[0]['id']}/feedback", headers=headers, json={"action": "accepted"}
    )
    assert feedback.status_code == 201
    other = next(p for p in dataset.profiles if p["email"] == customer_email(2))
    assert pg_client.get(f"/api/v1/customers/{other['id']}", headers=headers).status_code == 404
