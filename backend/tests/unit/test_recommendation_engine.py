"""Recommendation rules: triggers, suppression, traceability and safety."""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date
from decimal import Decimal

import pytest

from app.services.financial_analytics import compute_analytics
from app.services.recommendation_engine import RULES, evaluate
from app.services.recommendation_explanations import explain
from app.synthetic_data.generator import customer_financial_data
from tests.factories import AS_OF, account, customer, goal, monthly_history, obligation, profile, txn


def run(data):  # type: ignore[no-untyped-def]
    return evaluate(data, compute_analytics(data, AS_OF), AS_OF)


def rule_ids(result) -> set[str]:  # type: ignore[no-untyped-def]
    return {o.rule_id for o in result.outcomes}


def test_healthy_customer_gets_no_corrective_advice() -> None:
    result = run(customer(accounts=[account(balance="200000.00")]))
    assert result.confidence == "high"
    assert rule_ids(result) == set()


def test_emergency_fund_rule_with_traceable_evidence() -> None:
    result = run(customer(accounts=[account(balance="15000.00")]))
    outcome = next(o for o in result.outcomes if o.rule_id == "EMERGENCY_FUND_BUILD")
    assert outcome.priority == "high"  # 15000 / 23000 = 0.7 months < 1
    assert outcome.evidence["inputs"]["liquid_balance"] == "15000.00"
    assert outcome.evidence["calculations"]["coverage_months"] == "15000.00 / 23000.00 = 0.7"
    # capacity 33000 -> 50% pool 16500; gap 54000 / 12 = 4500 -> suggestion 4500
    assert outcome.facts["suggested_monthly"] == Decimal("4500.00")
    assert outcome.facts["suggested_monthly"] <= Decimal("33000.00") / 2


def test_no_savings_amount_when_capacity_is_zero() -> None:
    rows = monthly_history(income="27000.00")  # income equals expenses -> no spare capacity
    result = run(customer(rows, accounts=[account(balance="5000.00")]))
    outcome = next(o for o in result.outcomes if o.rule_id == "EMERGENCY_FUND_BUILD")
    assert outcome.facts["suggested_monthly"] is None
    assert "No amount suggested" in outcome.evidence["calculations"]["suggested_monthly"]


def test_goal_rule_and_celebration() -> None:
    goals = [goal("behind", monthly="1000.00", name="Laptop"), goal("nearly", saved="100000.00", name="Trip")]
    result = run(customer(accounts=[account(balance="200000.00")], goals=goals))
    subjects = {(o.rule_id, o.subject_key) for o in result.outcomes}
    assert ("GOAL_SAVINGS_INCREASE", "goal:behind") in subjects
    assert ("GOAL_PROGRESS_CELEBRATE", "goal:nearly:m75") in subjects


def test_discretionary_spending_rule() -> None:
    rows = monthly_history(dining="16000.00", income="70000.00")
    result = run(customer(rows, accounts=[account(balance="300000.00")]))
    outcome = next(o for o in result.outcomes if o.rule_id == "DISCRETIONARY_SPENDING_REVIEW")
    assert outcome.facts["share_pct"] == Decimal("41.0")  # 16000 / 39000
    assert outcome.facts["illustrative_saving"] == Decimal("1600.00")


def test_upcoming_lumpy_obligation_rule() -> None:
    later = run(customer(accounts=[account(balance="200000.00")], obligations=[obligation(due=date(2026, 11, 15))]))
    outcome = next(o for o in later.outcomes if o.rule_id == "UPCOMING_OBLIGATIONS_PREPARE")
    assert outcome.priority == "low"  # 22 days away, affordable
    assert outcome.evidence["inputs"]["obligations"][0]["due_date"] == "2026-11-15"
    soon = run(customer(accounts=[account(balance="200000.00")], obligations=[obligation(due=date(2026, 11, 5))]))
    assert next(o for o in soon.outcomes if o.rule_id == "UPCOMING_OBLIGATIONS_PREPARE").priority == "medium"


def test_obligations_exceeding_balance_are_high_priority() -> None:
    result = run(customer(accounts=[account(balance="20000.00")], obligations=[obligation()]))
    outcome = next(o for o in result.outcomes if o.rule_id == "UPCOMING_OBLIGATIONS_PREPARE")
    assert outcome.priority == "high"


