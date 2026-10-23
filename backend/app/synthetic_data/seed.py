"""Seed a database with reproducible SYNTHETIC data.

    python -m app.synthetic_data.seed --seed 42 --as-of 2026-10-24 --reset

* SQLite: the schema is created from the ORM models.
* PostgreSQL/Supabase: apply supabase/migrations first (python -m app.db.migrate).
* --reset deletes only rows belonging to synthetic profiles (is_synthetic = true).
  It refuses to run when ENVIRONMENT=production unless --allow-production is given.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.connection import get_engine
from app.models.tables import (
    Account,
    Base,
    CustomerFinancialProfile,
    DataQualityEvent,
    FinancialGoal,
    FinancialObligation,
    FinancialProduct,
    Profile,
    Transaction,
)
from app.services.financial_analytics import compute_analytics
from app.services.recommendation_service import ensure_rules
from app.synthetic_data.generator import SyntheticDataset, customer_financial_data, generate_dataset
from app.synthetic_data.reference_data import FINANCIAL_PRODUCTS
from app.utils.dates import utc_today


def _chunks(rows: list[dict], size: int = 2000):  # type: ignore[no-untyped-def]
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def seed_reference_data(session: Session) -> None:
    ensure_rules(session)
    existing = set(session.scalars(select(FinancialProduct.code)))
    for product in FINANCIAL_PRODUCTS:
        if product["code"] not in existing:
            session.add(FinancialProduct(**product))
    session.flush()


def reset_synthetic(session: Session) -> int:
    ids = list(session.scalars(select(Profile.id).where(Profile.is_synthetic.is_(True))))
    if ids:
        # Children cascade via foreign keys; delete explicitly in dependency order for clarity.
        for model in (
            Transaction,
            Account,
            FinancialGoal,
            FinancialObligation,
            DataQualityEvent,
            CustomerFinancialProfile,
        ):
            session.execute(delete(model).where(model.customer_id.in_(ids)))
        session.execute(delete(Profile).where(Profile.id.in_(ids)))
    session.flush()
    return len(ids)


def persist_quality_events(session: Session, dataset: SyntheticDataset) -> int:
    """Record data-quality findings per customer so they are visible to analysts."""
    count = 0
    for customer_id in dataset.customer_ids():
        analytics = compute_analytics(customer_financial_data(dataset, customer_id), dataset.as_of)
        for issue in analytics.data_quality.issues:
            session.add(
                DataQualityEvent(
                    customer_id=customer_id,
                    check_code=issue.code,
                    severity=issue.severity,
                    entity_type="customer",
                    entity_id=str(customer_id),
                    details={"message": issue.message, "count": issue.count, "as_of": dataset.as_of.isoformat()},
                )
            )
            count += 1
    return count


def seed_database(session: Session, dataset: SyntheticDataset, reset: bool = True) -> dict[str, int]:
    # Preserve links to real Supabase Auth users (set manually per docs/deployment.md) across a reset.
    links = {
        email: auth_id
        for email, auth_id in session.execute(
            select(Profile.email, Profile.auth_user_id).where(Profile.is_synthetic.is_(True))
        )
        if email and auth_id
    }
    removed = reset_synthetic(session) if reset else 0
    for row in dataset.profiles:
        if row["email"] in links:
            row["auth_user_id"] = links[row["email"]]
    seed_reference_data(session)
    session.execute(insert(Profile), dataset.profiles)
    session.execute(insert(CustomerFinancialProfile), dataset.financial_profiles)
    session.execute(insert(Account), dataset.accounts)
    # Insert originals before reversals so the self-referencing FK is always satisfied.
    originals = [t for t in dataset.transactions if t["reverses_transaction_id"] is None]
    reversals = [t for t in dataset.transactions if t["reverses_transaction_id"] is not None]
    for chunk in _chunks(originals):
        session.execute(insert(Transaction), chunk)
    if reversals:
        session.execute(insert(Transaction), reversals)
    if dataset.goals:
        session.execute(insert(FinancialGoal), dataset.goals)
    if dataset.obligations:
        session.execute(insert(FinancialObligation), dataset.obligations)
    quality_events = persist_quality_events(session, dataset)
    session.commit()
    return {
        "removed_profiles": removed,
        "profiles": len(dataset.profiles),
        "accounts": len(dataset.accounts),
        "transactions": len(dataset.transactions),
        "goals": len(dataset.goals),
        "obligations": len(dataset.obligations),
        "data_quality_events": quality_events,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--as-of", type=date.fromisoformat, default=None, help="Reference date for the data (default: today, UTC)"
    )
    parser.add_argument("--customers", type=int, default=None, help="Number of customers (default 60, min 50)")
    parser.add_argument("--history-months", type=int, default=13)
    parser.add_argument("--reset", action="store_true", help="Delete existing synthetic rows first")
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    if settings.environment == "production" and not args.allow_production:
        print(
            "Refusing to seed: ENVIRONMENT=production. Pass --allow-production to seed a deployed demo "
            "database with SYNTHETIC data.",
            file=sys.stderr,
        )
        return 2
    if args.customers is not None and args.customers < 50:
        parser.error("--customers must be at least 50")

    engine = get_engine()
    if settings.is_sqlite:
        Base.metadata.create_all(engine)
    dataset = generate_dataset(
        seed=args.seed,
        as_of=args.as_of or utc_today(),
        history_months=args.history_months,
        customer_count=args.customers,
    )
    with Session(engine) as session:
        if not args.reset and session.scalar(select(Profile.id).where(Profile.is_synthetic.is_(True)).limit(1)):
            print("Synthetic data already present; re-run with --reset to replace it.", file=sys.stderr)
            return 1
        counts = seed_database(session, dataset, reset=args.reset)
    print(f"Seeded SYNTHETIC dataset (seed={args.seed}, as_of={dataset.as_of}): {counts}")
    advisor = next(p for p in dataset.profiles if p["role"] == "advisor")
    first = next(p for p in dataset.profiles if p["role"] == "customer")
    print(
        f"Demo logins (local auth mode): {advisor['email']} (advisor), {first['email']} (customer). "
        "Password = LOCAL_DEMO_PASSWORD from backend/.env"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
