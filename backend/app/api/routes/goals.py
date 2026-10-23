from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentPrincipal, DbSession, ReadableCustomer, WritableCustomer, rate_limit
from app.api.routes.analytics import AsOf
from app.core.errors import ApiError
from app.models.tables import FinancialGoal
from app.repositories import customers as repo
from app.repositories.audit import record_audit
from app.schemas.api import GoalIn, GoalOut, GoalUpdate, GoalWithPlan
from app.services.financial_analytics import compute_analytics
from app.utils.dates import utc_now

router = APIRouter(prefix="/api/v1/customers", tags=["goals"])
MAX_ACTIVE_GOALS = 20


def _validate_dates(target_date, as_of) -> None:  # type: ignore[no-untyped-def]
    if target_date is not None and target_date <= as_of:
        raise ApiError(422, "target_date must be in the future")


@router.get(
    "/{customer_id}/goals",
    response_model=list[GoalWithPlan],
    summary="Goals with progress and assumption-based savings guidance",
)
def list_goals(customer: ReadableCustomer, session: DbSession, as_of: AsOf) -> list[GoalWithPlan]:
    goals = repo.list_goals(session, customer.id)
    analytics = compute_analytics(repo.load_financial_data(session, customer), as_of)
    plans = {p.goal_id: p for p in analytics.goals}
    return [
        GoalWithPlan(
            goal=GoalOut.model_validate(g),
            plan=plans[str(g.id)].model_dump(mode="json") if str(g.id) in plans else None,
        )
        for g in goals
    ]


@router.post(
    "/{customer_id}/goals",
    response_model=GoalOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a goal",
    dependencies=[Depends(rate_limit("goals"))],
)
def create_goal(
    body: GoalIn, customer: WritableCustomer, principal: CurrentPrincipal, session: DbSession, as_of: AsOf
) -> GoalOut:
    _validate_dates(body.target_date, as_of)
    if body.saved_amount > body.target_amount:
        raise ApiError(422, "saved_amount cannot exceed target_amount")
    if len(repo.list_goals(session, customer.id)) >= MAX_ACTIVE_GOALS:
        raise ApiError(409, f"A customer can have at most {MAX_ACTIVE_GOALS} goals")
    if any(g.name.lower() == body.name.lower() for g in repo.list_goals(session, customer.id)):
        raise ApiError(409, "A goal with this name already exists")
    now = utc_now()
    goal = FinancialGoal(customer_id=customer.id, created_at=now, updated_at=now, status="active", **body.model_dump())
    session.add(goal)
    session.flush()
    record_audit(
        session,
        actor_profile_id=principal.profile_id,
        customer_id=customer.id,
        action="goal.created",
        entity_type="financial_goal",
        entity_id=str(goal.id),
        metadata={"goal_type": body.goal_type},
    )
    session.commit()
    return GoalOut.model_validate(goal)


@router.patch(
    "/{customer_id}/goals/{goal_id}",
    response_model=GoalOut,
    summary="Update a goal",
    dependencies=[Depends(rate_limit("goals"))],
)
def update_goal(
    goal_id: uuid.UUID,
    body: GoalUpdate,
    customer: WritableCustomer,
    principal: CurrentPrincipal,
    session: DbSession,
    as_of: AsOf,
) -> GoalOut:
    goal = repo.get_goal(session, customer.id, goal_id)
    if goal is None:
        raise ApiError(404, "Goal not found")
    changes = body.model_dump(exclude_unset=True)
    if "target_date" in changes:
        _validate_dates(changes["target_date"], as_of)
    target = changes.get("target_amount", goal.target_amount)
    saved = changes.get("saved_amount", goal.saved_amount)
    if saved > target and changes.get("status") != "achieved":
        raise ApiError(422, "saved_amount cannot exceed target_amount")
    if "name" in changes and any(
        g.id != goal.id and g.name.lower() == changes["name"].lower() for g in repo.list_goals(session, customer.id)
    ):
        raise ApiError(409, "A goal with this name already exists")
    for key, value in changes.items():
        setattr(goal, key, value)
    goal.updated_at = utc_now()
    record_audit(
        session,
        actor_profile_id=principal.profile_id,
        customer_id=customer.id,
        action="goal.updated",
        entity_type="financial_goal",
        entity_id=str(goal.id),
        metadata={"fields": sorted(changes)},
    )
    session.commit()
    return GoalOut.model_validate(goal)
