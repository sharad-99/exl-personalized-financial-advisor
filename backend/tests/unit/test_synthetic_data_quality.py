"""Synthetic-data milestone: exact reproducibility, scenario coverage, validator checks and
database constraints that do not need PostgreSQL (SQLite with foreign keys on)."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.tables import Base, Transaction
from app.services.financial_analytics import compute_analytics
from app.synthetic_data.generator import customer_financial_data, generate_dataset
from app.synthetic_data.seed import seed_database
from app.synthetic_data.validation import validate_dataset
from tests.conftest import AS_OF, SEED

TABLES = ("profiles", "financial_profiles", "accounts", "transactions", "goals", "obligations")

# Golden values for seed=42, as_of=2026-10-24. If the generator changes on purpose, update these
# together with docs/synthetic-data.md; an unexpected change means reproducibility broke.
GOLDEN_COUNTS = {
    "profiles": 61,
    "financial_profiles": 60,
    "accounts": 119,
    "transactions": 22872,
    "goals": 85,
    "obligations": 146,
}
GOLDEN_SHA256 = "de068c7cd2937dd9f08a862875b1564ea77823c36e328071ce5315485cf97763"


def fingerprint(ds) -> str:  # type: ignore[no-untyped-def]
    payload = [getattr(ds, t) for t in TABLES]
    return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()


def test_exact_record_counts_and_fingerprint(dataset) -> None:  # type: ignore[no-untyped-def]
    assert {t: len(getattr(dataset, t)) for t in TABLES} == GOLDEN_COUNTS
    assert fingerprint(dataset) == GOLDEN_SHA256


def test_as_of_shifts_dates_but_keeps_shape() -> None:
    later = generate_dataset(seed=SEED, as_of=date(2027, 1, 15))
    assert len(later.customer_ids()) == 60
    assert max(t["posted_on"] for t in later.transactions) <= date(2027, 1, 15)
    assert validate_dataset(later).ok


def test_customer_count_scales_and_stays_valid() -> None:
    bigger = generate_dataset(seed=SEED, as_of=AS_OF, customer_count=75)
    assert len(bigger.customer_ids()) == 75
    assert validate_dataset(bigger).ok
    with pytest.raises(ValueError):
        generate_dataset(seed=SEED, as_of=AS_OF, history_months=6)


def test_validator_classification_stats(dataset) -> None:  # type: ignore[no-untyped-def]
    report = validate_dataset(dataset)
    injected = sum(1 for t in dataset.transactions if str(t["external_ref"]).endswith("-DUP"))
    assert report.ok, report.errors[:5]
    assert report.stats["duplicates_detected"] == injected == 20
    assert report.stats["internal_transfer_legs"] % 2 == 0 and report.stats["internal_transfer_legs"] > 0
    assert report.stats["reversal_pairs"] > 0 and report.stats["refund_txns"] > 0
    assert report.stats["uncategorized_after_rules"] == 0
    assert report.stats["income_txns"] > 0 and report.stats["expense_txns"] > 0


def test_scenario_coverage(dataset) -> None:  # type: ignore[no-untyped-def]
    fins = {f["customer_id"]: f for f in dataset.financial_profiles}
    by_customer: dict[uuid.UUID, list[dict]] = {}
    for t in dataset.transactions:
        by_customer.setdefault(t["customer_id"], []).append(t)

    # Recurring bills: a fixed broadband bill every month for established customers.
    broadband = [t for t in dataset.transactions if t["merchant_name"] == "FiberNet Broadband"]
    assert len({t["customer_id"] for t in broadband}) == 60
    # Debt obligations with principal and APR.
    loans = [o for o in dataset.obligations if o["obligation_type"] == "loan_emi"]
    assert loans and all(o["outstanding_principal"] and o["interest_rate_apr"] for o in loans)
    # Irregular income has several credits per month from different payers.
    gig = [c for c, f in fins.items() if f["income_pattern"] == "irregular"]
    assert len(gig) == 7
    # Income paid elsewhere: no declared income AND no income credits at all.
    no_income = [c for c, f in fins.items() if f["declared_monthly_income"] is None]
    assert len(no_income) == 4
    income_types = {"salary", "business_income", "pension", "interest", "other_income"}
    for customer_id in no_income:
        assert not any(t["transaction_type"] in income_types for t in by_customer[customer_id])
        analytics = compute_analytics(customer_financial_data(dataset, customer_id), AS_OF)
        assert analytics.monthly_averages.income is None  # unknown, never a silent zero
        assert "missing_income" in {i.code for i in analytics.data_quality.issues}
        assert analytics.data_quality.confidence == "low"
    # Goals in several states.
    assert {g["status"] for g in dataset.goals} >= {"active", "achieved"}


def test_savings_profiles_are_varied(dataset) -> None:  # type: ignore[no-untyped-def]
    statuses = set()
    for customer_id in dataset.customer_ids():
        statuses.add(compute_analytics(customer_financial_data(dataset, customer_id), AS_OF).emergency_fund.status)
    assert statuses == {"insufficient", "building", "sufficient", "unknown"}


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda ds: ds.transactions[0].update(category="salary", transaction_type="purchase"), "category"),
        (
            lambda ds: next(t for t in ds.transactions if t["transaction_type"] == "transfer_in").update(
                amount=Decimal("1.00")
            ),
            "unbalanced",
        ),
        (
            lambda ds: next(t for t in ds.transactions if t["transaction_type"] == "salary").update(external_ref="X"),
            None,
        ),  # harmless on its own (unique per account)
        (
            lambda ds: ds.transactions.append(dict(ds.transactions[5], id=uuid.uuid4(), external_ref="EXTRA-1")),
            "Duplicate detection mismatch",
        ),
        (lambda ds: ds.goals[0].update(saved_amount=ds.goals[0]["target_amount"] + 1, status="active"), "saved more"),
        (lambda ds: ds.accounts[0].update(masked_number="1234567890"), "masked number"),
    ],
)
def test_validator_flags_inconsistencies(dataset, mutate, expected) -> None:  # type: ignore[no-untyped-def]
    broken = copy.deepcopy(dataset)
    mutate(broken)
    report = validate_dataset(broken)
    if expected is None:
        return
    assert not report.ok
    assert any(expected in e for e in report.errors), report.errors[:5]


@pytest.fixture()
def seeded_sqlite(dataset):  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        counts = seed_database(session, dataset, reset=False)
    yield engine, counts
    engine.dispose()


def test_seed_loads_every_record(seeded_sqlite, dataset) -> None:  # type: ignore[no-untyped-def]
    _, counts = seeded_sqlite
    assert counts["transactions"] == len(dataset.transactions)
    assert counts["profiles"] == len(dataset.profiles)
    assert counts["data_quality_events"] > 0


def _txn(dataset, **overrides):  # type: ignore[no-untyped-def]
    base = dict(dataset.transactions[0])
    base.update(id=uuid.uuid4(), external_ref=f"T-{uuid.uuid4().hex[:8]}", reverses_transaction_id=None)
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "overrides",
    [
        {"external_ref": None},  # filled below with an existing ref -> duplicate import
        {"amount": Decimal("0.00")},  # amount must be positive
        {"amount": Decimal("-5.00")},
        {"direction": "sideways"},
        {"account_id": uuid.uuid4()},  # unknown account
        {"customer_id": "OTHER"},  # account owned by a different customer
    ],
)
def test_database_constraints(seeded_sqlite, dataset, overrides) -> None:  # type: ignore[no-untyped-def]
    engine, _ = seeded_sqlite
    if overrides.get("external_ref", "") is None:
        overrides = {"external_ref": dataset.transactions[0]["external_ref"]}
    if overrides.get("customer_id") == "OTHER":
        owner = dataset.transactions[0]["customer_id"]
        overrides = {"customer_id": next(c for c in dataset.customer_ids() if c != owner)}
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.execute(insert(Transaction), [_txn(dataset, **overrides)])
        session.commit()
