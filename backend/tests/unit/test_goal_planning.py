from datetime import date

from app.services.financial_analytics import plan_all_goals
from app.services.goal_planning import plan_goal
from tests.factories import AS_OF, d, goal


def test_achieved_goal() -> None:
    plan = plan_goal(goal(saved="120000.00"), AS_OF, d("5000"))
    assert plan.plan_status == "achieved"
    assert plan.progress_pct == d("100.0")


def test_on_track_when_planned_covers_required() -> None:
    # 100000 remaining over 12 months -> 8333.34 required (rounded up)
    plan = plan_goal(goal(monthly="9000.00"), AS_OF, d("0"))
    assert plan.required_monthly == d("8333.34")
    assert plan.plan_status == "on_track"
    assert plan.suggested_increase is None


def test_behind_with_enough_capacity_suggests_exact_shortfall() -> None:
    plan = plan_goal(goal(monthly="2000.00"), AS_OF, d("10000.00"))
    assert plan.plan_status == "behind"
    assert plan.suggested_increase == d("6333.34")
    assert plan.suggested_target_date is None


def test_suggestion_never_exceeds_available_capacity() -> None:
    plan = plan_goal(goal(monthly="2000.00"), AS_OF, d("1000.00"))
    assert plan.suggested_increase == d("1000.00")
    # 100000 / (2000 + 1000) = 33.4 -> 34 months
    assert plan.suggested_target_date == date(2029, 8, 24)


def test_unknown_capacity_gives_no_amount() -> None:
    plan = plan_goal(goal(monthly=None), AS_OF, None)
    assert plan.plan_status == "behind"
    assert plan.suggested_increase is None
    assert "cannot safely estimate" in plan.guidance


def test_zero_capacity_and_no_plan_gives_no_amount_or_date() -> None:
    plan = plan_goal(goal(monthly=None), AS_OF, d("0"))
    assert plan.suggested_increase is None
    assert plan.suggested_target_date is None


def test_overdue_no_date_and_inactive() -> None:
    assert plan_goal(goal(target_date=date(2026, 10, 1)), AS_OF, d("1000")).plan_status == "overdue"
    assert plan_goal(goal(target_date=None), AS_OF, d("1000")).plan_status == "no_target_date"
    assert plan_goal(goal(status="paused"), AS_OF, d("1000")).plan_status == "inactive"


def test_capacity_pool_is_shared_in_priority_order() -> None:
    goals = [
        goal("second", priority=2, name="Car", monthly="0.00"),
        goal("first", priority=1, name="Emergency", monthly="0.00"),
    ]
    plans = {p.goal_id: p for p in plan_all_goals(goals, AS_OF, d("10000.00"))}
    assert plans["first"].suggested_increase == d("8333.34")
    assert plans["second"].suggested_increase == d("1666.66")  # only the remainder
    total = plans["first"].suggested_increase + plans["second"].suggested_increase
    assert total == d("10000.00")
