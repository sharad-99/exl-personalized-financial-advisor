"""End-to-end API behaviour against a seeded (synthetic) SQLite database."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.schemas.analytics import AnalyticsResult
from app.schemas.api import CustomerDetail, RecommendationOut
from tests.conftest import AS_OF

UNKNOWN = "00000000-0000-4000-8000-000000000000"


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["database"] == "ok"
    assert "database_url" not in body


def test_openapi_documents_core_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in [
        "/health",
        "/api/v1/customers",
        "/api/v1/customers/{customer_id}",
        "/api/v1/customers/{customer_id}/transactions",
        "/api/v1/customers/{customer_id}/analytics",
        "/api/v1/customers/{customer_id}/goals",
        "/api/v1/customers/{customer_id}/recommendations",
        "/api/v1/customers/{customer_id}/recommendations/refresh",
        "/api/v1/recommendations/{recommendation_id}/feedback",
    ]:
        assert path in paths, path


def test_me_and_customer_list_scoping(client: TestClient, customer_a, advisor) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    me = client.get("/api/v1/me", headers=headers).json()
    assert me["role"] == "customer" and me["customer_id"] == customer_id
    mine = client.get("/api/v1/customers", headers=headers).json()
    assert [c["id"] for c in mine["items"]] == [customer_id]
    everyone = client.get("/api/v1/customers?page_size=100", headers=advisor).json()
    assert everyone["meta"]["total"] == 60
    filtered = client.get("/api/v1/customers?segment=gig_worker", headers=advisor).json()
    assert filtered["meta"]["total"] == 7
    assert all(c["persona_segment"] == "gig_worker" for c in filtered["items"])


def test_customer_detail_schema(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    response = client.get(f"/api/v1/customers/{customer_id}", headers=headers)
    assert response.status_code == 200
    detail = CustomerDetail.model_validate(response.json())
    assert detail.is_synthetic and detail.accounts
    assert all(a.masked_number.startswith("XXXX") for a in detail.accounts)
    assert detail.transaction_summary.transaction_count > 100


def test_transactions_pagination_filters_and_classification(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    url = f"/api/v1/customers/{customer_id}/transactions"
    first = client.get(url, params={"page_size": 10}, headers=headers).json()
    assert len(first["items"]) == 10 and first["meta"]["total"] > 10
    dates = [t["posted_on"] for t in first["items"]]
    assert dates == sorted(dates, reverse=True)
    credits = client.get(
        url, params={"direction": "credit", "start_date": "2026-09-01", "end_date": "2026-09-30"}, headers=headers
    ).json()
    assert credits["items"] and all(t["direction"] == "credit" for t in credits["items"])
    assert all("2026-09-01" <= t["posted_on"] <= "2026-09-30" for t in credits["items"])
    assert {t["counted_as"] for t in credits["items"]} <= {"income", "refund", "excluded"}
    assert isinstance(first["items"][0]["amount"], str)  # exact decimal string


def test_invalid_inputs_return_consistent_errors(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    cases = [
        f"/api/v1/customers/{customer_id}/transactions?start_date=2026-09-30&end_date=2026-09-01",
        f"/api/v1/customers/{customer_id}/transactions?page_size=5000",
        f"/api/v1/customers/{customer_id}/transactions?direction=sideways",
        f"/api/v1/customers/{customer_id}/analytics?months=0",
        f"/api/v1/customers/{customer_id}/analytics?start_date=2026-01-01",
        "/api/v1/customers/not-a-uuid",
    ]
    for url in cases:
        response = client.get(url, headers=headers)
        assert response.status_code == 422, url
        error = response.json()["error"]
        assert error["code"] == "validation_error" and error["request_id"]


def test_unknown_customer_is_404(client: TestClient, advisor) -> None:  # type: ignore[no-untyped-def]
    response = client.get(f"/api/v1/customers/{UNKNOWN}", headers=advisor)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_analytics_schema_and_values(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    response = client.get(f"/api/v1/customers/{customer_id}/analytics", headers=headers)
    assert response.status_code == 200
    result = AnalyticsResult.model_validate(response.json())
    assert result.is_synthetic_data
    assert result.period.as_of == AS_OF
    assert result.totals.net_observed_cash_flow == result.totals.total_income - result.totals.total_expenses
    spend = sum((c.amount for c in result.spending_by_category), Decimal("0"))
    assert spend == result.totals.total_expenses
    custom = client.get(
        f"/api/v1/customers/{customer_id}/analytics",
        params={"start_date": "2026-01-01", "end_date": "2026-03-31"},
        headers=headers,
    ).json()
    assert custom["period"]["months_in_period"] == 3


def test_goal_lifecycle(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    url = f"/api/v1/customers/{customer_id}/goals"
    created = client.post(
        url,
        headers=headers,
        json={
            "name": "Bike Fund",
            "goal_type": "vehicle",
            "target_amount": "90000.00",
            "saved_amount": "10000",
            "monthly_contribution": "2500",
            "target_date": "2027-12-01",
            "priority": 2,
        },
    )
    assert created.status_code == 201, created.text
    goal = created.json()
    assert goal["target_amount"] == "90000.00"
    duplicate = client.post(
        url, headers=headers, json={"name": "bike fund", "goal_type": "vehicle", "target_amount": "1000"}
    )
    assert duplicate.status_code == 409
    listed = client.get(url, headers=headers).json()
    mine = next(g for g in listed if g["goal"]["id"] == goal["id"])
    assert mine["plan"]["required_monthly"] is not None
    updated = client.patch(f"{url}/{goal['id']}", headers=headers, json={"saved_amount": "20000.00"})
    assert updated.status_code == 200 and updated.json()["saved_amount"] == "20000.00"


def test_goal_validation(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    url = f"/api/v1/customers/{customer_id}/goals"
    bad = [
        {"name": "", "goal_type": "travel", "target_amount": "100"},
        {"name": "X", "goal_type": "lottery", "target_amount": "100"},
        {"name": "X", "goal_type": "travel", "target_amount": "-5"},
        {"name": "X", "goal_type": "travel", "target_amount": "100.123"},
        {"name": "X", "goal_type": "travel", "target_amount": "100", "unexpected": 1},
        {"name": "X", "goal_type": "travel", "target_amount": "100", "target_date": "2020-01-01"},
        {"name": "X", "goal_type": "travel", "target_amount": "100", "saved_amount": "500"},
    ]
    for payload in bad:
        assert client.post(url, headers=headers, json=payload).status_code == 422, payload


def test_recommendations_generated_once_and_refresh_is_idempotent(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    url = f"/api/v1/customers/{customer_id}/recommendations"
    first = client.get(url, headers=headers).json()
    assert first["items"], "customer 1 should have at least one recommendation"
    for item in first["items"]:
        rec = RecommendationOut.model_validate(item)
        assert rec.rule_id and rec.rule_version >= 1 and rec.evidence["calculations"]
        assert rec.status == "pending" and rec.analytics_as_of == AS_OF
    second = client.get(url, headers=headers).json()
    assert [i["id"] for i in second["items"]] == [i["id"] for i in first["items"]]
    refresh = client.post(f"{url}/refresh", headers=headers).json()
    assert refresh["created"] == 0 and refresh["expired"] == 0
    assert len(refresh["active"]) == len(first["items"])


def test_feedback_flow_and_status_transitions(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    recs = client.get(f"/api/v1/customers/{customer_id}/recommendations", headers=headers).json()["items"]
    rec_id = recs[0]["id"]
    accepted = client.post(
        f"/api/v1/recommendations/{rec_id}/feedback", headers=headers, json={"action": "accepted", "comment": "Will do"}
    )
    assert accepted.status_code == 201
    assert accepted.json()["recommendation"]["status"] == "accepted"
    correction_without_reason = client.post(
        f"/api/v1/recommendations/{rec_id}/feedback", headers=headers, json={"action": "correction"}
    )
    assert correction_without_reason.status_code == 422
    correction = client.post(
        f"/api/v1/recommendations/{rec_id}/feedback",
        headers=headers,
        json={"action": "correction", "reason_code": "income_incorrect"},
    )
    assert correction.status_code == 201
    completed = client.post(f"/api/v1/recommendations/{rec_id}/feedback", headers=headers, json={"action": "completed"})
    assert completed.json()["recommendation"]["status"] == "completed"
    reopen = client.post(f"/api/v1/recommendations/{rec_id}/feedback", headers=headers, json={"action": "accepted"})
    assert reopen.status_code == 409
    detail = client.get(f"/api/v1/recommendations/{rec_id}", headers=headers).json()
    assert [f["action"] for f in detail["feedback"]] == ["accepted", "correction", "completed"]
    # Refresh keeps the customer's decision and does not create a duplicate active item.
    refresh = client.post(f"/api/v1/customers/{customer_id}/recommendations/refresh", headers=headers).json()
    assert rec_id not in {r["id"] for r in refresh["active"]}
    history = client.get(f"/api/v1/customers/{customer_id}/recommendations?status=completed", headers=headers)
    assert [r["id"] for r in history.json()["items"]] == [rec_id]


def test_dismissed_subject_not_reraised(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    recs = client.get(f"/api/v1/customers/{customer_id}/recommendations", headers=headers).json()["items"]
    target = recs[-1]
    client.post(
        f"/api/v1/recommendations/{target['id']}/feedback",
        headers=headers,
        json={"action": "dismissed", "reason_code": "not_relevant"},
    )
    refresh = client.post(f"/api/v1/customers/{customer_id}/recommendations/refresh", headers=headers).json()
    active_rules = {(r["rule_id"], r["id"]) for r in refresh["active"]}
    assert (target["rule_id"], target["id"]) not in active_rules


def test_withdrawing_consent_expires_pending_recommendations(client: TestClient, customer_a) -> None:  # type: ignore[no-untyped-def]
    customer_id, headers = customer_a
    url = f"/api/v1/customers/{customer_id}/recommendations"
    assert client.get(url, params={"status": "pending"}, headers=headers).json()["items"]
    consent = client.patch("/api/v1/me/consent", headers=headers, json={"data_sharing_consent": False})
    assert consent.status_code == 200 and consent.json()["data_sharing_consent"] is False
    # Expired immediately, not only on the next refresh.
    assert client.get(url, params={"status": "pending"}, headers=headers).json()["items"] == []
    refresh = client.post(f"{url}/refresh", headers=headers).json()
    assert refresh["active"] == [] and refresh["created"] == 0
    assert all("consented" in s["reason"] for s in refresh["suppressed_rules"])
    assert client.patch("/api/v1/me/consent", headers=headers, json={}).status_code == 422


def test_low_confidence_customer_only_gets_data_request(client: TestClient, advisor, dataset) -> None:  # type: ignore[no-untyped-def]
    stale = next(f["customer_id"] for f in dataset.financial_profiles if f["persona_segment"] == "stale_profile")
    body = client.get(f"/api/v1/customers/{stale}/recommendations", headers=advisor).json()
    assert {r["rule_id"] for r in body["items"]} <= {"MISSING_INFO_REQUEST", "GOAL_PROGRESS_CELEBRATE"}
    assert any(r["rule_id"] == "MISSING_INFO_REQUEST" for r in body["items"])
    assert all(r["confidence"] == "low" for r in body["items"])


def test_rule_catalogue(client: TestClient, advisor) -> None:  # type: ignore[no-untyped-def]
    rules = client.get("/api/v1/recommendation-rules", headers=advisor).json()
    assert len(rules) == 8 and all(r["version"] == 1 for r in rules)


def test_data_quality_events_recorded(client: TestClient, advisor, dataset) -> None:  # type: ignore[no-untyped-def]
    stale = next(f["customer_id"] for f in dataset.financial_profiles if f["persona_segment"] == "stale_profile")
    events = client.get(f"/api/v1/customers/{stale}/data-quality-events", headers=advisor).json()
    assert "stale_transactions" in {e["check_code"] for e in events}


def test_concurrent_first_generation_does_not_conflict(session_factory, dataset) -> None:  # type: ignore[no-untyped-def]
    """Simulates the race: a second session inserts the same recommendations first."""
    from app.models.tables import Profile
    from app.services import recommendation_service as svc

    customer_id = dataset.customer_ids()[0]
    with session_factory() as winner, session_factory() as loser:
        loser_customer = loser.get(Profile, customer_id)
        svc._refresh_once(winner, winner.get(Profile, customer_id), AS_OF, None)  # winner commits first
        original = svc._refresh_once
        calls = {"n": 0}

        def stale_first_attempt(session, customer, as_of, actor):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            if calls["n"] == 1:  # behave as if the rows were not visible yet -> duplicate insert
                from sqlalchemy.exc import IntegrityError

                raise IntegrityError("insert", {}, Exception("duplicate key"))
            return original(session, customer, as_of, actor)

        svc._refresh_once = stale_first_attempt
        try:
            summary = svc.refresh_for_customer(loser, loser_customer, AS_OF, None)
        finally:
            svc._refresh_once = original
        assert calls["n"] == 2 and summary.created == 0
