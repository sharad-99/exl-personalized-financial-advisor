"""Framework-free domain records consumed by the analytics and recommendation
services. Keeping services independent of SQLAlchemy/FastAPI makes them pure,
deterministic and easy to unit test."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TxnRecord:
    id: str
    account_id: str
    external_ref: str
    posted_on: date
    amount: Decimal  # always positive; direction carries the sign
    direction: str  # credit | debit
    transaction_type: str
    category: str
    description: str
    merchant_name: str | None = None
    transfer_group_id: str | None = None
    reverses_transaction_id: str | None = None

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.direction == "credit" else -self.amount


@dataclass(frozen=True, slots=True)
class AccountRecord:
    id: str
    account_type: str
    nickname: str
    masked_number: str
    opening_balance: Decimal
    opening_balance_date: date
    current_balance: Decimal | None
    balance_as_of: datetime | None
    is_liquid: bool
    status: str = "active"


@dataclass(frozen=True, slots=True)
class GoalRecord:
    id: str
    name: str
    goal_type: str
    target_amount: Decimal
    saved_amount: Decimal
    monthly_contribution: Decimal | None
    target_date: date | None
    priority: int
    status: str


@dataclass(frozen=True, slots=True)
class ObligationRecord:
    id: str
    obligation_type: str
    name: str
    amount: Decimal
    frequency: str
    next_due_date: date
    end_date: date | None
    is_essential: bool
    outstanding_principal: Decimal | None = None
    interest_rate_apr: Decimal | None = None
    status: str = "active"


@dataclass(frozen=True, slots=True)
class FinancialProfileRecord:
    persona_segment: str
    income_pattern: str
    declared_monthly_income: Decimal | None
    age_band: str | None
    dependents: int | None
    risk_preference: str
    profile_updated_at: datetime


@dataclass(frozen=True, slots=True)
class CustomerFinancialData:
    customer_id: str
    profile: FinancialProfileRecord | None
    accounts: list[AccountRecord] = field(default_factory=list)
    transactions: list[TxnRecord] = field(default_factory=list)
    goals: list[GoalRecord] = field(default_factory=list)
    obligations: list[ObligationRecord] = field(default_factory=list)
    data_sharing_consent: bool = True
