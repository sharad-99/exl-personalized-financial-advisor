import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import redact
from app.core.security import (
    LOCAL_AUDIENCE,
    LOCAL_ISSUER,
    AuthenticationError,
    RateLimiter,
    decode_access_token,
    issue_local_token,
)

SECRET = "unit-test-secret-that-is-definitely-long-enough"


def local_settings(**overrides) -> Settings:  # type: ignore[no-untyped-def]
    values = {
        "auth_mode": "local",
        "local_jwt_secret": SECRET,
        "local_demo_password": "demo-pass-123",
        "database_url": "sqlite:///:memory:",
        "environment": "test",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_production_rejects_local_auth_and_sqlite() -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE=supabase"):
        local_settings(environment="production")
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(
            _env_file=None,
            environment="production",
            auth_mode="supabase",  # type: ignore[call-arg]
            supabase_url="https://x.supabase.co",
            database_url="sqlite:///x.db",
            cors_allowed_origins="https://app.example.com",
        )


def test_wildcard_cors_and_weak_secret_rejected() -> None:
    with pytest.raises(ValidationError, match="explicit origins"):
        local_settings(cors_allowed_origins="*")
    with pytest.raises(ValidationError, match="LOCAL_JWT_SECRET"):
        local_settings(local_jwt_secret="short")


def test_cors_origins_parsed_from_comma_list() -> None:
    settings = local_settings(cors_allowed_origins="http://localhost:3000, https://demo.example.com/")
    assert settings.cors_allowed_origins == ["http://localhost:3000", "https://demo.example.com"]


def test_local_token_round_trip() -> None:
    settings = local_settings()
    subject = uuid.uuid4()
    token, ttl = issue_local_token(settings, subject, "customer")
    assert ttl == 480 * 60
    assert decode_access_token(settings, token) == subject


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: {**c, "exp": datetime.now(UTC) - timedelta(minutes=1)},
        lambda c: {**c, "aud": "someone-else"},
        lambda c: {**c, "iss": "evil"},
    ],
)
def test_invalid_claims_rejected(mutate) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    claims = {"sub": str(uuid.uuid4()), "aud": LOCAL_AUDIENCE, "iss": LOCAL_ISSUER, "exp": now + timedelta(hours=1)}
    token = jwt.encode(mutate(claims), SECRET, algorithm="HS256")
    with pytest.raises(AuthenticationError):
        decode_access_token(local_settings(), token)


def test_wrong_secret_and_alg_none_rejected() -> None:
    claims = {
        "sub": str(uuid.uuid4()),
        "aud": LOCAL_AUDIENCE,
        "iss": LOCAL_ISSUER,
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    forged = jwt.encode(claims, "another-secret-that-is-also-long-enough-xx", algorithm="HS256")
    unsigned = jwt.encode(claims, None, algorithm="none")  # type: ignore[arg-type]
    for token in (forged, unsigned, "not-a-jwt"):
        with pytest.raises(AuthenticationError):
            decode_access_token(local_settings(), token)


def test_supabase_hs256_tokens_verified_with_issuer_and_audience() -> None:
    settings = Settings(
        _env_file=None,
        auth_mode="supabase",
        supabase_url="https://abc.supabase.co",  # type: ignore[call-arg]
        supabase_jwt_secret=SECRET,
        database_url="sqlite:///:memory:",
    )
    subject = uuid.uuid4()
    good = jwt.encode(
        {
            "sub": str(subject),
            "aud": "authenticated",
            "iss": "https://abc.supabase.co/auth/v1",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        SECRET,
        algorithm="HS256",
    )
    assert decode_access_token(settings, good) == subject
    wrong_issuer = jwt.encode(
        {
            "sub": str(subject),
            "aud": "authenticated",
            "iss": "https://evil.example/auth/v1",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(settings, wrong_issuer)
    with pytest.raises(AuthenticationError):
        issue_local_token(settings, subject, "customer")


def test_rate_limiter_blocks_after_limit() -> None:
    limiter = RateLimiter()
    assert all(limiter.hit("k", 3)[0] for _ in range(3))
    allowed, retry_after = limiter.hit("k", 3)
    assert not allowed and retry_after >= 1
    assert limiter.hit("other", 3)[0]


def test_log_redaction() -> None:
    token = jwt.encode({"sub": "x"}, SECRET, algorithm="HS256")
    text = redact(f"Authorization: Bearer {token} password=hunter2 token: abc")
    assert token not in text
    assert "hunter2" not in text
    assert "[REDACTED]" in text
