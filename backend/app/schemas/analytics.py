"""Analytics response models. Money is Decimal, serialised as a JSON string
(e.g. "12345.67") so no precision is lost on the wire."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PeriodInfo(_Model):
    start_date: date
    end_date: date
    as_of: date
    months_in_period: int
    months_with_data: int


class CashFlowTotals(_Model):
    total_income: Decimal
    total_expenses: Decimal
    refunds_netted: Decimal
    net_observed_cash_flow: Decimal
    excluded_internal_transfers: Decimal
    excluded_duplicates: Decimal
    excluded_reversal_pairs: int
    note: str = (
        "Net observed cash flow is income minus expenses seen in the period. It is not a guarantee of "
        "disposable income."
    )


class MonthlyAverages(_Model):
    income: Decimal | None
    expenses: Decimal | None
    essential_expenses: Decimal | None
    discretionary_expenses: Decimal | None
    net_observed_cash_flow: Decimal | None
    basis_months: int


class SavingsRate(_Model):
    value_pct: Decimal | None
    status: Literal["calculated", "insufficient_data", "no_income"]
    formula: str = "(total income - total expenses) / total income x 100, over months with data"
    reason: str | None = None


class CategorySpend(_Model):
    category: str
    group: str
    amount: Decimal
    share_pct: Decimal | None
    transaction_count: int


class MonthlyTrendPoint(_Model):
    month: str
    income: Decimal
    expenses: Decimal
    essential_expenses: Decimal
    discretionary_expenses: Decimal
    net_observed_cash_flow: Decimal
    has_data: bool
    is_partial: bool


class MonthOverMonth(_Model):
    month: str
    expenses: Decimal
    previous_expenses: Decimal | None
    change_amount: Decimal | None
    change_pct: Decimal | None


class RecurringExpense(_Model):
    merchant: str
    category: str
    average_amount: Decimal
    occurrences: int
    months_observed: int
    last_date: date
    next_expected_date: date
    is_subscription: bool
    amount_variation_pct: Decimal


class IncomeStability(_Model):
    months_with_income: int
    coefficient_of_variation: Decimal | None
    pattern: Literal["stable", "variable", "insufficient_data"]
    declared_monthly_income: Decimal | None


class AccountBalance(_Model):
    account_id: str
    nickname: str
    account_type: str
    masked_number: str
    is_liquid: bool
    reported_balance: Decimal | None
    balance_as_of: datetime | None
    balance_is_stale: bool | None
    estimated_balance_from_transactions: Decimal
    reconciliation_difference: Decimal | None


class BalanceSummary(_Model):
    reported_liquid_balance: Decimal | None
    liquid_balance_status: Literal["fresh", "stale", "missing"]
    credit_card_outstanding: Decimal | None
    accounts: list[AccountBalance]
    note: str = (
        "Reported balances come from account records. Estimated balances are reconstructed from "
        "transactions and may differ."
    )


class EmergencyFund(_Model):
    liquid_balance: Decimal | None
    average_monthly_essential_expenses: Decimal | None
    coverage_months: Decimal | None
    target_months: int
    target_amount: Decimal | None
    gap_amount: Decimal | None
    status: Literal["sufficient", "building", "insufficient", "unknown"]
    reason: str | None
    assumptions: list[str]


class SavingsCapacity(_Model):
    average_monthly_net_cash_flow: Decimal | None
    recent_3_month_net_cash_flow: Decimal | None
    non_monthly_obligation_provision: Decimal
    estimated_monthly_capacity: Decimal | None
    observed_monthly_transfers_to_savings: Decimal | None
    reason: str | None
    calculation: dict[str, str]


class UpcomingObligation(_Model):
    obligation_id: str
    name: str
    obligation_type: str
    amount: Decimal
    frequency: str
    due_date: date
    days_until_due: int
    is_essential: bool


class UpcomingObligations(_Model):
    horizon_days: int
    items: list[UpcomingObligation]
    total_due: Decimal


class GoalProgress(_Model):
    goal_id: str
    name: str
    goal_type: str
    priority: int
    goal_status: str
    target_amount: Decimal
    saved_amount: Decimal
    remaining_amount: Decimal
    progress_pct: Decimal
    target_date: date | None
    months_remaining: int | None
    required_monthly: Decimal | None
    planned_monthly: Decimal | None
    plan_status: str
    projected_completion: date | None
    suggested_increase: Decimal | None
    suggested_target_date: date | None
    guidance: str
    calculation: dict[str, str]
    assumptions: list[str]


class QualityIssueOut(_Model):
    code: str
    severity: str
    message: str
    count: int


class DataQualityOut(_Model):
    latest_transaction_date: date | None
    days_since_last_transaction: int | None
    freshness: Literal["fresh", "aging", "stale", "no_data"]
    history_months: int
    profile_age_days: int | None
    balance_status: Literal["fresh", "stale", "missing"]
    issues: list[QualityIssueOut]
    confidence: Literal["high", "medium", "low"]
    confidence_reasons: list[str]


class AnalyticsResult(_Model):
    customer_id: str
    currency: str = "INR"
    is_synthetic_data: bool = True
    period: PeriodInfo
    totals: CashFlowTotals
    monthly_averages: MonthlyAverages
    savings_rate: SavingsRate
    spending_by_category: list[CategorySpend]
    monthly_trend: list[MonthlyTrendPoint]
    month_over_month: list[MonthOverMonth]
    recurring_expenses: list[RecurringExpense]
    income_stability: IncomeStability
    balances: BalanceSummary
    emergency_fund: EmergencyFund
    savings_capacity: SavingsCapacity
    upcoming_obligations: UpcomingObligations
    goals: list[GoalProgress]
    data_quality: DataQualityOut
