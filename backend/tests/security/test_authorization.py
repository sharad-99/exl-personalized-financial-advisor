"""Authentication and customer-level authorisation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import LOCAL_AUDIENCE, LOCAL_ISSUER
from app.main import create_app

PUBLIC = {("GET", "/health"), ("POST", "/api/v1/auth/local/login")}
SAMPLE_ID = "00000000-0000-4000-8000-000000000001"


def protected_routes() -> list[tuple[str, str]]:
    """Every documented /api route except the explicitly public ones."""
    paths = create_app(get_settings()).openapi()["paths"]
    routes = [
        (method.upper(), path)
        for path, operations in paths.items()
        if path.startswith("/api/")
        for method in operations
        if (method.upper(), path) not in PUBLIC
    ]
    assert len(routes) >= 12
    return sorted(routes)


@pytest.mark.parametrize(("method", "path"), protected_routes())
def test_every_protected_route_requires_authentication(client: TestClient, method: str, path: str) -> None:
    url = (
        path.replace("{customer_id}", SAMPLE_ID)
        .replace("{recommendation_id}", SAMPLE_ID)
        .replace("{goal_id}", SAMPLE_ID)
    )
    response = client.request(method, url, json={})
    assert response.status_code == 401, (method, path)
    assert response.json()["error"]["code"] == "unauthenticated"
    assert response.headers.get("www-authenticate") == "Bearer"


def test_invalid_tokens_rejected(client: TestClient) -> None:
    now = datetime.now(UTC)
    claims = {"sub": str(uuid.uuid4()), "aud": LOCAL_AUDIENCE, "iss": LOCAL_ISSUER, "exp": now + timedelta(hours=1)}
    tokens = [
        "garbage",
        jwt.encode(claims, "a-completely-different-secret-of-sufficient-length", algorithm="HS256"),
        jwt.encode(
            {**claims, "exp": now - timedelta(seconds=5)},
            get_settings().local_jwt_secret.get_secret_value(),
            algorithm="HS256",
        ),  # type: ignore[union-attr]
    ]
    for token in tokens:
        response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_valid_token_without_profile_is_forbidden(client: TestClient) -> None:
    from app.core.security import issue_local_token

    token, _ = issue_local_token(get_settings(), uuid.uuid4(), "customer")
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_customer_a_cannot_read_customer_b(client: TestClient, customer_a, customer_b) -> None:  # type: ignore[no-untyped-def]
    _, headers_a = customer_a
    b_id, _ = customer_b
    for suffix in [
        "",
        "/transactions",
        "/analytics",
        "/goals",
        "/obligations",
        "/recommendations",
        "/data-quality-events",
    ]:
        response = client.get(f"/api/v1/customers/{b_id}{suffix}", headers=headers_a)
        assert response.status_code == 404, suffix  # existence is not disclosed
    listing = client.get("/api/v1/customers", params={"search": "customer02"}, headers=headers_a).json()
    assert listing["items"] == []


def test_customer_a_cannot_modify_customer_b(client: TestClient, customer_a, customer_b, dataset) -> None:  # type: ignore[no-untyped-def]
    _, headers_a = customer_a
    b_id, _ = customer_b
    goal = {"name": "Hijack", "goal_type": "other", "target_amount": "100.00"}
    assert client.post(f"/api/v1/customers/{b_id}/goals", headers=headers_a, json=goal).status_code == 404
    b_goal = next((g for g in dataset.goals if str(g["customer_id"]) == b_id), None)
    if b_goal:
        response = client.patch(
            f"/api/v1/customers/{b_id}/goals/{b_goal['id']}", headers=headers_a, json={"saved_amount": "1.00"}
        )
        assert response.status_code == 404
    assert client.post(f"/api/v1/customers/{b_id}/recommendations/refresh", headers=headers_a).status_code == 404


def test_goal_id_from_another_customer_is_not_reachable_via_own_path(client: TestClient, customer_a, dataset) -> None:  # type: ignore[no-untyped-def]
    a_id, headers_a = customer_a
    foreign = next(g for g in dataset.goals if str(g["customer_id"]) != a_id)
    response = client.patch(
        f"/api/v1/customers/{a_id}/goals/{foreign['id']}", headers=headers_a, json={"saved_amount": "1.00"}
    )
    assert response.status_code == 404


def test_feedback_on_another_customers_recommendation_rejected(client: TestClient, customer_a, customer_b) -> None:  # type: ignore[no-untyped-def]
    _, headers_a = customer_a
    b_id, headers_b = customer_b
    b_recs = client.get(f"/api/v1/customers/{b_id}/recommendations", headers=headers_b).json()["items"]
    assert b_recs
    rec_id = b_recs[0]["id"]
    response = client.post(
        f"/api/v1/recommendations/{rec_id}/feedback", headers=headers_a, json={"action": "dismissed"}
    )
    assert response.status_code == 404
    assert client.get(f"/api/v1/recommendations/{rec_id}", headers=headers_a).status_code == 404
    still = client.get(f"/api/v1/recommendations/{rec_id}", headers=headers_b).json()
    assert still["status"] == "pending" and still["feedback"] == []


def test_advisor_is_read_only(client: TestClient, advisor, customer_b) -> None:  # type: ignore[no-untyped-def]
    b_id, headers_b = customer_b
    assert client.get(f"/api/v1/customers/{b_id}/analytics", headers=advisor).status_code == 200
    recs = client.get(f"/api/v1/customers/{b_id}/recommendations", headers=advisor).json()["items"]
    goal = {"name": "Advisor goal", "goal_type": "other", "target_amount": "100.00"}
    assert client.post(f"/api/v1/customers/{b_id}/goals", headers=advisor, json=goal).status_code == 403
    assert client.post(f"/api/v1/customers/{b_id}/recommendations/refresh", headers=advisor).status_code == 403
    response = client.post(
        f"/api/v1/recommendations/{recs[0]['id']}/feedback", headers=advisor, json={"action": "accepted"}
    )
    assert response.status_code == 403
