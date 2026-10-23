from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.models.tables import AuditEvent


def record_audit(
    session: Session,
    *,
    actor_profile_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append an audit event in the caller's transaction. Metadata must not contain secrets or
    free-text transaction descriptions."""
    session.add(
        AuditEvent(
            actor_profile_id=actor_profile_id,
            customer_id=customer_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request_id_var.get(),
            metadata_=metadata or {},
        )
    )
