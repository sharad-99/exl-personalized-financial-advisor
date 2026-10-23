"""Deterministic, explainable recommendation engine.

Responsibilities are split three ways:
  * this module   -> decide WHICH recommendations apply and WHY (facts + evidence)
  * recommendation_explanations -> turn facts into customer-facing text
  * recommendation_service      -> persistence, de-duplication and status

Hard guarantees (enforced here and by tests):
  * Same inputs + as_of + rule version => identical outcomes.
  * Every outcome carries rule id/version, inputs, calculations, assumptions
    and a priority reason. No opaque scores.
  * Missing data never silently becomes zero: rules that need a missing input
    are suppressed with a recorded reason.
  * No loans, no securities or specific investment products, no transactions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Any, Literal

from app.models.domain import CustomerFinancialData
from app.schemas.analytics import AnalyticsResult
from app.services.financial_analytics import emergency_reserve
from app.utils.dates import month_key
from app.utils.formatting import format_inr
from app.utils.money import ZERO, to_money

Priority = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    version: int
    category: str
    name: str
    description: str
    parameters: dict[str, Any]


RULES: dict[str, RuleDefinition] = {
    r.rule_id: r
    for r in (
        RuleDefinition(
            "MISSING_INFO_REQUEST",
            1,
            "missing_information",
            "Request missing information",
            "Ask for missing or stale data before giving further guidance.",
            {"stale_after_days": 35, "min_history_months": 3},
        ),
        RuleDefinition(
            "EMERGENCY_FUND_BUILD",
            1,
            "emergency_fund",
            "Build an emergency fund",
            "Liquid savings cover fewer months of essential expenses than the target.",
            {
                "base_target_months": 3,
                "elevated_target_months": 6,
                "high_priority_below_months": 1,
                "max_share_of_capacity": "0.50",
                "build_months": 12,
            },
        ),
        RuleDefinition(
            "GOAL_SAVINGS_INCREASE",
            1,
            "goal_savings",
            "Increase savings toward a goal",
            "A dated goal needs more per month than is currently planned.",
            {"high_priority_goal_rank": 1, "high_priority_within_months": 12},
        ),
        RuleDefinition(
            "DISCRETIONARY_SPENDING_REVIEW",
            1,
            "discretionary_spending",
            "Review high discretionary spending",
            "Discretionary spending is a large share of expenses or rose sharply.",
            {
                "share_threshold_pct": "35",
                "spike_ratio": "1.25",
                "spike_min_increase": "2000",
                "illustrative_reduction_pct": "10",
            },
        ),
        RuleDefinition(
            "UPCOMING_OBLIGATIONS_PREPARE",
            1,
            "upcoming_obligations",
            "Prepare for upcoming obligations",
            "Known non-monthly or large obligations are due within 30 days.",
            {"horizon_days": 30, "balance_share_threshold": "0.50"},
        ),
        RuleDefinition(
            "RECURRING_EXPENSES_REVIEW",
            1,
            "recurring_expenses",
            "Review recurring subscriptions",
            "Several recurring subscription charges were detected.",
            {"min_subscriptions": 3, "min_monthly_total": "1500", "income_share_threshold_pct": "3"},
        ),
        RuleDefinition(
            "CASH_FLOW_CONSISTENCY",
            1,
            "cash_flow_consistency",
            "Improve cash-flow consistency",
            "Spending exceeded income in recent months or income is highly variable.",
            {"lookback_months": 3, "negative_months_threshold": 2, "income_cv_threshold": "0.25"},
        ),
        RuleDefinition(
            "GOAL_PROGRESS_CELEBRATE",
            1,
            "goal_celebration",
            "Celebrate goal progress",
            "A goal has reached a 50%, 75% or 100% milestone.",
            {"milestones_pct": [50, 75, 100]},
        ),
    )
}

# Rules that rely on recorded goal data only; they may run even with low data confidence.
RUNS_ON_LOW_CONFIDENCE = frozenset({"MISSING_INFO_REQUEST", "GOAL_PROGRESS_CELEBRATE"})


@dataclass(frozen=True)
class RuleOutcome:
    rule_id: str
    rule_version: int
    category: str
    subject_key: str
    priority: Priority
    priority_reason: str
    facts: dict[str, Any]  # template variables for the explanation layer
    evidence: dict[str, Any]  # inputs, calculations, thresholds (persisted for traceability)
    assumptions: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SuppressedRule:
    rule_id: str
    reason: str


@dataclass(frozen=True)
class EngineResult:
    customer_id: str
    as_of: date
    period_key: str
    confidence: str
    confidence_reason: str
    data_as_of: date | None
    outcomes: list[RuleOutcome]
    suppressed: list[SuppressedRule]


def _s(value: Decimal | None) -> str | None:
    """Evidence values are stored as strings to keep exact decimals in JSON."""
    return None if value is None else str(value)


def _rule(rule_id: str) -> RuleDefinition:
    return RULES[rule_id]


def _confidence_qualifier(analytics: AnalyticsResult) -> list[str]:
    dq = analytics.data_quality
    if dq.confidence == "high":
        return []
    return [f"Data confidence is {dq.confidence}: " + "; ".join(dq.confidence_reasons)]


# --------------------------------------------------------------------------- rules
def rule_missing_info(data: CustomerFinancialData, a: AnalyticsResult) -> list[RuleOutcome]:
    dq = a.data_quality
    codes = {i.code for i in dq.issues}
    gaps: list[str] = []
    if dq.freshness in {"stale", "no_data"}:
        gaps.append("recent_transactions")
    if "short_history" in codes:
        gaps.append("longer_transaction_history")
    if "missing_income" in codes:
        gaps.append("monthly_income")
    if "missing_balance" in codes:
        gaps.append("account_balances")
    if not gaps:
        return []
    if "stale_profile" in codes:
        gaps.append("profile_confirmation")
    rule = _rule("MISSING_INFO_REQUEST")
    priority: Priority = "high" if dq.confidence == "low" else "medium"
    actions = {
        "recent_transactions": "Refresh or re-link your account so recent transactions are available.",
        "longer_transaction_history": "Allow at least three months of history to build up before relying on trends.",
        "monthly_income": "Confirm your typical monthly income in your profile.",
        "account_balances": "Share an up-to-date balance for your savings account.",
        "profile_confirmation": "Review and confirm your profile details.",
    }
    return [
        RuleOutcome(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            category=rule.category,
            subject_key="data-gaps",
            priority=priority,
            priority_reason=(
                "Data confidence is low, so other guidance is paused until this is resolved."
                if priority == "high"
                else "Some guidance is qualified until this data is provided."
            ),
            facts={
                "gaps": gaps,
                "days_since_last_transaction": dq.days_since_last_transaction,
                "history_months": dq.history_months,
            },
            evidence={
                "inputs": {
                    "freshness": dq.freshness,
                    "days_since_last_transaction": dq.days_since_last_transaction,
                    "latest_transaction_date": dq.latest_transaction_date.isoformat()
                    if dq.latest_transaction_date
                    else None,
                    "history_months": dq.history_months,
                    "balance_status": dq.balance_status,
                    "quality_issue_codes": sorted(codes),
                },
                "calculations": {"missing_items": gaps},
                "thresholds": rule.parameters,
            },
            assumptions=["Guidance quality depends on recent, complete data; we do not fill gaps with zeros."],
            actions=[actions[g] for g in gaps],
        )
    ]


def rule_emergency_fund(data: CustomerFinancialData, a: AnalyticsResult) -> list[RuleOutcome] | SuppressedRule:
    ef = a.emergency_fund
    rule = _rule("EMERGENCY_FUND_BUILD")
    if ef.status == "unknown":
        return SuppressedRule(rule.rule_id, ef.reason or "Emergency-fund coverage cannot be calculated.")
    if ef.status == "sufficient":
        return []
    assert ef.coverage_months is not None and ef.gap_amount is not None  # status implies these exist
    capacity = a.savings_capacity.estimated_monthly_capacity
    suggested = emergency_reserve(capacity, ef)
    months_to_target = None
    calcs = {
        "coverage_months": f"{ef.liquid_balance} / {ef.average_monthly_essential_expenses} = {ef.coverage_months}",
        "target_amount": f"{ef.average_monthly_essential_expenses} x {ef.target_months} = {ef.target_amount}",
        "gap_amount": f"max({ef.target_amount} - {ef.liquid_balance}, 0) = {ef.gap_amount}",
    }
    if suggested > 0:
        months_to_target = int((ef.gap_amount / suggested).to_integral_value(rounding=ROUND_CEILING))
        calcs["suggested_monthly"] = f"min(50% of capacity {capacity}, gap {ef.gap_amount} / 12) = {suggested}"
        calcs["months_to_target"] = f"ceil({ef.gap_amount} / {suggested}) = {months_to_target}"
    else:
        calcs["suggested_monthly"] = "No amount suggested: estimated capacity after expenses and obligations is 0."
    high = ef.coverage_months < 1
    near_target = ef.coverage_months >= Decimal(ef.target_months) * Decimal("0.9")
    actions = (
        [f"Set up a monthly transfer of about {format_inr(suggested)} to a separate savings account."]
        if suggested > 0
        else ["Review non-essential spending to free up room for a small monthly buffer."]
    )
    actions.append("Keep the emergency fund in an easily accessible account, separate from daily spending.")
    return [
        RuleOutcome(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            category=rule.category,
            subject_key="emergency-fund",
            priority="high" if high else ("low" if near_target else "medium"),
            priority_reason=(
                f"Liquid savings cover {ef.coverage_months} months of essential expenses, below 1 month."
                if high
                else f"Coverage of {ef.coverage_months} months is close to the {ef.target_months}-month target."
                if near_target
                else f"Coverage of {ef.coverage_months} months is below the {ef.target_months}-month target."
            ),
            facts={
                "coverage_months": ef.coverage_months,
                "target_months": ef.target_months,
                "gap_amount": ef.gap_amount,
                "suggested_monthly": suggested if suggested > 0 else None,
                "months_to_target": months_to_target,
                "liquid_balance": ef.liquid_balance,
                "avg_essential": ef.average_monthly_essential_expenses,
            },
            evidence={
                "inputs": {
                    "liquid_balance": _s(ef.liquid_balance),
                    "average_monthly_essential_expenses": _s(ef.average_monthly_essential_expenses),
                    "target_months": ef.target_months,
                    "estimated_monthly_capacity": _s(capacity),
                    "basis_months": a.monthly_averages.basis_months,
                },
                "calculations": calcs,
                "thresholds": rule.parameters,
            },
            assumptions=ef.assumptions
            + [
                "Suggested amounts use at most half of the estimated monthly capacity, which already excludes "
                "essential spending and known obligations.",
            ]
            + _confidence_qualifier(a),
            actions=actions,
        )
    ]


def rule_goal_savings(data: CustomerFinancialData, a: AnalyticsResult) -> list[RuleOutcome]:
    rule = _rule("GOAL_SAVINGS_INCREASE")
    outcomes: list[RuleOutcome] = []
    for goal in a.goals:
        if goal.plan_status != "behind" or goal.required_monthly is None:
            continue
        soon = goal.months_remaining is not None and goal.months_remaining <= 12
        if goal.priority == 1 and soon:
            priority: Priority = "high"
            reason = "This is your top-priority goal and its target date is within 12 months."
        elif goal.priority >= 4:
            priority, reason = "low", f"This goal is ranked priority {goal.priority} of 5."
        else:
            priority, reason = "medium", "The goal is behind schedule at the current planned contribution."
        actions = []
        if goal.suggested_increase and not goal.suggested_target_date:
            actions.append(f"Increase the monthly contribution by about {format_inr(goal.suggested_increase)}.")
        if goal.suggested_target_date:
            if goal.suggested_increase:
                actions.append(
                    f"Add about {format_inr(goal.suggested_increase)} per month, the most the estimate allows."
                )
            actions.append(f"Consider moving the target date to around {goal.suggested_target_date:%b %Y}.")
        if not actions:
            actions.append("Review the target amount or date for this goal.")
        outcomes.append(
            RuleOutcome(
                rule_id=rule.rule_id,
                rule_version=rule.version,
                category=rule.category,
                subject_key=f"goal:{goal.goal_id}",
                priority=priority,
                priority_reason=reason,
                facts={
                    "goal_name": goal.name,
                    "required_monthly": goal.required_monthly,
                    "planned_monthly": goal.planned_monthly,
                    "suggested_increase": goal.suggested_increase,
                    "suggested_target_date": goal.suggested_target_date,
                    "months_remaining": goal.months_remaining,
                    "remaining_amount": goal.remaining_amount,
                    "target_date": goal.target_date,
                    "capacity_known": a.savings_capacity.estimated_monthly_capacity is not None,
                },
                evidence={
                    "inputs": {
                        "goal_id": goal.goal_id,
                        "target_amount": _s(goal.target_amount),
                        "saved_amount": _s(goal.saved_amount),
                        "planned_monthly": _s(goal.planned_monthly),
                        "target_date": goal.target_date.isoformat() if goal.target_date else None,
                        "goal_priority": goal.priority,
                        "estimated_monthly_capacity": _s(a.savings_capacity.estimated_monthly_capacity),
                    },
                    "calculations": goal.calculation,
                    "thresholds": rule.parameters,
                },
                assumptions=goal.assumptions + _confidence_qualifier(a),
                actions=actions,
            )
        )
    return outcomes


def rule_discretionary(data: CustomerFinancialData, a: AnalyticsResult) -> list[RuleOutcome] | SuppressedRule:
    rule = _rule("DISCRETIONARY_SPENDING_REVIEW")
    avg = a.monthly_averages
    if avg.basis_months < 3 or not avg.expenses or avg.discretionary_expenses is None:
        return SuppressedRule(rule.rule_id, "Needs at least 3 months of expense data.")
    share = (avg.discretionary_expenses / avg.expenses * 100).quantize(Decimal("0.1"))
    complete = [p for p in a.monthly_trend if not p.is_partial and p.has_data]
    spike_ratio = Decimal(rule.parameters["spike_ratio"])
    latest = complete[-1] if complete else None
    trailing = complete[-4:-1]
    trailing_avg = (
        to_money(sum((p.discretionary_expenses for p in trailing), ZERO) / len(trailing))
        if len(trailing) == 3
        else None
    )
    spike = bool(
        latest
        and trailing_avg
        and trailing_avg > 0
        and latest.discretionary_expenses >= trailing_avg * spike_ratio
        and latest.discretionary_expenses - trailing_avg >= Decimal(rule.parameters["spike_min_increase"])
    )
    high_share = share >= Decimal(rule.parameters["share_threshold_pct"])
    if not (high_share or spike):
        return []
    top = [c for c in a.spending_by_category if c.group == "discretionary"][:3]
    illustrative = to_money(avg.discretionary_expenses * Decimal("0.10"))
    negative = avg.net_observed_cash_flow is not None and avg.net_observed_cash_flow < 0
    calcs = {
        "discretionary_share_pct": f"{avg.discretionary_expenses} / {avg.expenses} x 100 = {share}",
        "illustrative_monthly_saving": f"10% x {avg.discretionary_expenses} = {illustrative}",
    }
    if latest and trailing_avg is not None:
        calcs["latest_vs_trailing"] = (
            f"{latest.month}: {latest.discretionary_expenses} vs prior 3-month average {trailing_avg}"
        )
    return [
        RuleOutcome(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            category=rule.category,
            subject_key="discretionary",
            priority="high" if negative else "medium",
            priority_reason=(
                "Average spending exceeds average income, so discretionary costs matter most now."
                if negative
                else "Discretionary spending is high relative to your total spending."
            ),
            facts={
                "share_pct": share,
                "high_share": high_share,
                "spike": spike,
                "latest_month": latest.month if latest else None,
                "latest_amount": latest.discretionary_expenses if latest else None,
                "trailing_avg": trailing_avg,
                "top_categories": [(c.category, c.amount) for c in top],
                "illustrative_saving": illustrative,
            },
            evidence={
                "inputs": {
                    "avg_monthly_discretionary": _s(avg.discretionary_expenses),
                    "avg_monthly_expenses": _s(avg.expenses),
                    "basis_months": avg.basis_months,
                    "top_discretionary_categories": [
                        {"category": c.category, "period_total": _s(c.amount)} for c in top
                    ],
                },
                "calculations": calcs,
                "thresholds": rule.parameters,
            },
            assumptions=[
                "Discretionary = dining, shopping, entertainment, subscriptions, travel, personal care and gifts.",
                "The 10% figure is illustrative, not a target set for you.",
            ]
            + _confidence_qualifier(a),
            actions=[
                f"Review recent {top[0].category.replace('_', ' ')} spending."
                if top
                else "Review recent discretionary spending.",
                "Set a monthly spending limit for your largest discretionary category.",
            ],
        )
    ]


def rule_upcoming_obligations(data: CustomerFinancialData, a: AnalyticsResult) -> list[RuleOutcome]:
    rule = _rule("UPCOMING_OBLIGATIONS_PREPARE")
    up = a.upcoming_obligations
    if not up.items:
        return []
    lumpy = [o for o in up.items if o.frequency != "monthly"]
    liquid = a.balances.reported_liquid_balance
    share = (up.total_due / liquid).quantize(Decimal("0.01")) if liquid and liquid > 0 else None
    over_threshold = share is not None and share > Decimal(rule.parameters["balance_share_threshold"])
    if not lumpy and not over_threshold:
        return []
    if liquid is not None and up.total_due > liquid:
        priority: Priority = "high"
        reason = "Obligations due in the next 30 days exceed the reported liquid balance."
    elif over_threshold or any(o.days_until_due <= 14 for o in lumpy):
        priority, reason = "medium", "A large or non-routine payment is due soon."
    else:
        priority, reason = "low", "A non-routine payment is due within 30 days."
    assumptions = ["Monthly obligations are assumed to be paid from regular income as usual."]
    if liquid is None:
        assumptions.append("Liquid balance is not reported, so affordability could not be checked.")
    assumptions += _confidence_qualifier(a)
    return [
        RuleOutcome(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            category=rule.category,
            subject_key="upcoming-30d",
            priority=priority,
            priority_reason=reason,
            facts={
                "items": [(o.name, o.amount, o.due_date) for o in up.items],
                "total_due": up.total_due,
                "lumpy": [(o.name, o.amount, o.due_date) for o in lumpy],
                "liquid_balance": liquid,
            },
            evidence={
                "inputs": {
                    "obligations": [
                        {
                            "id": o.obligation_id,
                            "name": o.name,
                            "amount": _s(o.amount),
                            "frequency": o.frequency,
                            "due_date": o.due_date.isoformat(),
                        }
                        for o in up.items
                    ],
                    "reported_liquid_balance": _s(liquid),
                },
                "calculations": {
                    "total_due": " + ".join(_s(o.amount) or "" for o in up.items) + f" = {up.total_due}",
                    "share_of_liquid_balance": f"{up.total_due} / {liquid} = {share}"
                    if share is not None
                    else "not available",
                },
                "thresholds": rule.parameters,
            },
            assumptions=assumptions,
            actions=[
                f"Keep {format_inr(o.amount)} available for {o.name} by {o.due_date:%d %b %Y}."
                for o in (lumpy or up.items)[:3]
            ],
        )
    ]


def rule_recurring(data: CustomerFinancialData, a: AnalyticsResult) -> list[RuleOutcome]:
    rule = _rule("RECURRING_EXPENSES_REVIEW")
    subs = [r for r in a.recurring_expenses if r.is_subscription]
    total = sum((r.average_amount for r in subs), ZERO)
    income = a.monthly_averages.income
    income_share = (total / income * 100).quantize(Decimal("0.1")) if income else None
    triggered = len(subs) >= rule.parameters["min_subscriptions"] or (
        subs
        and (
            total >= Decimal(rule.parameters["min_monthly_total"])
            or (income_share is not None and income_share >= Decimal(rule.parameters["income_share_threshold_pct"]))
        )
    )
    if not triggered:
        return []
    negative = a.monthly_averages.net_observed_cash_flow is not None and a.monthly_averages.net_observed_cash_flow < 0
    annual = total * 12
    return [
        RuleOutcome(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            category=rule.category,
            subject_key="subscriptions",
            priority="medium" if negative else "low",
            priority_reason=(
                "Spending exceeds income on average, so recurring costs are worth reviewing."
                if negative
                else "Recurring charges add up over a year, but are not urgent."
            ),
            facts={
                "count": len(subs),
                "monthly_total": total,
                "annual_total": annual,
                "merchants": [(r.merchant, r.average_amount) for r in subs],
            },
            evidence={
                "inputs": {
                    "subscriptions": [
                        {
                            "merchant": r.merchant,
                            "average_amount": _s(r.average_amount),
                            "months_observed": r.months_observed,
                            "last_date": r.last_date.isoformat(),
                        }
                        for r in subs
                    ],
                    "avg_monthly_income": _s(income),
                },
                "calculations": {
                    "monthly_total": " + ".join(_s(r.average_amount) or "" for r in subs) + f" = {total}",
                    "annual_total": f"{total} x 12 = {annual}",
                    "share_of_income_pct": str(income_share) if income_share is not None else "n/a",
                },
                "thresholds": rule.parameters,
            },
            assumptions=[
                "Recurring = same merchant charged roughly monthly in 3+ of the last 6 months with amounts within 15%."
            ]
            + _confidence_qualifier(a),
            actions=[
                "Check whether each subscription is still used.",
                "Cancel or downgrade the ones you no longer need.",
            ],
        )
    ]


def rule_cash_flow(data: CustomerFinancialData, a: AnalyticsResult) -> list[RuleOutcome] | SuppressedRule:
    rule = _rule("CASH_FLOW_CONSISTENCY")
    complete = [p for p in a.monthly_trend if not p.is_partial and p.has_data][-3:]
    if len(complete) < 3:
        return SuppressedRule(rule.rule_id, "Needs 3 complete months of data.")
    negative = [p for p in complete if p.net_observed_cash_flow < 0]
    cv = a.income_stability.coefficient_of_variation
    variable = cv is not None and cv > Decimal(rule.parameters["income_cv_threshold"])
    if len(negative) < rule.parameters["negative_months_threshold"] and not variable:
        return []
    avg_net = a.monthly_averages.net_observed_cash_flow
    buffer_target = a.monthly_averages.essential_expenses
    high = avg_net is not None and avg_net < 0
    actions = []
    if buffer_target:
        actions.append(f"Aim to keep a buffer of about one month of essential expenses ({format_inr(buffer_target)}).")
    if variable:
        actions.append("When a large payment arrives, set part of it aside to cover leaner months.")
    actions.append("Schedule bill payments shortly after income usually arrives.")
    return [
        RuleOutcome(
            rule_id=rule.rule_id,
            rule_version=rule.version,
            category=rule.category,
            subject_key="cash-flow",
            priority="high" if high else "medium",
            priority_reason=(
                "Average spending is higher than average income over the period."
                if high
                else "Cash flow is uneven month to month."
            ),
            facts={
                "negative_months": [p.month for p in negative],
                "income_cv": cv,
                "variable_income": variable,
                "avg_net": avg_net,
                "buffer_target": buffer_target,
            },
            evidence={
                "inputs": {
                    "last_3_months": [
                        {
                            "month": p.month,
                            "income": _s(p.income),
                            "expenses": _s(p.expenses),
                            "net": _s(p.net_observed_cash_flow),
                        }
                        for p in complete
                    ],
                    "income_coefficient_of_variation": _s(cv),
                },
                "calculations": {
                    "negative_months": f"{len(negative)} of last 3 complete months had net < 0",
                    "income_variability": f"coefficient of variation = {cv}",
                },
                "thresholds": rule.parameters,
            },
            assumptions=["Net observed cash flow excludes transfers between your own accounts."]
            + _confidence_qualifier(a),
            actions=actions,
        )
    ]


def rule_goal_celebrate(data: CustomerFinancialData, a: AnalyticsResult) -> list[RuleOutcome]:
    rule = _rule("GOAL_PROGRESS_CELEBRATE")
    outcomes: list[RuleOutcome] = []
    for goal in a.goals:
        if goal.goal_status in {"paused", "cancelled"} or goal.progress_pct < 50:
            continue
        milestone = 100 if goal.progress_pct >= 100 else (75 if goal.progress_pct >= 75 else 50)
        outcomes.append(
            RuleOutcome(
                rule_id=rule.rule_id,
                rule_version=rule.version,
                category=rule.category,
                subject_key=f"goal:{goal.goal_id}:m{milestone}",
                priority="low",
                priority_reason="Positive progress update; no action is required.",
                facts={
                    "goal_name": goal.name,
                    "milestone": milestone,
                    "progress_pct": goal.progress_pct,
                    "saved_amount": goal.saved_amount,
                    "target_amount": goal.target_amount,
                },
                evidence={
                    "inputs": {
                        "goal_id": goal.goal_id,
                        "saved_amount": _s(goal.saved_amount),
                        "target_amount": _s(goal.target_amount),
                    },
                    "calculations": {
                        "progress_pct": goal.calculation.get("progress_pct", ""),
                        "milestone": f"highest of 50/75/100 reached = {milestone}",
                    },
                    "thresholds": rule.parameters,
                },
                assumptions=["Progress uses the saved amount recorded on the goal."],
                actions=(
                    ["Mark the goal as achieved, or set a new goal."]
                    if milestone == 100
                    else ["Keep your current contribution going."]
                ),
            )
        )
    return outcomes


RULE_FUNCTIONS = (
    ("MISSING_INFO_REQUEST", rule_missing_info),
    ("EMERGENCY_FUND_BUILD", rule_emergency_fund),
    ("GOAL_SAVINGS_INCREASE", rule_goal_savings),
    ("DISCRETIONARY_SPENDING_REVIEW", rule_discretionary),
    ("UPCOMING_OBLIGATIONS_PREPARE", rule_upcoming_obligations),
    ("RECURRING_EXPENSES_REVIEW", rule_recurring),
    ("CASH_FLOW_CONSISTENCY", rule_cash_flow),
    ("GOAL_PROGRESS_CELEBRATE", rule_goal_celebrate),
)
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def evaluate(data: CustomerFinancialData, analytics: AnalyticsResult, as_of: date) -> EngineResult:
    dq = analytics.data_quality
    outcomes: list[RuleOutcome] = []
    suppressed: list[SuppressedRule] = []
    if not data.data_sharing_consent:
        suppressed = [
            SuppressedRule(rule_id, "Customer has not consented to personalised insights.")
            for rule_id, _ in RULE_FUNCTIONS
        ]
    else:
        for rule_id, func in RULE_FUNCTIONS:
            if dq.confidence == "low" and rule_id not in RUNS_ON_LOW_CONFIDENCE:
                suppressed.append(
                    SuppressedRule(
                        rule_id, "Paused because data confidence is low: " + "; ".join(dq.confidence_reasons)
                    )
                )
                continue
            result = func(data, analytics)
            if isinstance(result, SuppressedRule):
                suppressed.append(result)
            else:
                outcomes.extend(result)
    outcomes.sort(key=lambda o: (PRIORITY_ORDER[o.priority], o.rule_id, o.subject_key))
    return EngineResult(
        customer_id=data.customer_id,
        as_of=as_of,
        period_key=month_key(as_of),
        confidence=dq.confidence,
        confidence_reason="; ".join(dq.confidence_reasons),
        data_as_of=dq.latest_transaction_date,
        outcomes=outcomes,
        suppressed=suppressed,
    )
