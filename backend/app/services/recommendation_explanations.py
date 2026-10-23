"""Customer-facing explanation text for rule outcomes.

Kept separate from rule logic so wording can change without touching the
decision logic (and vice versa). Every sentence is built from facts computed
by the engine; nothing here invents numbers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.services.recommendation_engine import RuleOutcome
from app.utils.formatting import format_inr, format_pct

GAP_LABELS = {
    "recent_transactions": "recent transactions",
    "longer_transaction_history": "a longer transaction history",
    "monthly_income": "your monthly income",
    "account_balances": "an up-to-date account balance",
    "profile_confirmation": "confirmation of your profile details",
}


@dataclass(frozen=True)
class Explanation:
    title: str
    explanation: str
    reason: str


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _missing_info(f: dict[str, Any]) -> Explanation:
    gaps = [GAP_LABELS[g] for g in f["gaps"]]
    stale = (
        f" Your latest transaction is {f['days_since_last_transaction']} days old."
        if "recent_transactions" in f["gaps"] and f["days_since_last_transaction"] is not None
        else ""
    )
    return Explanation(
        title="Help us personalise your guidance",
        explanation=f"We need {_join(gaps)} before we can give reliable guidance on savings and spending.",
        reason=f"Some inputs are missing or out of date.{stale} We do not guess missing figures.",
    )


def _emergency(f: dict[str, Any]) -> Explanation:
    pace = ""
    if f["suggested_monthly"]:
        pace = (
            f" Setting aside about {format_inr(f['suggested_monthly'])} a month would close the gap in "
            f"roughly {f['months_to_target']} months."
        )
    else:
        pace = " There is no spare monthly capacity right now, so start by reviewing non-essential spending."
    return Explanation(
        title="Build your emergency fund",
        explanation=(
            f"Your liquid savings cover about {f['coverage_months']} months of essential expenses. "
            f"A {f['target_months']}-month cushion helps you handle surprises without borrowing.{pace}"
        ),
        reason=(
            f"Liquid balance {format_inr(f['liquid_balance'])} against average essential spending of "
            f"{format_inr(f['avg_essential'])} a month leaves a gap of {format_inr(f['gap_amount'])}."
        ),
    )


def _goal_savings(f: dict[str, Any]) -> Explanation:
    plan = (
        f"your current plan is {format_inr(f['planned_monthly'])} a month"
        if f["planned_monthly"] is not None
        else "there is no planned monthly contribution yet"
    )
    if f["suggested_target_date"]:
        tail = f" A more realistic target date would be around {f['suggested_target_date']:%B %Y}."
    elif f["suggested_increase"]:
        tail = f" Adding about {format_inr(f['suggested_increase'])} a month would keep it on schedule."
    elif f["capacity_known"]:
        tail = (
            " Your estimated spare monthly capacity is currently nil, so consider a later target date or "
            "reviewing spending first."
        )
    else:
        tail = " We could not estimate a safe extra amount from the available data."
    return Explanation(
        title=f"Get '{f['goal_name']}' back on track",
        explanation=(
            f"To reach this goal by {f['target_date']:%B %Y}, you need about "
            f"{format_inr(f['required_monthly'])} a month for {f['months_remaining']} months.{tail}"
        ),
        reason=f"{format_inr(f['remaining_amount'])} remains, and {plan}.",
    )


def _discretionary(f: dict[str, Any]) -> Explanation:
    top = _join([f"{c.replace('_', ' ')} ({format_inr(a)})" for c, a in f["top_categories"]])
    detail = []
    if f["high_share"]:
        detail.append(f"discretionary items made up {format_pct(f['share_pct'])} of your spending")
    if f["spike"]:
        detail.append(
            f"in {f['latest_month']} they reached {format_inr(f['latest_amount'])}, above your "
            f"recent average of {format_inr(f['trailing_avg'])}"
        )
    return Explanation(
        title="Review your discretionary spending",
        explanation=(
            f"Trimming discretionary spending by 10% would free up about "
            f"{format_inr(f['illustrative_saving'])} a month. Largest areas over the period: {top}."
        ),
        reason="Over the analysis period, " + _join(detail) + ".",
    )


def _upcoming(f: dict[str, Any]) -> Explanation:
    focus = f["lumpy"] or f["items"]
    listed = _join([f"{name} ({format_inr(amount)}, due {due:%d %b})" for name, amount, due in focus[:3]])
    balance = (
        f" Your reported liquid balance is {format_inr(f['liquid_balance'])}."
        if f["liquid_balance"] is not None
        else " Your liquid balance is not reported."
    )
    return Explanation(
        title="Prepare for upcoming payments",
        explanation=f"Coming up in the next 30 days: {listed}. Setting this money aside now avoids a shortfall.",
        reason=(
            f"Known obligations due within 30 days, including routine monthly ones, total "
            f"{format_inr(f['total_due'])}.{balance}"
        ),
    )


def _recurring(f: dict[str, Any]) -> Explanation:
    merchants = _join([f"{m} ({format_inr(a)})" for m, a in f["merchants"][:5]])
    return Explanation(
        title="Review your recurring subscriptions",
        explanation=(
            f"You have {f['count']} recurring subscriptions costing about {format_inr(f['monthly_total'])} "
            f"a month ({format_inr(f['annual_total'])} a year)."
        ),
        reason=f"Detected monthly charges: {merchants}.",
    )


def _cash_flow(f: dict[str, Any]) -> Explanation:
    parts = []
    if f["negative_months"]:
        parts.append(f"spending exceeded income in {_join(f['negative_months'])}")
    if f["variable_income"]:
        parts.append(f"your income varies a lot from month to month (variation {f['income_cv']})")
    buffer = (
        f" A buffer of about {format_inr(f['buffer_target'])} (one month of essentials) smooths this out."
        if f["buffer_target"]
        else ""
    )
    return Explanation(
        title="Smooth out your monthly cash flow",
        explanation=f"Uneven cash flow makes it harder to cover bills on time.{buffer}",
        reason="In recent months, " + _join(parts) + ".",
    )


def _celebrate(f: dict[str, Any]) -> Explanation:
    if f["milestone"] == 100:
        title, body = f"You reached '{f['goal_name']}'!", "You have saved the full target amount."
    else:
        title = f"'{f['goal_name']}' is {f['milestone']}% funded"
        body = f"You have saved {format_inr(f['saved_amount'])} of {format_inr(f['target_amount'])}."
    return Explanation(
        title=title,
        explanation=body + " Well done.",
        reason=f"Recorded progress is {f['progress_pct']}% of the target.",
    )


TEMPLATES: dict[str, Callable[[dict[str, Any]], Explanation]] = {
    "MISSING_INFO_REQUEST": _missing_info,
    "EMERGENCY_FUND_BUILD": _emergency,
    "GOAL_SAVINGS_INCREASE": _goal_savings,
    "DISCRETIONARY_SPENDING_REVIEW": _discretionary,
    "UPCOMING_OBLIGATIONS_PREPARE": _upcoming,
    "RECURRING_EXPENSES_REVIEW": _recurring,
    "CASH_FLOW_CONSISTENCY": _cash_flow,
    "GOAL_PROGRESS_CELEBRATE": _celebrate,
}


def explain(outcome: RuleOutcome) -> Explanation:
    return TEMPLATES[outcome.rule_id](outcome.facts)
