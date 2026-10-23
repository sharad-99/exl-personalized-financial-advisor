from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentPrincipal, DbSession, load_customer_for, rate_limit
from app.core.errors import ApiError
from app.models.tables import Recommendation
from app.schemas.api import FeedbackIn, FeedbackOut, FeedbackResult, RecommendationOut
from app.services import recommendation_service as svc

router = APIRouter(prefix="/api/v1", tags=["feedback"])


@router.post(
    "/recommendations/{recommendation_id}/feedback",
    response_model=FeedbackResult,
    status_code=status.HTTP_201_CREATED,
    summary="Accept, dismiss, complete or correct a recommendation (owner only)",
    dependencies=[Depends(rate_limit("feedback"))],
)
def submit_feedback(
    recommendation_id: uuid.UUID, body: FeedbackIn, principal: CurrentPrincipal, session: DbSession
) -> FeedbackResult:
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise ApiError(404, "Recommendation not found")
    try:
        load_customer_for(principal, session, rec.customer_id, write=True)
    except ApiError as exc:
        # Do not reveal whether another customer's recommendation exists.
        if exc.status_code == 404:
            raise ApiError(404, "Recommendation not found") from exc
        raise
    try:
        feedback = svc.apply_feedback(
            session,
            rec,
            actor_profile_id=principal.profile_id,
            action=body.action,
            reason_code=body.reason_code,
            comment=body.comment,
        )
    except svc.InvalidTransitionError as exc:
        session.rollback()
        raise ApiError(409, str(exc)) from exc
    session.refresh(rec)
    return FeedbackResult(
        recommendation=RecommendationOut.model_validate(rec), feedback=FeedbackOut.model_validate(feedback)
    )
