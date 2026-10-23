"""Goal progress and assumption-based savings guidance.

Guidance never proposes saving more than the *available* estimated capacity
passed in by the caller (which already excludes essential commitments), and it
never recommends borrowing or specific investment products.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Literal

from app.models.domain import GoalRecord
from app.utils.dates import add_months, months_between
from app.utils.formatting import format_inr
from app.utils.money import ZERO, to_money

GoalStatus = Literal["achieved", "on_track", "behind", "no_target_date", "overdue", "inactive"]


@dataclass(frozen=True)
class GoalPlan:
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
    plan_status: GoalStatus
    projected_completion: date | None
    suggested_increase: Decimal | None
    suggested_target_date: date | None
    guidance: str
    calculation: dict[str, str] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)


def _ceil_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def _months_to_cover(remaining: Decimal, monthly: Decimal) -> int:
    return int((remaining / monthly).to_integral_value(rounding=ROUND_CEILING))


def plan_goal(goal: GoalRecord, as_of: date, available_capacity: Decimal | None) -> GoalPlan:
    """Plan a single goal.

    available_capacity: estimated monthly amount that could additionally be
    directed to this goal (None = cannot be estimated safely).
    """
    target = to_money(goal.target_amount)
    saved = to_money(goal.saved_amount)
    remaining = max(target - saved, ZERO)
    progress = min((saved / target * 100).quantize(Decimal("0.1")), Decimal("100.0"))
    planned = to_money(goal.monthly_contribution) if goal.monthly_contribution is not None else None
    assumptions = [
        "Saved amount is as recorded on the goal; it is not verified against account balances.",
        "Months remaining are whole calendar months from the evaluation date to the target date.",
    ]
    calc: dict[str, str] = {
        "remaining_amount": f"{target} - {saved} = {remaining}",
        "progress_pct": f"{saved} / {target} x 100 = {progress}",
    }

    base = dict(
        goal_id=goal.id,
        name=goal.name,
        goal_type=goal.goal_type,
        priority=goal.priority,
        goal_status=goal.status,
        target_amount=target,
        saved_amount=saved,
        remaining_amount=remaining,
        progress_pct=progress,
        target_date=goal.target_date,
        planned_monthly=planned,
    )

    if goal.status in {"paused", "cancelled"}:
        return GoalPlan(
            **base,
            months_remaining=None,
            required_monthly=None,
            plan_status="inactive",
            projected_completion=None,
            suggested_increase=None,
            suggested_target_date=None,
            guidance="This goal is not active, so no savings guidance is generated.",
            calculation=calc,
            assumptions=assumptions,
        )

    if remaining == ZERO or goal.status == "achieved":
        return GoalPlan(
            **base,
            months_remaining=None,
            required_monthly=ZERO,
            plan_status="achieved",
            projected_completion=None,
            suggested_increase=None,
            suggested_target_date=None,
            guidance="Target reached. Consider confirming the goal as achieved.",
            calculation=calc,
            assumptions=assumptions,
        )

    projected = None
    if planned and planned > 0:
        months_needed = _months_to_cover(remaining, planned)
        projected = add_months(as_of, months_needed)
        calc["projected_completion"] = f"ceil({remaining} / {planned}) = {months_needed} months"

    if goal.target_date is None:
        return GoalPlan(
            **base,
            months_remaining=None,
            required_monthly=None,
            plan_status="no_target_date",
            projected_completion=projected,
            suggested_increase=None,
            suggested_target_date=None,
            guidance="Add a target date so we can work out a monthly amount for this goal.",
            calculation=calc,
            assumptions=assumptions,
        )

    months_left = months_between(as_of, goal.target_date)
    if months_left <= 0:
        return GoalPlan(
            **base,
            months_remaining=0,
            required_monthly=None,
            plan_status="overdue",
            projected_completion=projected,
            suggested_increase=None,
            suggested_target_date=None,
            guidance="The target date has passed with an amount still remaining. Review the target date or amount.",
            calculation=calc,
            assumptions=assumptions,
        )

    required = _ceil_money(remaining / months_left)
    calc["required_monthly"] = f"ceil({remaining} / {months_left} months) = {required}"
    current = planned or ZERO

    if current >= required:
        return GoalPlan(
            **base,
            months_remaining=months_left,
            required_monthly=required,
            plan_status="on_track",
            projected_completion=projected,
            suggested_increase=None,
            suggested_target_date=None,
            guidance=f"Your planned monthly contribution covers the required {format_inr(required)}.",
            calculation=calc,
            assumptions=assumptions,
        )

    shortfall = required - current
    calc["monthly_shortfall"] = f"{required} - {current} = {shortfall}"
    if available_capacity is None:
        return GoalPlan(
            **base,
            months_remaining=months_left,
            required_monthly=required,
            plan_status="behind",
            projected_completion=projected,
            suggested_increase=None,
            suggested_target_date=None,
            guidance="This goal needs a higher monthly amount, but we cannot safely estimate how "
            "much you could set aside from the data available.",
            calculation=calc,
            assumptions=assumptions,
        )

    capacity = max(to_money(available_capacity), ZERO)
    assumptions.append(
        "Suggested amounts are capped at the estimated capacity left after essential "
        "spending and known obligations; they are not guaranteed disposable income."
    )
    if capacity >= shortfall:
        calc["suggested_increase"] = f"min({shortfall}, available capacity {capacity}) = {shortfall}"
        return GoalPlan(
            **base,
            months_remaining=months_left,
            required_monthly=required,
            plan_status="behind",
            projected_completion=projected,
            suggested_increase=shortfall,
            suggested_target_date=None,
            guidance=f"Adding {format_inr(shortfall)} to your monthly contribution would keep this goal on schedule.",
            calculation=calc,
            assumptions=assumptions,
        )

    affordable = current + capacity
    suggested_date = None
    if affordable > 0:
        months_needed = _months_to_cover(remaining, affordable)
        suggested_date = add_months(as_of, months_needed)
        calc["suggested_target_date"] = (
            f"ceil({remaining} / ({current} + {capacity})) = {months_needed} months -> {suggested_date}"
        )
    guidance = (
        f"The required {format_inr(required)} per month is above the estimated capacity. Consider moving "
        f"the target date to around {suggested_date:%B %Y} or lowering the target amount."
        if suggested_date
        else "The estimated capacity does not currently leave room for this goal. Consider reviewing "
        "spending or moving the target date."
    )
    return GoalPlan(
        **base,
        months_remaining=months_left,
        required_monthly=required,
        plan_status="behind",
        projected_completion=projected,
        suggested_increase=capacity if capacity > 0 else None,
        suggested_target_date=suggested_date,
        guidance=guidance,
        calculation=calc,
        assumptions=assumptions,
    )
