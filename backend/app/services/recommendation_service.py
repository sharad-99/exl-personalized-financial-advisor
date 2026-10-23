"""Recommendation persistence: stable IDs, de-duplication, status and feedback.

Refreshing is idempotent: running it twice with the same data, date and rule
versions creates nothing new. IDs are UUIDv5 over
(customer, rule, version, subject, period), so the same advice in the same
month always maps to the same row.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.tables import Profile, Recommendation, RecommendationFeedback, RecommendationRule
from app.repositories.audit import record_audit
from app.repositories.customers import load_financial_data
from app.services.financial_analytics import compute_analytics
from app.services.recommendation_engine import RULES, EngineResult, RuleOutcome, SuppressedRule, evaluate
from app.services.recommendation_explanations import explain
from app.utils.dates import utc_now

RECOMMENDATION_NAMESPACE = uuid.UUID("2f0c9a5e-8d1b-4c7a-b3e6-91d4f05a7c28")
ACTIVE_STATUSES = frozenset({"pending", "accepted"})
DISMISSAL_RESPECT_DAYS = 60
FEEDBACK_TO_STATUS = {"accepted": "accepted", "dismissed": "dismissed", "completed": "completed"}
ALLOWED_TRANSITIONS = {
    "pending": {"accepted", "dismissed", "completed"},
    "accepted": {"completed", "dismissed"},
    "dismissed": set(),
    "completed": set(),
    "expired": set(),
}


@dataclass(frozen=True)
class RefreshSummary:
    created: int
    updated: int
    unchanged: int
    expired: int
    suppressed: list[SuppressedRule]
    engine: EngineResult


def stable_recommendation_id(customer_id: str, outcome: RuleOutcome, period_key: str) -> uuid.UUID:
    key = f"{customer_id}|{outcome.rule_id}|{outcome.rule_version}|{outcome.subject_key}|{period_key}"
    return uuid.uuid5(RECOMMENDATION_NAMESPACE, key)


def _aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def ensure_rules(session: Session) -> None:
    """Make sure every rule version the engine can emit exists (FK target)."""
    existing = {(r.rule_id, r.version) for r in session.scalars(select(RecommendationRule))}
    for rule in RULES.values():
        if (rule.rule_id, rule.version) not in existing:
            session.add(
                RecommendationRule(
                    rule_id=rule.rule_id,
                    version=rule.version,
                    category=rule.category,
                    name=rule.name,
                    description=rule.description,
                    parameters=json.loads(_canonical(rule.parameters)),
                )
            )
    session.flush()


def refresh_for_customer(
    session: Session, customer: Profile, as_of: date, actor_profile_id: uuid.UUID | None
) -> RefreshSummary:
    data = load_financial_data(session, customer)
    analytics = compute_analytics(data, as_of)
    result = evaluate(data, analytics, as_of)
    ensure_rules(session)

    now = utc_now()
    # Subjects the customer already acted on (accepted, or dismissed recently) are not re-raised
    # as new pending items in a later period; this prevents duplicate active recommendations.
    decided = {
        (r.rule_id, r.subject_key)
        for r in session.scalars(
            select(Recommendation).where(
                Recommendation.customer_id == customer.id, Recommendation.status.in_(["accepted", "dismissed"])
            )
        )
        if r.status == "accepted"
        or (r.status_changed_at is not None and (now - _aware(r.status_changed_at)).days < DISMISSAL_RESPECT_DAYS)
    }
    produced: set[uuid.UUID] = set()
    created = updated = unchanged = 0
    for outcome in result.outcomes:
        text = explain(outcome)
        rec_id = stable_recommendation_id(data.customer_id, outcome, result.period_key)
        produced.add(rec_id)
        if session.get(Recommendation, rec_id) is None and (outcome.rule_id, outcome.subject_key) in decided:
            unchanged += 1
            continue
        evidence = json.loads(_canonical(outcome.evidence))
        payload = {
            "title": text.title,
            "explanation": text.explanation,
            "reason": text.reason,
            "priority": outcome.priority,
            "priority_reason": outcome.priority_reason,
            "evidence": evidence,
            "assumptions": list(outcome.assumptions),
            "suggested_actions": list(outcome.actions),
            "confidence": result.confidence,
            "confidence_reason": result.confidence_reason,
        }
        evidence_hash = hashlib.sha256(_canonical(payload).encode()).hexdigest()
        existing = session.get(Recommendation, rec_id)
        if existing is None:
            session.add(
                Recommendation(
                    id=rec_id,
                    customer_id=customer.id,
                    rule_id=outcome.rule_id,
                    rule_version=outcome.rule_version,
                    category=outcome.category,
                    subject_key=outcome.subject_key,
                    period_key=result.period_key,
                    data_as_of=result.data_as_of,
                    analytics_as_of=as_of,
                    evidence_hash=evidence_hash,
                    status="pending",
                    created_at=now,
                    updated_at=now,
                    **payload,
                )
            )
            created += 1
        elif existing.status == "pending" and existing.evidence_hash != evidence_hash:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.evidence_hash = evidence_hash
            existing.data_as_of = result.data_as_of
            existing.analytics_as_of = as_of
            existing.updated_at = now
            updated += 1
        else:
            unchanged += 1  # accepted/dismissed/completed decisions are never overwritten

    expired = 0
    stale_pending = session.scalars(
        select(Recommendation).where(Recommendation.customer_id == customer.id, Recommendation.status == "pending")
    )
    for rec in stale_pending:
        if rec.id not in produced:
            rec.status = "expired"
            rec.status_changed_at = now
            rec.updated_at = now
            expired += 1

    record_audit(
        session,
        actor_profile_id=actor_profile_id,
        customer_id=customer.id,
        action="recommendations.refreshed",
        entity_type="customer",
        entity_id=str(customer.id),
        metadata={
            "created": created,
            "updated": updated,
            "expired": expired,
            "as_of": as_of.isoformat(),
            "rule_versions": {r.rule_id: r.version for r in RULES.values()},
        },
    )
    session.commit()
    return RefreshSummary(
        created=created,
        updated=updated,
        unchanged=unchanged,
        expired=expired,
        suppressed=result.suppressed,
        engine=result,
    )


def list_recommendations(
    session: Session, customer_id: uuid.UUID, statuses: list[str] | None, offset: int, limit: int
) -> tuple[list[Recommendation], int]:
    query = select(Recommendation).where(Recommendation.customer_id == customer_id)
    if statuses:
        query = query.where(Recommendation.status.in_(statuses))
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    priority_rank = case({"high": 0, "medium": 1, "low": 2}, value=Recommendation.priority)
    rows = session.scalars(
        query.order_by(
            Recommendation.period_key.desc(), priority_rank, Recommendation.rule_id, Recommendation.subject_key
        )
        .offset(offset)
        .limit(limit)
    ).all()
    return list(rows), int(total)


def has_any_recommendations(session: Session, customer_id: uuid.UUID) -> bool:
    return (
        session.scalar(select(Recommendation.id).where(Recommendation.customer_id == customer_id).limit(1)) is not None
    )


def expire_pending(session: Session, customer_id: uuid.UUID) -> int:
    """Expire all pending recommendations (e.g. when consent is withdrawn). Caller commits."""
    now = utc_now()
    count = 0
    for rec in session.scalars(
        select(Recommendation).where(Recommendation.customer_id == customer_id, Recommendation.status == "pending")
    ):
        rec.status = "expired"
        rec.status_changed_at = now
        rec.updated_at = now
        count += 1
    return count


class InvalidTransitionError(ValueError):
    pass


def apply_feedback(
    session: Session,
    rec: Recommendation,
    *,
    actor_profile_id: uuid.UUID,
    action: str,
    reason_code: str | None,
    comment: str | None,
) -> RecommendationFeedback:
    if action in FEEDBACK_TO_STATUS:
        target = FEEDBACK_TO_STATUS[action]
        if target not in ALLOWED_TRANSITIONS[rec.status]:
            raise InvalidTransitionError(f"Cannot change a {rec.status} recommendation to {target}.")
        rec.status = target
        rec.status_changed_at = utc_now()
        rec.updated_at = rec.status_changed_at
    feedback = RecommendationFeedback(
        recommendation_id=rec.id,
        customer_id=rec.customer_id,
        submitted_by_profile_id=actor_profile_id,
        action=action,
        reason_code=reason_code,
        comment=comment,
        created_at=utc_now(),
    )
    session.add(feedback)
    # The free-text comment is deliberately not copied into the audit log.
    record_audit(
        session,
        actor_profile_id=actor_profile_id,
        customer_id=rec.customer_id,
        action=f"recommendation.feedback.{action}",
        entity_type="recommendation",
        entity_id=str(rec.id),
        metadata={"reason_code": reason_code, "new_status": rec.status, "rule_id": rec.rule_id},
    )
    session.commit()
    return feedback


def feedback_for(session: Session, recommendation_id: uuid.UUID) -> list[RecommendationFeedback]:
    return list(
        session.scalars(
            select(RecommendationFeedback)
            .where(RecommendationFeedback.recommendation_id == recommendation_id)
            .order_by(RecommendationFeedback.created_at)
        )
    )
