"""Data quality and freshness checks.

These checks feed (a) the confidence indicator attached to analytics and
recommendations and (b) the data_quality_events table via the validation
script. Thresholds are explicit constants so they can be documented and tested.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from app.models.domain import CustomerFinancialData
from app.services.spending_categorization import ClassifiedTxn

FRESH_DAYS = 10
AGING_DAYS = 35
BALANCE_STALE_DAYS = 7
PROFILE_STALE_DAYS = 365
MIN_HISTORY_MONTHS_FOR_TRENDS = 3
FULL_HISTORY_MONTHS = 6
UNCATEGORIZED_SHARE_WARNING = Decimal("0.10")

Severity = Literal["info", "warning", "error"]
Freshness = Literal["fresh", "aging", "stale", "no_data"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class QualityIssue:
    code: str
    severity: Severity
    message: str
    count: int = 1


@dataclass(frozen=True)
class DataQualityReport:
    latest_transaction_date: date | None
    days_since_last_transaction: int | None
    freshness: Freshness
    history_months: int
    profile_age_days: int | None
    balance_status: Literal["fresh", "stale", "missing"]
    issues: list[QualityIssue] = field(default_factory=list)
    confidence: Confidence = "low"
    confidence_reasons: list[str] = field(default_factory=list)


def freshness_for(days: int | None) -> Freshness:
    if days is None:
        return "no_data"
    if days <= FRESH_DAYS:
        return "fresh"
    if days <= AGING_DAYS:
        return "aging"
    return "stale"


def assess_data_quality(
    data: CustomerFinancialData, classified: list[ClassifiedTxn], as_of: date, history_months: int
) -> DataQualityReport:
    issues: list[QualityIssue] = []
    txns = [c.txn for c in classified if c.txn.posted_on <= as_of]
    latest = max((t.posted_on for t in txns), default=None)
    days_since = (as_of - latest).days if latest else None
    freshness = freshness_for(days_since)

    future = [c for c in classified if c.txn.posted_on > as_of]
    if future:
        issues.append(
            QualityIssue(
                "future_dated_transaction",
                "error",
                "Transactions dated after the evaluation date were ignored.",
                len(future),
            )
        )

    reasons = Counter(c.exclusion_reason for c in classified if c.exclusion_reason)
    if reasons["probable_duplicate"]:
        issues.append(
            QualityIssue(
                "probable_duplicate",
                "warning",
                "Probable duplicate imports were excluded from totals.",
                reasons["probable_duplicate"],
            )
        )
    if reasons["orphan_reversal"]:
        issues.append(
            QualityIssue(
                "orphan_reversal",
                "warning",
                "Reversals without a matching original transaction were excluded.",
                reasons["orphan_reversal"],
            )
        )
    if reasons["unmatched_transfer"]:
        issues.append(
            QualityIssue(
                "unmatched_transfer",
                "warning",
                "Transfers without a matching counterpart leg were excluded from income and expenses.",
                reasons["unmatched_transfer"],
            )
        )

    spend = [c for c in classified if c.flow == "expense"]
    uncategorized = [c for c in spend if c.category == "uncategorized"]
    if spend and Decimal(len(uncategorized)) / Decimal(len(spend)) > UNCATEGORIZED_SHARE_WARNING:
        issues.append(
            QualityIssue(
                "high_uncategorized_share",
                "warning",
                "More than 10% of expenses could not be categorised.",
                len(uncategorized),
            )
        )
    elif uncategorized:
        issues.append(
            QualityIssue(
                "uncategorized_transactions", "info", "Some expenses could not be categorised.", len(uncategorized)
            )
        )

    if freshness == "no_data":
        issues.append(QualityIssue("no_transactions", "error", "No transactions are available."))
    elif freshness == "stale":
        issues.append(
            QualityIssue("stale_transactions", "warning", f"The latest transaction is {days_since} days old.")
        )

    if history_months < MIN_HISTORY_MONTHS_FOR_TRENDS:
        issues.append(
            QualityIssue(
                "short_history", "warning", f"Only {history_months} month(s) of transaction history are available."
            )
        )

    liquid = [a for a in data.accounts if a.is_liquid and a.status == "active"]
    balance_status: Literal["fresh", "stale", "missing"] = "fresh"
    if not liquid or any(a.current_balance is None for a in liquid):
        balance_status = "missing"
        issues.append(
            QualityIssue("missing_balance", "warning", "One or more liquid account balances are not reported.")
        )
    elif any(
        a.balance_as_of is not None and (as_of - a.balance_as_of.date()).days > BALANCE_STALE_DAYS for a in liquid
    ):
        balance_status = "stale"
        issues.append(
            QualityIssue("stale_balance", "warning", f"A reported balance is older than {BALANCE_STALE_DAYS} days.")
        )

    profile_age = None
    if data.profile is None:
        issues.append(QualityIssue("missing_profile", "warning", "The customer financial profile is missing."))
    else:
        profile_age = (as_of - data.profile.profile_updated_at.date()).days
        if profile_age > PROFILE_STALE_DAYS:
            issues.append(
                QualityIssue("stale_profile", "info", "Profile details have not been confirmed in over a year.")
            )
        has_income_txn = any(c.flow == "income" for c in classified)
        if data.profile.declared_monthly_income is None and not has_income_txn:
            issues.append(
                QualityIssue("missing_income", "error", "No declared income and no income transactions were found.")
            )

    confidence, confidence_reasons = _confidence(freshness, history_months, balance_status, issues)
    return DataQualityReport(
        latest_transaction_date=latest,
        days_since_last_transaction=days_since,
        freshness=freshness,
        history_months=history_months,
        profile_age_days=profile_age,
        balance_status=balance_status,
        issues=issues,
        confidence=confidence,
        confidence_reasons=confidence_reasons,
    )


def _confidence(
    freshness: Freshness, history_months: int, balance_status: str, issues: list[QualityIssue]
) -> tuple[Confidence, list[str]]:
    low: list[str] = []
    medium: list[str] = []
    codes = {i.code for i in issues}
    if freshness in {"stale", "no_data"}:
        low.append("Transaction data is stale or missing.")
    if history_months < MIN_HISTORY_MONTHS_FOR_TRENDS:
        low.append(f"Fewer than {MIN_HISTORY_MONTHS_FOR_TRENDS} months of history.")
    if "missing_income" in codes:
        low.append("Income cannot be determined.")
    if freshness == "aging":
        medium.append("Latest transactions are more than 10 days old.")
    if MIN_HISTORY_MONTHS_FOR_TRENDS <= history_months < FULL_HISTORY_MONTHS:
        medium.append(f"Fewer than {FULL_HISTORY_MONTHS} months of history.")
    if balance_status != "fresh":
        medium.append(f"Liquid account balance is {balance_status}.")
    if "high_uncategorized_share" in codes:
        medium.append("Many expenses are uncategorised.")
    if "stale_profile" in codes:
        medium.append("Profile details may be out of date.")
    if low:
        return "low", low + medium
    if medium:
        return "medium", medium
    return "high", ["Recent, complete transaction history and fresh balances."]
