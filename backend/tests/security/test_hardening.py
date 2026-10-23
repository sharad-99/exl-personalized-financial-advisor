"""Secret handling, abuse protection, CORS and input safety."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app
from tests.conftest import PASSWORD, customer_email


def test_privileged_values_never_returned(client: TestClient, customer_a, advisor) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    settings = get_settings()
    secrets = [settings.local_jwt_secret.get_secret_value(), PASSWORD]  # type: ignore[union-attr]
    urls = [
        "/health",
        "/openapi.json",
        "/api/v1/me",
        f"/api/v1/customers/{customer_id}",
        f"/api/v1/customers/{customer_id}/analytics",
        f"/api/v1/customers/{customer_id}/recommendations",
        "/api/v1/recommendation-rules",
    ]
    for url in urls:
        text = client.get(url, headers=headers).text
        for secret in secrets:
            assert secret not in text, url
    me = client.get("/api/v1/me", headers=headers).json()
    assert "auth_user_id" not in me and "password" not in me


def test_wrong_password_and_unknown_user_look_identical(client: TestClient) -> None:
    wrong = client.post("/api/v1/auth/local/login", json={"email": customer_email(3), "password": "nope"})
    unknown = client.post("/api/v1/auth/local/login", json={"email": "ghost@demo.exl.test", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_login_rate_limited(client: TestClient) -> None:
    statuses = [
        client.post("/api/v1/auth/local/login", json={"email": customer_email(4), "password": "bad"}).status_code
        for _ in range(7)
    ]
    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429


def test_refresh_rate_limited(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    limit = get_settings().rate_limit_sensitive_per_minute
    codes = [
        client.post(f"/api/v1/customers/{customer_id}/recommendations/refresh", headers=headers).status_code
        for _ in range(limit + 1)
    ]
    assert codes[-1] == 429 and set(codes[:-1]) == {200}


def test_local_login_disabled_in_supabase_mode() -> None:
    settings = Settings(
        _env_file=None,
        auth_mode="supabase",
        supabase_url="https://abc.supabase.co",  # type: ignore[call-arg]
        database_url="sqlite:///:memory:",
    )
    client = TestClient(create_app(settings))
    response = client.post("/api/v1/auth/local/login", json={"email": customer_email(1), "password": PASSWORD})
    assert response.status_code == 404


def test_injection_style_input_is_treated_as_data(client: TestClient, advisor) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/api/v1/customers", params={"search": "' OR 1=1 --"}, headers=advisor)
    assert response.status_code == 200 and response.json()["items"] == []
    response = client.get("/api/v1/customers", params={"segment": "x; drop table profiles"}, headers=advisor)
    assert response.status_code == 422
    assert client.get("/api/v1/customers", headers=advisor).json()["meta"]["total"] == 60


def test_oversized_body_rejected(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    payload = '{"name": "' + "x" * 70_000 + '"}'
    response = client.post(
        f"/api/v1/customers/{customer_id}/goals",
        content=payload,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_validation_errors_do_not_echo_input(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    marker = "<script>alert('x')</script>"
    response = client.post(
        f"/api/v1/customers/{customer_id}/goals",
        headers=headers,
        json={"name": "ok", "goal_type": marker, "target_amount": "1"},
    )
    assert response.status_code == 422
    assert marker not in response.text


def test_cors_allows_only_configured_origins(client: TestClient) -> None:
    allowed = client.options(
        "/api/v1/me", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    denied = client.options(
        "/api/v1/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in denied.headers


def test_security_headers_present(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"]


def test_audit_log_has_no_free_text_or_tokens(client: TestClient, customer_a, session_factory) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    from app.models.tables import AuditEvent

    customer_id, headers = customer_a
    rec = client.get(f"/api/v1/customers/{customer_id}/recommendations", headers=headers).json()["items"][0]
    client.post(
        f"/api/v1/recommendations/{rec['id']}/feedback",
        headers=headers,
        json={"action": "dismissed", "comment": "PRIVATE NOTE 42"},
    )
    with session_factory() as session:
        events = session.scalars(select(AuditEvent)).all()
    blob = " ".join(str(e.metadata_) for e in events)
    assert "PRIVATE NOTE 42" not in blob
    assert "Bearer" not in blob
    assert {"auth.local_login", "recommendation.feedback.dismissed"} <= {e.action for e in events}


def test_rate_limits_are_per_user_not_shared(client: TestClient, customer_a, customer_b) -> None:  # type: ignore[no-untyped-def]
    a_id, a_headers = customer_a
    b_id, b_headers = customer_b
    limit = get_settings().rate_limit_sensitive_per_minute
    for _ in range(limit):
        client.post(f"/api/v1/customers/{a_id}/recommendations/refresh", headers=a_headers)
    assert client.post(f"/api/v1/customers/{a_id}/recommendations/refresh", headers=a_headers).status_code == 429
    # Same client IP (as behind the Next.js proxy), different user: not affected.
    assert client.post(f"/api/v1/customers/{b_id}/recommendations/refresh", headers=b_headers).status_code == 200


def test_api_docs_and_schema_hidden_in_production() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        auth_mode="supabase",  # type: ignore[call-arg]
        supabase_url="https://abc.supabase.co",
        database_url="postgresql://u:p@db.invalid:5432/x",
        cors_allowed_origins="https://app.example.com",
    )
    client = TestClient(create_app(settings))
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path
