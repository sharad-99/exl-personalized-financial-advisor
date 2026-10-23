from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, ReadableCustomer
from app.core.errors import ApiError
from app.repositories import customers as repo
from app.schemas.analytics import AnalyticsResult
from app.services.financial_analytics import compute_analytics
from app.utils.dates import add_months, utc_today

router = APIRouter(prefix="/api/v1/customers", tags=["analytics"])


def evaluation_date() -> date:
    """Analytics are evaluated as of today (UTC). Overridden in tests for determinism."""
    return utc_today()


AsOf = Annotated[date, Depends(evaluation_date)]


@router.get(
    "/{customer_id}/analytics",
    response_model=AnalyticsResult,
    summary="Computed financial analytics (never stored; derived on request)",
)
def get_analytics(
    customer: ReadableCustomer,
    session: DbSession,
    as_of: AsOf,
    months: Annotated[int, Query(ge=1, le=12, description="Complete months to analyse")] = 6,
    start_date: date | None = None,
    end_date: date | None = None,
) -> AnalyticsResult:
    if (start_date is None) != (end_date is None):
        raise ApiError(422, "Provide both start_date and end_date, or neither")
    if start_date and end_date:
        if start_date > end_date:
            raise ApiError(422, "start_date must be on or before end_date")
        if end_date > as_of:
            raise ApiError(422, "end_date cannot be in the future")
        if add_months(start_date, 24) < end_date:
            raise ApiError(422, "The period may span at most 24 months")
    data = repo.load_financial_data(session, customer)
    result = compute_analytics(data, as_of, window_months=months, start_date=start_date, end_date=end_date)
    result.is_synthetic_data = customer.is_synthetic
    return result
