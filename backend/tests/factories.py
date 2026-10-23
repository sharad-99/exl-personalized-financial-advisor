"""Tiny builders for hand-crafted analytics scenarios (no database)."""

from __future__ import annotations

import itertools
from datetime import UTC, date, datetime, time
from decimal import Decimal

from app.models.domain import (
    AccountRecord,
    CustomerFinancialData,
    FinancialProfileRecord,
    GoalRecord,
    ObligationRecord,
    TxnRecord,
)

_counter = itertools.count(1)
AS_OF = date(2026, 10, 24)
SAVINGS = "acc-savings"
CARD = "acc-card"
DEPOSIT = "acc-deposit"


def d(value: str) -> Decimal:
    return Decimal(value)


def txn(
    posted_on: date,
    amount: str,
    direction: str,
    ttype: str,
    category: str,
    *,
    account: str = SAVINGS,
    description: str | None = None,
    merchant: str | None = None,
    group: str | None = None,
    reverses: str | None = None,
    txn_id: str | None = None,
) -> TxnRecord:
    n = next(_counter)
    return TxnRecord(
        id=txn_id or f"t{n}",
        account_id=account,
        external_ref=f"REF{n:06d}",
        posted_on=posted_on,
        amount=Decimal(amount),
        direction=direction,
        transaction_type=ttype,
        category=category,
        description=description or f"POS/{(merchant or category).upper()}/{n}",
        merchant_name=merchant,
        transfer_group_id=group,
        reverses_transaction_id=reverses,
    )


def account(
    account_id: str = SAVINGS,
    account_type: str = "savings",
    balance: str | None = "100000.00",
    opening: str = "0.00",
    as_of: date = AS_OF,
    liquid: bool | None = None,
) -> AccountRecord:
    return AccountRecord(
        id=account_id,
        account_type=account_type,
        nickname=account_type.title(),
        masked_number="XXXX1234",
        opening_balance=Decimal(opening),
        opening_balance_date=date(2025, 9, 1),
        current_balance=Decimal(balance) if balance is not None else None,
        balance_as_of=datetime.combine(as_of, time(12), tzinfo=UTC) if balance is not None else None,
        is_liquid=liquid if liquid is not None else account_type in {"savings", "current"},
    )


def profile(
    income_pattern: str = "salaried_stable",
    declared: str | None = "60000.00",
    dependents: int = 0,
    updated: date = date(2026, 6, 1),
) -> FinancialProfileRecord:
    return FinancialProfileRecord(
        persona_segment="young_salaried",
        income_pattern=income_pattern,
        declared_monthly_income=Decimal(declared) if declared else None,
        age_band="25-34",
        dependents=dependents,
        risk_preference="balanced",
        profile_updated_at=datetime.combine(updated, time(9), tzinfo=UTC),
    )


def goal(
    goal_id: str = "g1",
    target: str = "120000.00",
    saved: str = "20000.00",
    monthly: str | None = "2000.00",
    target_date: date | None = date(2027, 10, 24),
    priority: int = 1,
    status: str = "active",
    name: str = "Emergency Fund",
) -> GoalRecord:
    return GoalRecord(
        id=goal_id,
        name=name,
        goal_type="emergency_fund",
        target_amount=Decimal(target),
        saved_amount=Decimal(saved),
        monthly_contribution=Decimal(monthly) if monthly is not None else None,
        target_date=target_date,
        priority=priority,
        status=status,
    )


def obligation(
    obligation_id: str = "o1",
    amount: str = "24000.00",
    frequency: str = "annual",
    due: date = date(2026, 11, 5),
    name: str = "Insurance Premium",
) -> ObligationRecord:
    return ObligationRecord(
        id=obligation_id,
        obligation_type="insurance_premium",
        name=name,
        amount=Decimal(amount),
        frequency=frequency,
        next_due_date=due,
        end_date=None,
        is_essential=True,
    )


def monthly_history(
    months: int = 6,
    income: str = "60000.00",
    rent: str = "15000.00",
    groceries: str = "8000.00",
    dining: str = "4000.00",
    end_month: date = date(2026, 9, 1),
    include_current: bool = True,
) -> list[TxnRecord]:
    """`months` complete months ending at end_month with salary, rent, groceries, dining,
    plus (optionally) a few transactions in the current partial month so data is fresh."""
    out: list[TxnRecord] = []
    if include_current:
        out += [
            txn(date(2026, 10, 1), income, "credit", "salary", "salary", merchant="Employer"),
            txn(date(2026, 10, 20), "1200.00", "debit", "purchase", "groceries", merchant="FreshMart"),
        ]
    for i in range(months):
        m = end_month.month - i
        y = end_month.year
        while m <= 0:
            m += 12
            y -= 1
        out += [
            txn(date(y, m, 1), income, "credit", "salary", "salary", merchant="Employer"),
            txn(date(y, m, 3), rent, "debit", "bill_payment", "rent", merchant="Landlord"),
            txn(date(y, m, 10), groceries, "debit", "purchase", "groceries", merchant="FreshMart"),
            txn(date(y, m, 15), dining, "debit", "purchase", "dining", merchant="Cafe Aroma"),
        ]
    return out


def customer(
    transactions: list[TxnRecord] | None = None,
    accounts: list[AccountRecord] | None = None,
    goals: list[GoalRecord] | None = None,
    obligations: list[ObligationRecord] | None = None,
    fin_profile: FinancialProfileRecord | None | str = "default",
    consent: bool = True,
) -> CustomerFinancialData:
    return CustomerFinancialData(
        customer_id="cust-1",
        profile=profile() if fin_profile == "default" else fin_profile,  # type: ignore[arg-type]
        accounts=accounts if accounts is not None else [account()],
        transactions=transactions if transactions is not None else monthly_history(),
        goals=goals or [],
        obligations=obligations or [],
        data_sharing_consent=consent,
    )
