"""Shared FastAPI dependencies: database session, authentication,
customer-level authorisation, pagination and rate limiting.

Authorisation model
  * customer: may read and modify ONLY their own customer record.
  * advisor (EXL analyst demo role): may read every synthetic customer, but may
    not modify customer data or give feedback on a customer's behalf.
A customer asking for someone else's record gets 404 (not 403) so record
existence is not disclosed.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.security import AuthenticationError, Principal, decode_access_token, rate_limiter
from app.db.connection import get_db
from app.models.tables import Profile
from app.repositories import customers as repo

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    return token.strip()


def get_principal(request: Request, session: DbSession, settings: AppSettings) -> Principal:
    token = _bearer_token(request)
    try:
        subject = decode_access_token(settings, token)
    except AuthenticationError as exc:
        raise ApiError(401, str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
    profile = repo.get_profile_by_auth_user(session, subject)
    if profile is None:
        raise ApiError(403, "No customer profile is linked to this account")
    principal = Principal(profile_id=profile.id, role=profile.role, auth_subject=subject)
    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def load_customer_for(principal: Principal, session: Session, customer_id: uuid.UUID, *, write: bool) -> Profile:
    """Central authorisation check used by every customer-scoped route."""
    if principal.role == "customer" and principal.profile_id != customer_id:
        raise ApiError(404, "Customer not found")
    if principal.is_advisor and write:
        raise ApiError(403, "Advisors have read-only access to customer data")
    customer = repo.get_customer(session, customer_id)
    if customer is None:
        raise ApiError(404, "Customer not found")
    return customer


def readable_customer(customer_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession) -> Profile:
    return load_customer_for(principal, session, customer_id, write=False)


def writable_customer(customer_id: uuid.UUID, principal: CurrentPrincipal, session: DbSession) -> Profile:
    return load_customer_for(principal, session, customer_id, write=True)


ReadableCustomer = Annotated[Profile, Depends(readable_customer)]
WritableCustomer = Annotated[Profile, Depends(writable_customer)]


@dataclass(frozen=True)
class Page:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def pagination(
    settings: AppSettings,
    page: Annotated[int, Query(ge=1, le=10_000, description="1-based page number")] = 1,
    page_size: Annotated[int | None, Query(ge=1, description="Items per page")] = None,
) -> Page:
    size = page_size or settings.default_page_size
    if size > settings.max_page_size:
        raise ApiError(422, f"page_size must be at most {settings.max_page_size}")
    return Page(page=page, page_size=size)


Pagination = Annotated[Page, Depends(pagination)]


def rate_limit(bucket: str, limit_setting: str = "rate_limit_sensitive_per_minute") -> Callable[..., None]:
    """Per-user limit for authenticated, state-changing routes.

    Depends on the authenticated principal so every user has their own bucket; keying on
    client IP would make all users share one bucket behind the Next.js proxy.
    """

    def dependency(principal: CurrentPrincipal, settings: AppSettings) -> None:
        limit = int(getattr(settings, limit_setting))
        allowed, retry_after = rate_limiter.hit(f"{bucket}:user:{principal.profile_id}", limit)
        if not allowed:
            raise ApiError(429, "Too many requests; please retry later", headers={"Retry-After": str(retry_after)})

    return dependency
