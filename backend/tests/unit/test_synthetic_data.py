from collections import Counter
from datetime import date

from app.synthetic_data.generator import PERSONAS, generate_dataset
from app.synthetic_data.reference_data import render_reference_sql
from app.synthetic_data.validation import validate_dataset
from tests.conftest import AS_OF, SEED

REFERENCE_SQL = "../supabase/migrations/20261024000300_reference_data.sql"


def test_dataset_meets_volume_requirements(dataset) -> None:  # type: ignore[no-untyped-def]
    assert len(dataset.customer_ids()) >= 50
    report = validate_dataset(dataset)
    assert report.ok, report.errors[:5]
    assert report.stats["transactions"] > 50 * 12 * 10


def test_dataset_is_reproducible_and_seed_sensitive(dataset) -> None:  # type: ignore[no-untyped-def]
    again = generate_dataset(seed=SEED, as_of=AS_OF)
    assert again.transactions == dataset.transactions
    assert again.accounts == dataset.accounts
    other = generate_dataset(seed=SEED + 1, as_of=AS_OF)
    assert other.transactions != dataset.transactions


def test_persona_coverage(dataset) -> None:  # type: ignore[no-untyped-def]
    segments = Counter(f["persona_segment"] for f in dataset.financial_profiles)
    assert set(segments) == {p.segment for p in PERSONAS}
    patterns = {f["income_pattern"] for f in dataset.financial_profiles}
    assert {"salaried_stable", "irregular"} <= patterns
    assert any(f["declared_monthly_income"] is None for f in dataset.financial_profiles)
    assert any(a["current_balance"] is None for a in dataset.accounts)
    assert any(o["obligation_type"] == "loan_emi" for o in dataset.obligations)
    types = Counter(t["transaction_type"] for t in dataset.transactions)
    assert types["refund"] and types["reversal"] and types["transfer_in"] and types["transfer_out"]
    assert any(str(t["external_ref"]).endswith("-DUP") for t in dataset.transactions)


def test_at_least_twelve_months_for_established_customers(dataset) -> None:  # type: ignore[no-untyped-def]
    segments = {f["customer_id"]: f["persona_segment"] for f in dataset.financial_profiles}
    first = {}
    for t in dataset.transactions:
        first[t["customer_id"]] = min(first.get(t["customer_id"], t["posted_on"]), t["posted_on"])
    established = [c for c in dataset.customer_ids() if segments[c] not in {"new_to_bank"}]
    assert all(first[c] <= date(2025, 10, 31) for c in established)


def test_no_real_looking_identifiers(dataset) -> None:  # type: ignore[no-untyped-def]
    assert all(p["email"].endswith("@demo.exl.test") for p in dataset.profiles)
    assert all(p["is_synthetic"] for p in dataset.profiles)


def test_validation_detects_injected_inconsistency(dataset) -> None:  # type: ignore[no-untyped-def]
    broken = generate_dataset(seed=SEED, as_of=AS_OF)
    broken.accounts[0]["current_balance"] += 1
    broken.transactions[0]["description"] = "NEFT/ACCOUNT 123456789012"
    report = validate_dataset(broken)
    assert not report.ok
    assert any("reconcile" in e for e in report.errors)
    assert any("digit run" in e for e in report.errors)


def test_reference_data_migration_matches_code() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / REFERENCE_SQL.removeprefix("../")
    assert path.read_text(encoding="utf-8") == render_reference_sql(), (
        "Regenerate with: python -m app.synthetic_data.reference_data > " + REFERENCE_SQL
    )


def test_reset_preserves_linked_auth_users(dataset) -> None:  # type: ignore[no-untyped-def]
    import uuid

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.models.tables import Base, Profile
    from app.synthetic_data.seed import seed_database

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    real_auth_id = uuid.uuid4()
    with Session(engine) as session:
        seed_database(session, generate_dataset(seed=SEED, as_of=AS_OF), reset=False)
        profile = session.scalar(select(Profile).where(Profile.email == "customer01@demo.exl.test"))
        profile.auth_user_id = real_auth_id  # as linked to a Supabase user
        session.commit()
        seed_database(session, generate_dataset(seed=SEED, as_of=AS_OF), reset=True)
        relinked = session.scalar(select(Profile).where(Profile.email == "customer01@demo.exl.test"))
        assert relinked.auth_user_id == real_auth_id
