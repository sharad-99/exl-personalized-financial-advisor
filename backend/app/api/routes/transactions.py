from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DbSession, Pagination, ReadableCustomer
from app.core.errors import ApiError
from app.repositories import customers as repo
from app.schemas.api import Paginated, TransactionOut, page_meta
from app.services.spending_categorization import classify_transactions

router = APIRouter(prefix="/api/v1/customers", tags=["transactions"])


@router.get(
    "/{customer_id}/transactions",
    response_model=Paginated[TransactionOut],
    summary="Transactions with classification (how each is counted in analytics)",
)
def list_transactions(
    customer: ReadableCustomer,
    session: DbSession,
    page: Pagination,
    start_date: date | None = None,
    end_date: date | None = None,
    category: Annotated[str | None, Query(pattern=r"^[a-z_]{3,30}$")] = None,
    direction: Literal["credit", "debit"] | None = None,
    account_id: uuid.UUID | None = None,
) -> Paginated[TransactionOut]:
    if start_date and end_date and start_date > end_date:
        raise ApiError(422, "start_date must be on or before end_date")
    rows, total = repo.query_transactions(
        session,
        customer.id,
        start=start_date,
        end=end_date,
        category=category,
        direction=direction,
        account_id=account_id,
        offset=page.offset,
        limit=page.page_size,
    )
    # Classification needs the customer's full history (duplicates, transfer legs, reversals).
    data = repo.load_financial_data(session, customer)
    by_id = {c.txn.id: c for c in classify_transactions(data.transactions, data.accounts)}
    items = []
    for t in rows:
        c = by_id[str(t.id)]
        items.append(
            TransactionOut(
                id=t.id,
                account_id=t.account_id,
                posted_on=t.posted_on,
                amount=t.amount,
                direction=t.direction,
                transaction_type=t.transaction_type,
                category=t.category,
                effective_category=c.category,
                category_source=c.category_source,
                merchant_name=t.merchant_name,
                description=t.description,
                counted_as=c.flow,
                exclusion_reason=c.exclusion_reason,
            )
        )
    return Paginated[TransactionOut](items=items, meta=page_meta(page.page, page.page_size, total))
