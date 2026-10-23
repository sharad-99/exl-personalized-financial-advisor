"""Authentication primitives.

Two modes, chosen by AUTH_MODE:
  * supabase: verify Supabase Auth access tokens (asymmetric keys via JWKS, or the
    legacy HS256 project secret), audience 'authenticated'.
  * local: development-only HS256 tokens issued by /api/v1/auth/local/login for
    seeded SYNTHETIC demo users. Rejected at start-up when ENVIRONMENT=production.

Tokens are only ever read from the Authorization header and never logged.
"""

from __future__ import annotations

import hmac
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from app.core.config import Settings
from app.utils.dates import utc_now

LOCAL_ISSUER = "exl-local-dev"
LOCAL_AUDIENCE = "exl-api"
ALLOWED_ASYMMETRIC_ALGS = ["RS256", "ES256"]


class AuthenticationError(Exception):
    """Raised for any token problem; the message is safe to show to clients."""


@dataclass(frozen=True)
class Principal:
    profile_id: uuid.UUID
    role: str  # customer | advisor
    auth_subject: uuid.UUID

    @property
    def is_advisor(self) -> bool:
        return self.role == "advisor"


def issue_local_token(settings: Settings, auth_subject: uuid.UUID, role: str) -> tuple[str, int]:
    if settings.auth_mode != "local" or settings.local_jwt_secret is None:
        raise AuthenticationError("Local login is disabled")
    ttl = settings.local_token_ttl_minutes * 60
    now = utc_now()
    token = jwt.encode(
        {
            "sub": str(auth_subject),
            "role": "authenticated",
            "app_role": role,
            "iss": LOCAL_ISSUER,
            "aud": LOCAL_AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(seconds=ttl),
            "jti": str(uuid.uuid4()),
        },
        settings.local_jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    return token, ttl


def verify_password(supplied: str, expected: str) -> bool:
    return hmac.compare_digest(supplied.encode(), expected.encode())


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, lifespan=600, timeout=5)


def decode_access_token(settings: Settings, token: str) -> uuid.UUID:
    """Validate a bearer token and return the auth subject (user id)."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Malformed access token") from exc
    alg = header.get("alg")
    options = {"require": ["exp", "sub", "aud"]}
    try:
        if settings.auth_mode == "local":
            if alg != "HS256" or settings.local_jwt_secret is None:
                raise AuthenticationError("Unsupported token")
            claims = jwt.decode(
                token,
                settings.local_jwt_secret.get_secret_value(),
                algorithms=["HS256"],
                audience=LOCAL_AUDIENCE,
                issuer=LOCAL_ISSUER,
                options=options,
            )
        elif alg == "HS256":
            if settings.supabase_jwt_secret is None:
                raise AuthenticationError("Unsupported token")
            claims = jwt.decode(
                token,
                settings.supabase_jwt_secret.get_secret_value(),
                algorithms=["HS256"],
                audience=settings.supabase_jwt_audience,
                issuer=settings.supabase_issuer,
                options=options,
            )
        elif alg in ALLOWED_ASYMMETRIC_ALGS and settings.supabase_jwks_url:
            signing_key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=ALLOWED_ASYMMETRIC_ALGS,
                audience=settings.supabase_jwt_audience,
                issuer=settings.supabase_issuer,
                options=options,
            )
        else:
            raise AuthenticationError("Unsupported token")
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid access token") from exc
    try:
        return uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise AuthenticationError("Invalid token subject") from exc


class RateLimiter:
    """In-process sliding-window limiter.

    Adequate for a single-instance pilot. A multi-instance deployment needs a
    shared store (e.g. Redis) — documented in docs/security.md.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: float = 60.0) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = int(window_seconds - (now - bucket[0])) + 1
                return False, retry_after
            bucket.append(now)
            if len(self._hits) > 10_000:  # bound memory
                for stale in [k for k, v in self._hits.items() if not v]:
                    del self._hits[stale]
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter()
