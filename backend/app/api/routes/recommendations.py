from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import (
    CurrentPrincipal,
    DbSession,
    Pagination,
    ReadableCustomer,
    WritableCustomer,
    load_customer_for,
    rate_limit,
)
from app.api.routes.analytics import AsOf
from app.core.errors import ApiError
from app.models.tables import Recommendation, RecommendationRule
from app.schemas.api import (
    FeedbackOut,
    RecommendationDetail,
    RecommendationList,
    RecommendationOut,
    RecommendationStatus,
    RefreshOut,
    RuleOut,
    SuppressedRuleOut,
    page_meta,
)
from app.services import recommendation_service as svc

router = APIRouter(prefix="/api/v1", tags=["recommendations"])


@router.get(
    "/customers/{customer_id}/recommendations",
    response_model=RecommendationList,
    summary="Stored recommendations (first call generates them once; refresh re-evaluates)",
)
def list_recommendations(
    customer: ReadableCustomer,
    principal: CurrentPrincipal,
    session: DbSession,
    page: Pagination,
    as_of: AsOf,
    status: Annotated[list[RecommendationStatus] | None, Query(description="Filter by status (repeatable)")] = None,
) -> RecommendationList:
    if not svc.has_any_recommendations(session, customer.id):
        # Idempotent: stable IDs mean this can never create duplicates.
        svc.refresh_for_customer(session, customer, as_of, principal.profile_id)
    rows, total = svc.list_recommendations(
        session, customer.id, list(status) if status else None, page.offset, page.page_size
    )
    return RecommendationList(
        items=[RecommendationOut.model_validate(r) for r in rows],
        meta=page_meta(page.page, page.page_size, total),
        is_synthetic_data=customer.is_synthetic,
    )


@router.post(
    "/customers/{customer_id}/recommendations/refresh",
    response_model=RefreshOut,
    summary="Re-evaluate rules against current data",
    dependencies=[Depends(rate_limit("refresh"))],
)
def refresh(customer: WritableCustomer, principal: CurrentPrincipal, session: DbSession, as_of: AsOf) -> RefreshOut:
    summary = svc.refresh_for_customer(session, customer, as_of, principal.profile_id)
    active, _ = svc.list_recommendations(session, customer.id, ["pending", "accepted"], 0, 100)
    return RefreshOut(
        created=summary.created,
        updated=summary.updated,
        unchanged=summary.unchanged,
        expired=summary.expired,
        as_of=as_of,
        confidence=summary.engine.confidence,
        confidence_reason=summary.engine.confidence_reason,
        suppressed_rules=[SuppressedRuleOut(rule_id=s.rule_id, reason=s.reason) for s in summary.suppressed],
        active=[RecommendationOut.model_validate(r) for r in active],
    )


@router.get(
    "/recommendations/{recommendation_id}",
    response_model=RecommendationDetail,
    summary="One recommendation with its evidence and feedback history",
)
def get_recommendation(
    recommendation_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession
) -> RecommendationDetail:
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise ApiError(404, "Recommendation not found")
    try:
        load_customer_for(principal, session, rec.customer_id, write=False)
    except ApiError as exc:
        raise ApiError(404, "Recommendation not found") from exc
    detail = RecommendationDetail.model_validate(
        {
            **RecommendationOut.model_validate(rec).model_dump(),
            "feedback": [FeedbackOut.model_validate(f) for f in svc.feedback_for(session, rec.id)],
        }
    )
    return detail


@router.get("/recommendation-rules", response_model=list[RuleOut], summary="Versioned rule catalogue")
def list_rules(_: CurrentPrincipal, session: DbSession) -> list[RuleOut]:
    svc.ensure_rules(session)
    session.commit()
    rows = session.scalars(select(RecommendationRule).order_by(RecommendationRule.rule_id, RecommendationRule.version))
    return [RuleOut.model_validate(r) for r in rows]
