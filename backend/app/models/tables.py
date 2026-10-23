"""SQLAlchemy ORM models mirroring supabase/migrations/*.sql.

The SQL migrations are the source of truth for PostgreSQL/Supabase. These
models are used by the API and, for zero-dependency local demos and unit
tests, to create an equivalent SQLite schema with `metadata.create_all`.
tests/integration/test_schema_parity.py checks the two stay aligned.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.utils.money import to_money


class Money(TypeDecorator[Decimal]):
    """NUMERIC(14,2) on PostgreSQL; exact decimal string on SQLite (which lacks a decimal type)."""

    impl = Numeric(14, 2)
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(32))
        return dialect.type_descriptor(Numeric(14, 2, asdecimal=True))

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> Any:
        if value is None:
            return None
        money = to_money(value)
        return str(money) if dialect.name == "sqlite" else money

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return to_money(Decimal(str(value)))


JsonType = JSON().with_variant(JSONB(), "postgresql")
Timestamp = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (CheckConstraint("role in ('customer', 'advisor')", name="profiles_role_check"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    auth_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    role: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    data_sharing_consent: Mapped[bool] = mapped_column(Boolean, default=True)
    marketing_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_updated_at: Mapped[datetime | None] = mapped_column(Timestamp)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now(), onupdate=func.now())

    financial_profile: Mapped[CustomerFinancialProfile | None] = relationship(
        back_populates="customer", uselist=False, lazy="joined"
    )


class CustomerFinancialProfile(Base):
    __tablename__ = "customer_financial_profiles"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    persona_segment: Mapped[str] = mapped_column(Text)
    income_pattern: Mapped[str] = mapped_column(Text)
    declared_monthly_income: Mapped[Decimal | None] = mapped_column(Money)
    age_band: Mapped[str | None] = mapped_column(Text)
    dependents: Mapped[int | None] = mapped_column(SmallInteger)
    city_tier: Mapped[str | None] = mapped_column(Text)
    risk_preference: Mapped[str] = mapped_column(Text, default="unknown")
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    profile_updated_at: Mapped[datetime] = mapped_column(Timestamp)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now(), onupdate=func.now())

    customer: Mapped[Profile] = relationship(back_populates="financial_profile")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("id", "customer_id", name="accounts_id_customer_unique"),
        UniqueConstraint("customer_id", "masked_number", name="accounts_customer_masked_unique"),
        CheckConstraint("(current_balance is null) = (balance_as_of is null)", name="accounts_balance_pair"),
        Index("accounts_customer_idx", "customer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"))
    account_type: Mapped[str] = mapped_column(Text)
    nickname: Mapped[str] = mapped_column(Text)
    masked_number: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    opening_balance: Mapped[Decimal] = mapped_column(Money)
    opening_balance_date: Mapped[date] = mapped_column(Date)
    current_balance: Mapped[Decimal | None] = mapped_column(Money)
    balance_as_of: Mapped[datetime | None] = mapped_column(Timestamp)
    is_liquid: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(Text, default="active")
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now(), onupdate=func.now())


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "customer_id"],
            ["accounts.id", "accounts.customer_id"],
            ondelete="CASCADE",
            name="transactions_account_owner_fk",
        ),
        UniqueConstraint("account_id", "external_ref", name="transactions_import_unique"),
        CheckConstraint("amount > 0", name="transactions_amount_check"),
        Index("transactions_customer_posted_idx", "customer_id", "posted_on"),
        Index("transactions_account_posted_idx", "account_id", "posted_on"),
        Index("transactions_customer_category_idx", "customer_id", "category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    external_ref: Mapped[str] = mapped_column(Text)
    posted_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Money)
    direction: Mapped[str] = mapped_column(Text)
    transaction_type: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    merchant_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    transfer_group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reverses_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


class FinancialGoal(Base):
    __tablename__ = "financial_goals"
    __table_args__ = (
        CheckConstraint("target_amount > 0", name="financial_goals_target_check"),
        Index("financial_goals_customer_idx", "customer_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    goal_type: Mapped[str] = mapped_column(Text)
    target_amount: Mapped[Decimal] = mapped_column(Money)
    saved_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    monthly_contribution: Mapped[Decimal | None] = mapped_column(Money)
    target_date: Mapped[date | None] = mapped_column(Date)
    priority: Mapped[int] = mapped_column(SmallInteger, default=3)
    status: Mapped[str] = mapped_column(Text, default="active")
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now(), onupdate=func.now())


class FinancialObligation(Base):
    __tablename__ = "financial_obligations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"))
    obligation_type: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Money)
    frequency: Mapped[str] = mapped_column(Text)
    next_due_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_essential: Mapped[bool] = mapped_column(Boolean, default=True)
    outstanding_principal: Mapped[Decimal | None] = mapped_column(Money)
    interest_rate_apr: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(Text, default="active")
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now(), onupdate=func.now())


class FinancialProduct(Base):
    __tablename__ = "financial_products"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    product_type: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    is_investment_product: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now(), onupdate=func.now())


class RecommendationRule(Base):
    __tablename__ = "recommendation_rules"

    rule_id: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["rule_id", "rule_version"],
            ["recommendation_rules.rule_id", "recommendation_rules.version"],
            name="recommendations_rule_fk",
        ),
        UniqueConstraint(
            "customer_id",
            "rule_id",
            "rule_version",
            "subject_key",
            "period_key",
            name="recommendations_dedup_unique",
        ),
        Index("recommendations_customer_status_idx", "customer_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"))
    rule_id: Mapped[str] = mapped_column(Text)
    rule_version: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(Text)
    subject_key: Mapped[str] = mapped_column(Text)
    period_key: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text)
    priority_reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JsonType)
    assumptions: Mapped[list[str]] = mapped_column(JsonType, default=list)
    suggested_actions: Mapped[list[str]] = mapped_column(JsonType, default=list)
    confidence: Mapped[str] = mapped_column(Text)
    confidence_reason: Mapped[str] = mapped_column(Text)
    data_as_of: Mapped[date | None] = mapped_column(Date)
    analytics_as_of: Mapped[date] = mapped_column(Date)
    evidence_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")
    status_changed_at: Mapped[datetime | None] = mapped_column(Timestamp)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now(), onupdate=func.now())


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedback"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("recommendations.id", ondelete="CASCADE"))
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"))
    submitted_by_profile_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("profiles.id"))
    action: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


class DataQualityEvent(Base):
    __tablename__ = "data_quality_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("profiles.id", ondelete="CASCADE"))
    check_code: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    detected_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(Timestamp)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_profile_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)  # no FK: audit rows outlive entities
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(Timestamp, server_default=func.now())


ALL_TABLES = [
    "profiles",
    "customer_financial_profiles",
    "accounts",
    "transactions",
    "financial_goals",
    "financial_obligations",
    "financial_products",
    "recommendation_rules",
    "recommendations",
    "recommendation_feedback",
    "data_quality_events",
    "audit_events",
]
