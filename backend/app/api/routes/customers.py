from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession, Pagination, ReadableCustomer
from app.models.tables import DataQualityEvent
from app.repositories import customers as repo
from app.schemas.api import (
    AccountOut,
    CustomerDetail,
    CustomerSummary,
    DataQualityEventOut,
    FinancialProfileOut,
    GoalOut,
    ObligationOut,
    Paginated,
    TransactionSummaryOut,
    page_meta,
)

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])

Segment = Annotated[str | None, Query(pattern=r"^[a-z_]{3,40}$", description="Persona segment filter")]


@router.get(
    "",
    response_model=Paginated[CustomerSummary],
    summary="List customers visible to the caller (customers see only themselves)",
)
def list_customers(
    principal: CurrentPrincipal,
    session: DbSession,
    page: Pagination,
    search: Annotated[str | None, Query(min_length=1, max_length=60)] = None,
    segment: Segment = None,
) -> Paginated[CustomerSummary]:
    restrict = None if principal.is_advisor else principal.profile_id
    rows, total = repo.list_customers(
        session, restrict_to=restrict, search=search, segment=segment, offset=page.offset, limit=page.page_size
    )
    items = [
        CustomerSummary(
            id=p.id,
            display_name=p.display_name,
            is_synthetic=p.is_synthetic,
            persona_segment=p.financial_profile.persona_segment if p.financial_profile else None,
            income_pattern=p.financial_profile.income_pattern if p.financial_profile else None,
        )
        for p in rows
    ]
    return Paginated[CustomerSummary](items=items, meta=page_meta(page.page, page.page_size, total))


@router.get("/{customer_id}", response_model=CustomerDetail, summary="Customer financial profile")
def get_customer(customer: ReadableCustomer, session: DbSession) -> CustomerDetail:
    count, first, last = repo.transaction_summary(session, customer.id)
    return CustomerDetail(
        id=customer.id,
        display_name=customer.display_name,
        is_synthetic=customer.is_synthetic,
        data_sharing_consent=customer.data_sharing_consent,
        financial_profile=FinancialProfileOut.model_validate(customer.financial_profile)
        if customer.financial_profile
        else None,
        accounts=[AccountOut.model_validate(a) for a in repo.list_accounts(session, customer.id)],
        obligations=[ObligationOut.model_validate(o) for o in repo.list_obligations(session, customer.id)],
        goals=[GoalOut.model_validate(g) for g in repo.list_goals(session, customer.id)],
        transaction_summary=TransactionSummaryOut(
            transaction_count=count, first_transaction_date=first, last_transaction_date=last
        ),
    )


@router.get("/{customer_id}/obligations", response_model=list[ObligationOut], summary="Known obligations")
def list_obligations(customer: ReadableCustomer, session: DbSession) -> list[ObligationOut]:
    return [ObligationOut.model_validate(o) for o in repo.list_obligations(session, customer.id)]


@router.get(
    "/{customer_id}/data-quality-events",
    response_model=list[DataQualityEventOut],
    summary="Recorded data-quality findings for this customer",
)
def data_quality_events(customer: ReadableCustomer, session: DbSession) -> list[DataQualityEventOut]:
    rows = session.scalars(
        select(DataQualityEvent)
        .where(DataQualityEvent.customer_id == customer.id)
        .order_by(DataQualityEvent.detected_at.desc(), DataQualityEvent.check_code)
        .limit(100)
    )
    return [DataQualityEventOut.model_validate(r) for r in rows]
