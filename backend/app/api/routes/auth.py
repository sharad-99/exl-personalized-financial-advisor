from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import AppSettings, CurrentPrincipal, DbSession
from app.core.errors import ApiError
from app.core.security import issue_local_token, rate_limiter, verify_password
from app.repositories import customers as repo
from app.repositories.audit import record_audit
from app.schemas.api import ConsentIn, LocalLoginIn, MeOut, TokenOut
from app.services.recommendation_service import expire_pending
from app.utils.dates import utc_now

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post(
    "/auth/local/login",
    response_model=TokenOut,
    summary="DEVELOPMENT ONLY: sign in as a seeded synthetic demo user",
    responses={
        401: {"description": "Invalid credentials"},
        404: {"description": "Disabled"},
        429: {"description": "Rate limited"},
    },
)
def local_login(body: LocalLoginIn, request: Request, session: DbSession, settings: AppSettings) -> TokenOut:
    if settings.auth_mode != "local" or settings.environment == "production":
        raise ApiError(404, "Not found")
    client = request.client.host if request.client else "unknown"
    allowed, retry = rate_limiter.hit(f"login:{client}:{body.email.lower()}", settings.rate_limit_login_per_minute)
    if not allowed:
        raise ApiError(429, "Too many login attempts; please retry later", headers={"Retry-After": str(retry)})
    profile = repo.get_profile_by_email(session, body.email)
    password = settings.local_demo_password.get_secret_value() if settings.local_demo_password else ""
    password_ok = verify_password(body.password, password)
    if profile is None or profile.auth_user_id is None or not profile.is_synthetic or not password_ok:
        raise ApiError(401, "Invalid email or password")
    token, ttl = issue_local_token(settings, profile.auth_user_id, profile.role)
    record_audit(
        session,
        actor_profile_id=profile.id,
        customer_id=profile.id if profile.role == "customer" else None,
        action="auth.local_login",
        entity_type="profile",
        entity_id=str(profile.id),
    )
    session.commit()
    return TokenOut(access_token=token, expires_in=ttl)


def _me(profile) -> MeOut:  # type: ignore[no-untyped-def]
    return MeOut(
        profile_id=profile.id,
        role=profile.role,
        display_name=profile.display_name,
        email=profile.email,
        customer_id=profile.id if profile.role == "customer" else None,
        is_synthetic=profile.is_synthetic,
        data_sharing_consent=profile.data_sharing_consent,
        marketing_consent=profile.marketing_consent,
        consent_updated_at=profile.consent_updated_at,
    )


@router.get("/me", response_model=MeOut, summary="Current user profile and consent settings")
def me(principal: CurrentPrincipal, session: DbSession) -> MeOut:
    profile = repo.get_profile(session, principal.profile_id)
    if profile is None:  # pragma: no cover - principal resolution guarantees a profile
        raise ApiError(404, "Profile not found")
    return _me(profile)


@router.patch("/me/consent", response_model=MeOut, summary="Update privacy and consent preferences")
def update_consent(body: ConsentIn, principal: CurrentPrincipal, session: DbSession) -> MeOut:
    profile = repo.get_profile(session, principal.profile_id)
    if profile is None:  # pragma: no cover
        raise ApiError(404, "Profile not found")
    changes = {}
    if body.data_sharing_consent is not None:
        profile.data_sharing_consent = body.data_sharing_consent
        changes["data_sharing_consent"] = body.data_sharing_consent
        if not body.data_sharing_consent:
            changes["expired_recommendations"] = expire_pending(session, profile.id)
    if body.marketing_consent is not None:
        profile.marketing_consent = body.marketing_consent
        changes["marketing_consent"] = body.marketing_consent
    profile.consent_updated_at = utc_now()
    record_audit(
        session,
        actor_profile_id=profile.id,
        customer_id=profile.id if profile.role == "customer" else None,
        action="consent.updated",
        entity_type="profile",
        entity_id=str(profile.id),
        metadata=changes,
    )
    session.commit()
    return _me(profile)
