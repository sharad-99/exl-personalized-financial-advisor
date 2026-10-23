"""Request and response models for the public API."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

T = TypeVar("T")

MoneyIn = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]
GoalType = Literal[
    "emergency_fund", "home_purchase", "education", "retirement", "vehicle", "travel", "wedding", "debt_payoff", "other"
]
RecommendationStatus = Literal["pending", "accepted", "dismissed", "completed", "expired"]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    meta: PageMeta


def page_meta(page: int, page_size: int, total: int) -> PageMeta:
    return PageMeta(
        page=page, page_size=page_size, total=total, total_pages=max((total + page_size - 1) // page_size, 1)
    )


# ---------------------------------------------------------------- health & auth
class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    database: Literal["ok", "unavailable"]
    auth_mode: str


class LocalLoginIn(StrictInput):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_in: int


class MeOut(ApiModel):
    profile_id: uuid.UUID
    role: Literal["customer", "advisor"]
    display_name: str
    email: str | None
    customer_id: uuid.UUID | None
    is_synthetic: bool
    data_sharing_consent: bool
    marketing_consent: bool
    consent_updated_at: datetime | None


class ConsentIn(StrictInput):
    data_sharing_consent: bool | None = None
    marketing_consent: bool | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> ConsentIn:
        if self.data_sharing_consent is None and self.marketing_consent is None:
            raise ValueError("Provide at least one consent field")
        return self


# ---------------------------------------------------------------- customers
class FinancialProfileOut(ApiModel):
    persona_segment: str
    income_pattern: str
    declared_monthly_income: Decimal | None
    age_band: str | None
    dependents: int | None
    city_tier: str | None
    risk_preference: str
    currency: str
    profile_updated_at: datetime


class CustomerSummary(ApiModel):
    id: uuid.UUID
    display_name: str
    persona_segment: str | None
    income_pattern: str | None
    is_synthetic: bool


class AccountOut(ApiModel):
    id: uuid.UUID
    account_type: str
    nickname: str
    masked_number: str
    currency: str
    current_balance: Decimal | None
    balance_as_of: datetime | None
    is_liquid: bool
    status: str


class ObligationOut(ApiModel):
    id: uuid.UUID
    obligation_type: str
    name: str
    amount: Decimal
    frequency: str
    next_due_date: date
    end_date: date | None
    is_essential: bool
    outstanding_principal: Decimal | None
    interest_rate_apr: Decimal | None
    status: str


class TransactionSummaryOut(BaseModel):
    transaction_count: int
    first_transaction_date: date | None
    last_transaction_date: date | None


class CustomerDetail(ApiModel):
    id: uuid.UUID
    display_name: str
    is_synthetic: bool
    data_sharing_consent: bool
    financial_profile: FinancialProfileOut | None
    accounts: list[AccountOut]
    obligations: list[ObligationOut]
    goals: list[GoalOut]
    transaction_summary: TransactionSummaryOut


# ---------------------------------------------------------------- transactions
class TransactionOut(ApiModel):
    id: uuid.UUID
    account_id: uuid.UUID
    posted_on: date
    amount: Decimal
    direction: str
    transaction_type: str
    category: str
    effective_category: str
    category_source: str
    merchant_name: str | None
    description: str
    counted_as: Literal["income", "expense", "refund", "excluded"]
    exclusion_reason: str | None


# ---------------------------------------------------------------- goals
class GoalOut(ApiModel):
    id: uuid.UUID
    name: str
    goal_type: str
    target_amount: Decimal
    saved_amount: Decimal
    monthly_contribution: Decimal | None
    target_date: date | None
    priority: int
    status: str
    created_at: datetime
    updated_at: datetime


class GoalIn(StrictInput):
    name: str = Field(min_length=1, max_length=80)
    goal_type: GoalType
    target_amount: MoneyIn = Field(gt=0, le=Decimal("100000000000"))
    saved_amount: MoneyIn = Field(default=Decimal("0"), ge=0, le=Decimal("100000000000"))
    monthly_contribution: MoneyIn | None = Field(default=None, ge=0, le=Decimal("100000000"))
    target_date: date | None = None
    priority: int = Field(default=3, ge=1, le=5)

    @field_validator("name")
    @classmethod
    def _no_control_chars(cls, value: str) -> str:
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("Name must not contain control characters")
        return value


class GoalUpdate(StrictInput):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    target_amount: MoneyIn | None = Field(default=None, gt=0, le=Decimal("100000000000"))
    saved_amount: MoneyIn | None = Field(default=None, ge=0, le=Decimal("100000000000"))
    monthly_contribution: MoneyIn | None = Field(default=None, ge=0, le=Decimal("100000000"))
    target_date: date | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    status: Literal["active", "achieved", "paused", "cancelled"] | None = None


class GoalWithPlan(BaseModel):
    goal: GoalOut
    plan: dict[str, Any] | None


# ---------------------------------------------------------------- recommendations
class FeedbackOut(ApiModel):
    id: uuid.UUID
    action: str
    reason_code: str | None
    comment: str | None
    created_at: datetime


class RecommendationOut(ApiModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    rule_id: str
    rule_version: int
    category: str
    title: str
    explanation: str
    reason: str
    priority: Literal["high", "medium", "low"]
    priority_reason: str
    evidence: dict[str, Any]
    assumptions: list[str]
    suggested_actions: list[str]
    confidence: Literal["high", "medium", "low"]
    confidence_reason: str
    data_as_of: date | None
    analytics_as_of: date
    period_key: str
    status: RecommendationStatus
    status_changed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RecommendationDetail(RecommendationOut):
    feedback: list[FeedbackOut]


class SuppressedRuleOut(BaseModel):
    rule_id: str
    reason: str


class RecommendationList(BaseModel):
    items: list[RecommendationOut]
    meta: PageMeta
    is_synthetic_data: bool = True


class RefreshOut(BaseModel):
    created: int
    updated: int
    unchanged: int
    expired: int
    as_of: date
    confidence: str
    confidence_reason: str
    suppressed_rules: list[SuppressedRuleOut]
    active: list[RecommendationOut]


class FeedbackIn(StrictInput):
    action: Literal["accepted", "dismissed", "completed", "correction"]
    reason_code: (
        Literal[
            "not_relevant",
            "already_doing_this",
            "cannot_afford",
            "income_incorrect",
            "expense_incorrect",
            "goal_outdated",
            "transaction_miscategorized",
            "other",
        ]
        | None
    ) = None
    comment: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _correction_needs_reason(self) -> FeedbackIn:
        if self.action == "correction" and self.reason_code is None:
            raise ValueError("A correction requires a reason_code")
        return self


class FeedbackResult(BaseModel):
    recommendation: RecommendationOut
    feedback: FeedbackOut


class RuleOut(ApiModel):
    rule_id: str
    version: int
    category: str
    name: str
    description: str
    parameters: dict[str, Any]
    is_active: bool


class DataQualityEventOut(ApiModel):
    id: uuid.UUID
    check_code: str
    severity: str
    details: dict[str, Any]
    detected_at: datetime


CustomerDetail.model_rebuild()