def test_subscription_rule() -> None:
    rows = monthly_history()
    for name, price in (("StreamFlix", "649.00"), ("TuneBox", "119.00"), ("CloudVault", "75.00")):
        rows += [
            txn(date(2026, m, 14), price, "debit", "purchase", "subscriptions", merchant=name) for m in (6, 7, 8, 9, 10)
        ]
    result = run(customer(rows, accounts=[account(balance="200000.00")]))
    outcome = next(o for o in result.outcomes if o.rule_id == "RECURRING_EXPENSES_REVIEW")
    assert outcome.facts["count"] == 3
    assert outcome.facts["monthly_total"] == Decimal("843.00")


def test_cash_flow_rule_for_negative_months() -> None:
    rows = monthly_history()
    rows += [txn(date(2026, m, 20), "40000.00", "debit", "purchase", "travel") for m in (8, 9)]
    result = run(customer(rows, accounts=[account(balance="200000.00")]))
    outcome = next(o for o in result.outcomes if o.rule_id == "CASH_FLOW_CONSISTENCY")
    assert outcome.facts["negative_months"] == ["2026-08", "2026-09"]


def test_low_confidence_suppresses_dependent_rules_and_requests_data() -> None:
    rows = monthly_history(end_month=date(2026, 6, 1), include_current=False)
    result = run(customer(rows, accounts=[account(balance="1000.00")], goals=[goal(monthly="0.00")]))
    assert result.confidence == "low"
    assert rule_ids(result) == {"MISSING_INFO_REQUEST"}
    suppressed = {s.rule_id for s in result.suppressed}
    assert {"EMERGENCY_FUND_BUILD", "GOAL_SAVINGS_INCREASE", "DISCRETIONARY_SPENDING_REVIEW"} <= suppressed
    missing = next(o for o in result.outcomes if o.rule_id == "MISSING_INFO_REQUEST")
    assert "recent_transactions" in missing.facts["gaps"]


def test_missing_income_is_requested_not_assumed_zero() -> None:
    rows = [t for t in monthly_history() if t.transaction_type != "salary"]
    result = run(customer(rows, fin_profile=profile(declared=None)))
    missing = next(o for o in result.outcomes if o.rule_id == "MISSING_INFO_REQUEST")
    assert "monthly_income" in missing.facts["gaps"]


def test_missing_balance_suppresses_emergency_rule_with_reason() -> None:
    result = run(customer(accounts=[account(balance=None)]))
    reasons = {s.rule_id: s.reason for s in result.suppressed}
    assert "EMERGENCY_FUND_BUILD" in reasons
    assert "not reported" in reasons["EMERGENCY_FUND_BUILD"]


def test_consent_withdrawn_produces_nothing() -> None:
    result = run(customer(accounts=[account(balance="1000.00")], consent=False))
    assert result.outcomes == []
    assert len(result.suppressed) == len(RULES)


def test_evaluation_is_reproducible() -> None:
    data = customer(accounts=[account(balance="15000.00")], goals=[goal()], obligations=[obligation()])
    first = [asdict(o) for o in run(data).outcomes]
    second = [asdict(o) for o in run(data).outcomes]
    assert first == second


BANNED = re.compile(
    r"\b(stock|shares|equity fund|mutual fund|crypto|bitcoin|take (out )?a loan|borrow more|personal loan offer|"
    r"buy now|guaranteed return)\b",
    re.IGNORECASE,
)


@pytest.mark.parametrize("seed_index", range(0, 60, 1))
def test_every_synthetic_customer_gets_safe_traceable_recommendations(dataset, seed_index: int) -> None:  # type: ignore[no-untyped-def]
    customer_id = dataset.customer_ids()[seed_index]
    data = customer_financial_data(dataset, customer_id)
    analytics = compute_analytics(data, AS_OF)
    result = evaluate(data, analytics, AS_OF)
    capacity = analytics.savings_capacity.estimated_monthly_capacity
    for outcome in result.outcomes:
        rule = RULES[outcome.rule_id]
        assert outcome.rule_version == rule.version and outcome.category == rule.category
        assert outcome.evidence["inputs"] and outcome.evidence["calculations"]
        assert outcome.priority_reason and outcome.assumptions and outcome.actions
        text = explain(outcome)
        assert text.title and text.explanation and text.reason
        blob = " ".join([text.title, text.explanation, text.reason, *outcome.actions])
        assert not BANNED.search(blob), blob
        assert "None" not in blob, blob  # missing values must never leak into text
        suggested = outcome.facts.get("suggested_monthly") or outcome.facts.get("suggested_increase")
        if suggested is not None:
            assert capacity is not None and suggested <= capacity
    if analytics.data_quality.confidence == "low":
        assert rule_ids(result) <= {"MISSING_INFO_REQUEST", "GOAL_PROGRESS_CELEBRATE"}
