"""Data access for customers and their financial records.

Every function that returns customer data takes the customer_id explicitly;
authorisation is decided before these are called (see app/api/deps.py).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.domain import (
    AccountRecord,
    CustomerFinancialData,
    FinancialProfileRecord,
    GoalRecord,
    ObligationRecord,
    TxnRecord,
)
from app.models.tables import (
    Account,
    CustomerFinancialProfile,
    FinancialGoal,
    FinancialObligation,
    Profile,
    Transaction,
)


def get_profile(session: Session, profile_id: uuid.UUID) -> Profile | None:
    return session.get(Profile, profile_id)


def get_profile_by_auth_user(session: Session, auth_user_id: uuid.UUID) -> Profile | None:
    return session.scalar(select(Profile).where(Profile.auth_user_id == auth_user_id))


def get_profile_by_email(session: Session, email: str) -> Profile | None:
    return session.scalar(select(Profile).where(Profile.email == email.lower()))


def get_customer(session: Session, customer_id: uuid.UUID) -> Profile | None:
    return session.scalar(select(Profile).where(Profile.id == customer_id, Profile.role == "customer"))


def list_customers(
    session: Session,
    *,
    restrict_to: uuid.UUID | None,
    search: str | None,
    segment: str | None,
    offset: int,
    limit: int,
) -> tuple[list[Profile], int]:
    query: Select[tuple[Profile]] = select(Profile).where(Profile.role == "customer")
    if restrict_to is not None:
        query = query.where(Profile.id == restrict_to)
    if search:
        pattern = f"%{search.lower()}%"  # bound parameter, never interpolated into SQL
        query = query.where(
            or_(func.lower(Profile.display_name).like(pattern), func.lower(Profile.email).like(pattern))
        )
    if segment:
        query = query.join(CustomerFinancialProfile).where(CustomerFinancialProfile.persona_segment == segment)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(query.order_by(Profile.display_name, Profile.id).offset(offset).limit(limit)).unique().all()
    return list(rows), int(total)


def list_accounts(session: Session, customer_id: uuid.UUID) -> list[Account]:
    return list(
        session.scalars(
            select(Account)
            .where(Account.customer_id == customer_id)
            .order_by(Account.account_type, Account.masked_number)
        )
    )


def list_obligations(session: Session, customer_id: uuid.UUID) -> list[FinancialObligation]:
    return list(
        session.scalars(
            select(FinancialObligation)
            .where(FinancialObligation.customer_id == customer_id)
            .order_by(FinancialObligation.next_due_date, FinancialObligation.name)
        )
    )


def list_goals(session: Session, customer_id: uuid.UUID, include_cancelled: bool = False) -> list[FinancialGoal]:
    query = select(FinancialGoal).where(FinancialGoal.customer_id == customer_id)
    if not include_cancelled:
        query = query.where(FinancialGoal.status != "cancelled")
    return list(session.scalars(query.order_by(FinancialGoal.priority, FinancialGoal.created_at, FinancialGoal.name)))


def get_goal(session: Session, customer_id: uuid.UUID, goal_id: uuid.UUID) -> FinancialGoal | None:
    return session.scalar(
        select(FinancialGoal).where(FinancialGoal.id == goal_id, FinancialGoal.customer_id == customer_id)
    )


def query_transactions(
    session: Session,
    customer_id: uuid.UUID,
    *,
    start: date | None,
    end: date | None,
    category: str | None,
    direction: str | None,
    account_id: uuid.UUID | None,
    offset: int,
    limit: int,
) -> tuple[list[Transaction], int]:
    query = select(Transaction).where(Transaction.customer_id == customer_id)
    if start:
        query = query.where(Transaction.posted_on >= start)
    if end:
        query = query.where(Transaction.posted_on <= end)
    if category:
        query = query.where(Transaction.category == category)
    if direction:
        query = query.where(Transaction.direction == direction)
    if account_id:
        query = query.where(Transaction.account_id == account_id)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(Transaction.posted_on.desc(), Transaction.external_ref.desc()).offset(offset).limit(limit)
    ).all()
    return list(rows), int(total)


def transaction_summary(session: Session, customer_id: uuid.UUID) -> tuple[int, date | None, date | None]:
    row = session.execute(
        select(func.count(Transaction.id), func.min(Transaction.posted_on), func.max(Transaction.posted_on)).where(
            Transaction.customer_id == customer_id
        )
    ).one()
    return int(row[0]), row[1], row[2]


def load_financial_data(session: Session, customer: Profile) -> CustomerFinancialData:
    """Load everything the analytics engine needs for one customer."""
    fin = customer.financial_profile
    accounts = list_accounts(session, customer.id)
    txns = session.scalars(select(Transaction).where(Transaction.customer_id == customer.id)).all()
    return CustomerFinancialData(
        customer_id=str(customer.id),
        profile=FinancialProfileRecord(
            persona_segment=fin.persona_segment,
            income_pattern=fin.income_pattern,
            declared_monthly_income=fin.declared_monthly_income,
            age_band=fin.age_band,
            dependents=fin.dependents,
            risk_preference=fin.risk_preference,
            profile_updated_at=fin.profile_updated_at,
        )
        if fin
        else None,
        accounts=[
            AccountRecord(
                id=str(a.id),
                account_type=a.account_type,
                nickname=a.nickname,
                masked_number=a.masked_number,
                opening_balance=a.opening_balance,
                opening_balance_date=a.opening_balance_date,
                current_balance=a.current_balance,
                balance_as_of=a.balance_as_of,
                is_liquid=a.is_liquid,
                status=a.status,
            )
            for a in accounts
        ],
        transactions=[
            TxnRecord(
                id=str(t.id),
                account_id=str(t.account_id),
                external_ref=t.external_ref,
                posted_on=t.posted_on,
                amount=t.amount,
                direction=t.direction,
                transaction_type=t.transaction_type,
                category=t.category,
                description=t.description,
                merchant_name=t.merchant_name,
                transfer_group_id=str(t.transfer_group_id) if t.transfer_group_id else None,
                reverses_transaction_id=str(t.reverses_transaction_id) if t.reverses_transaction_id else None,
            )
            for t in txns
        ],
        goals=[
            GoalRecord(
                id=str(g.id),
                name=g.name,
                goal_type=g.goal_type,
                target_amount=g.target_amount,
                saved_amount=g.saved_amount,
                monthly_contribution=g.monthly_contribution,
                target_date=g.target_date,
                priority=g.priority,
                status=g.status,
            )
            for g in list_goals(session, customer.id)
        ],
        obligations=[
            ObligationRecord(
                id=str(o.id),
                obligation_type=o.obligation_type,
                name=o.name,
                amount=o.amount,
                frequency=o.frequency,
                next_due_date=o.next_due_date,
                end_date=o.end_date,
                is_essential=o.is_essential,
                outstanding_principal=o.outstanding_principal,
                interest_rate_apr=o.interest_rate_apr,
                status=o.status,
            )
            for o in list_obligations(session, customer.id)
        ],
        data_sharing_consent=customer.data_sharing_consent,
    )
