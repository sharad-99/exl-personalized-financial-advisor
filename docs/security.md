# Security

This is an academic demo on **synthetic data**. The controls below are implemented and tested, but the system
has **not** been penetration-tested or audited and is **not** production-ready for real customer data. Section 13
lists the known gaps.

## 1. Threat model (summary)

| Asset | Threats | Primary controls |
|---|---|---|
| Customer financial records | Customer A reading or modifying customer B's data; anonymous access; direct database access with public keys | Central API authorisation (`load_customer_for`), 404 on foreign IDs, RLS with `FORCE`, composite ownership FK |
| Access tokens | Theft through XSS, tokens in logs, token forgery | httpOnly cookies, BFF proxy (the browser never holds tokens), JWT signature, issuer, audience and expiry checks, log redaction |
| State-changing actions | CSRF, advisor tampering | Same-origin check on route handlers, bearer-only API with `allow_credentials=False`, advisor writes return 403 |
| Availability | Brute force, oversized payloads, slow requests, runaway queries | Rate limits, 64 KB body cap, 15 s request timeout, 10 s PostgreSQL `statement_timeout` |
| Secrets | Committed credentials, service-role key exposure | `.env` git-ignored, no defaults for secrets, config validation, backend uses a least-privilege DB role |
| Audit trail | Tampering, leaking sensitive text | Append-only trigger, INSERT/SELECT-only grant, no free text or tokens in metadata |

Out of scope: real banking integrations, real personal data, payment execution.

## 2. Authentication modes (`backend/app/core/config.py`, `core/security.py`)

| Mode | Use | How |
|---|---|---|
| `AUTH_MODE=local` | **Development and demo only** | `POST /api/v1/auth/local/login` checks the shared `LOCAL_DEMO_PASSWORD` in constant time (`hmac.compare_digest`) for a seeded synthetic profile. It issues an HS256 JWT signed with `LOCAL_JWT_SECRET` (at least 32 characters) with `iss=exl-local-dev`, `aud=exl-api`, `sub=<auth_user_id>`, `iat`, `nbf`, `exp` (default TTL 480 minutes, allowed range 5–1440) and a `jti` |
| `AUTH_MODE=supabase` | Deployments | Supabase Auth issues the tokens. The backend verifies them: **RS256 or ES256** through the project's JWKS (`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`, keys cached for 10 minutes, 5 s fetch timeout), or **HS256** with `SUPABASE_JWT_SECRET` for projects that still use legacy shared-secret signing. Issuer must equal `<SUPABASE_URL>/auth/v1`. Audience must equal `SUPABASE_JWT_AUDIENCE` (default `authenticated`) |

What the configuration enforces at start-up (`Settings._validate_security`):
- `ENVIRONMENT=production` requires `AUTH_MODE=supabase`. Local login is impossible in production, and the login
  route also returns 404 there.
- Production requires a PostgreSQL `DATABASE_URL` (no SQLite) and `https` CORS origins.
- `AUTH_MODE=local` requires `LOCAL_JWT_SECRET` of at least 32 characters and `LOCAL_DEMO_PASSWORD` of at least
  8 characters.
- `AUTH_MODE=supabase` requires `SUPABASE_URL`.
- `CORS_ALLOWED_ORIGINS` must not contain `*`.

What token verification enforces:
- The claims `exp`, `sub` and `aud` must be present.
- Only HS256 is accepted in local mode. Algorithms outside the allowed set, including `none`, are rejected.
- Expired tokens get "Access token expired". `sub` must be a UUID.
- Tokens are read only from the `Authorization` header.

### Profile linking (`profiles.auth_user_id`)
After verifying a token, the API loads the profile whose `auth_user_id` equals the token's `sub`. A valid token
with no linked profile gets **403**. Supabase users are therefore not automatically customers. An administrator
links each one by running SQL as the database owner (Supabase SQL editor):

```sql
-- 1. Find the Supabase user id (Authentication > Users, or):
select id, email from auth.users where email = 'demo.customer@example.com';

-- 2. Link it to a seeded synthetic profile:
update public.profiles
   set auth_user_id = '<supabase-user-uuid>'
 where email = 'customer01@demo.exl.test';

-- Advisor demo account:
update public.profiles
   set auth_user_id = '<supabase-user-uuid>'
 where email = 'advisor@demo.exl.test';
```

`auth_user_id` is UNIQUE, so one Supabase user maps to exactly one profile. Re-seeding with `--reset` recreates
the synthetic profiles with generated `auth_user_id` values, so the link SQL has to be re-run afterwards.

## 3. Authorisation model (`backend/app/api/deps.py`)

- **Customer:** may read and modify only their own record. `load_customer_for` returns **404** ("Customer not
  found" or "Recommendation not found") for another customer's ID, so the API never confirms that the record
  exists. Goals are always looked up by `(customer_id, goal_id)`, so a goal ID from another customer is also a 404.
- **Advisor** (a demo analyst concept): may read all synthetic customers. Any customer write (goal create or
  update, refresh, feedback) returns **403**.
- The `GET /customers` list is restricted to the caller for customers.
- The same rule is enforced in the database by RLS (section 10).

## 4. Browser session and CSRF (`frontend/src/lib/server/session.ts`, route handlers)

- **Local mode:** the token is stored in the `exl_session` cookie with `httpOnly`, `SameSite=Lax`, `path=/`,
  `Secure` when `NODE_ENV=production`, and `maxAge` equal to the token TTL. Browser JavaScript cannot read it.
- **Supabase mode:** `@supabase/ssr` manages the session cookies. The proxy validates the user with
  `auth.getUser()` (a call to the Auth server) before it uses the session's access token.
- **CSRF:** `POST /api/auth/login`, `POST /api/auth/logout`, and every non-GET call through
  `/api/backend/[...path]` require an `Origin` header whose host matches `x-forwarded-host` or `host`. Otherwise
  the response is 403. Together with `SameSite=Lax` and an API that accepts only bearer tokens, cross-site requests
  cannot trigger writes.
- **Open-redirect guard:** after login, the `next` parameter is used only if it starts with `/` and not with `//`
  (`safeNext` in `login-form.tsx`). Anything else goes to `/dashboard`.
- **Path allowlist:** the BFF forwards only paths that match an explicit regular expression of known API routes
  with UUID-shaped IDs. It returns 404 for everything else, so it cannot be used to reach other backend paths.
- **Timeouts and limits:** the BFF has a 15 s upstream timeout and rejects bodies over 32,768 characters.
- `frontend/src/proxy.ts` only redirects visitors without a session to `/login`. Real authorisation is done by
  the backend on every call.

## 5. CORS (`main.py`)

- Explicit origins come from `CORS_ALLOWED_ORIGINS`. `*` is rejected at start-up, and production origins must use
  `https`.
- `allow_credentials=False`, because the API uses bearer tokens and never cookies.
- Methods are GET, POST, PATCH and OPTIONS. Headers are `Authorization`, `Content-Type` and `X-Request-ID`.
- Because the browser normally talks only to the same-origin BFF, CORS matters only for direct API clients.

## 6. Security headers

| Layer | Headers |
|---|---|
| Backend | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `X-Request-ID`. `Cache-Control: no-store` on `/api/*`. `Strict-Transport-Security: max-age=63072000; includeSubDomains` in production |
| Frontend (`next.config.ts`) | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`. `X-Powered-By` is turned off. BFF responses carry `Cache-Control: no-store` |

## 7. Input handling and resource limits

- **Request models:** Pydantic models with `extra="forbid"`, whitespace stripping, length, range and pattern
  limits, and no control characters in goal names. Money is limited to 14 digits and 2 decimal places.
- **Validation errors:** these return location, message and type only, never the submitted values
  (`test_validation_errors_do_not_echo_input`).
- **SQL:** all SQL is built with SQLAlchemy expressions and bound parameters. Search patterns are bound and never
  interpolated (`test_injection_style_input_is_treated_as_data`).
- **Body size:** a `Content-Length` over 65,536 bytes gets **413**.
- **Timeout:** requests are limited to 15 s (`REQUEST_TIMEOUT_SECONDS`) and return **504** when exceeded.
- **Database timeouts:** PostgreSQL has a 10 s `statement_timeout`, a 10 s connect timeout, and a small pool
  (5 connections plus 5 overflow).
- **Database errors:** these map to **503** without internal details. Integrity violations map to **409**.

## 8. Rate limiting (`core/security.py`, `api/deps.py`)

- Local login is limited to **5 per minute** per client IP and email.
- Goals (create and update), recommendation refresh, and feedback are limited to **20 per minute**
  (`RATE_LIMIT_SENSITIVE_PER_MINUTE`) per bucket.
- Exceeding a limit returns **429** with `Retry-After`.
- The limiter is an in-memory sliding window, guarded by a lock and bounded to 10,000 keys.

**Limitations:**
- State is per process. Multiple instances or workers each keep their own counters, and a restart resets them.
  Running more than one instance needs a shared store such as Redis.
- The sensitive buckets (refresh, goals, feedback) depend on the authenticated principal and are keyed by the
  user's profile ID, so users behind the same proxy IP do not share a bucket.
- The login limit's IP component is likewise the BFF's IP when login goes through the frontend. In practice the
  limit is per email address.

## 9. Logging, audit and data minimisation

- **Logging:** JSON logs go to stdout (`core/logging.py`). The access log records only method, path (no query
  string), status, duration and request ID. Uvicorn's access log is turned off because it would print query strings.
- **Redaction:** `redact()` masks `Bearer <token>`, any JWT-shaped string, and `password=`, `secret=`, `token=` and
  `api_key=` values in messages and exception text. The extra fields `authorization`, `password` and `token` are
  dropped.
- **Never logged or audited:** access tokens, passwords, transaction descriptions, and feedback comments. The
  comment is stored only in `recommendation_feedback`.
- **Audit events:** `audit_events` records the actor, customer, action, entity and request ID. It is append-only
  (a trigger blocks UPDATE and DELETE) and has no foreign keys, so history cannot be cascaded away.
- **Responses:** never include `auth_user_id`, secrets, or the demo password
  (`test_privileged_values_never_returned`).

## 10. Database: RLS and least-privilege role

- All 12 tables have `ENABLE` and `FORCE ROW LEVEL SECURITY`.
- `anon` has no privileges.
- `authenticated` (a Supabase client with a user JWT) can only `SELECT` its own rows, through
  `customer_id = current_profile_id()`. An advisor can read everything except `data_quality_events` and
  `audit_events`. There are no write grants.
- The backend connects as the **`exl_api`** role. It has SELECT, INSERT and UPDATE on the entity tables, SELECT
  and INSERT only on `recommendation_feedback` and `audit_events`, and **no DELETE**.
- The migration creates `exl_api` as `NOLOGIN`. Enable it per environment with a strong, unique password, as the
  database owner:

```sql
alter role exl_api with login password '<generate-a-long-random-password>';
-- On Supabase, use the pooled connection string with user exl_api.<project-ref>, e.g.
-- postgresql://exl_api.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

Run migrations and seeding as the owner role, not as `exl_api`. Seeding with `--reset` needs DELETE.

## 11. Secrets handling

- Real values go only in `backend/.env` and `frontend/.env.local`. Both are git-ignored (`.env`, `.env.*`) and
  are never committed. The `*.example` templates contain placeholders only. `make env` generates random local
  secrets.
- There are no default values for secrets in code: `local_jwt_secret`, `local_demo_password` and
  `supabase_jwt_secret` are `SecretStr | None`, and the configuration validation fails if they are missing where
  they are required.
- The frontend receives only `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. Both are
  public by design and protected by RLS. **The Supabase service-role key is never used by the frontend or the
  backend.**
- The backend connects through a PostgreSQL connection string for the least-privilege `exl_api` role.
  `API_BASE_URL` is server-only.
- CI uses throwaway, clearly labelled test-only values.

## 12. Security tests (`backend/tests/security`, 34 test cases)

`test_authorization.py` (8 functions, 23 cases):
- `test_every_protected_route_requires_authentication`: parametrised over all 16 protected `/api` operations
  from OpenAPI. Each must return 401 with `WWW-Authenticate: Bearer`.
- `test_invalid_tokens_rejected`: garbage, wrong-secret and expired tokens (`alg=none` is covered in the
  unit tests).
- `test_valid_token_without_profile_is_forbidden`: 403.
- `test_customer_a_cannot_read_customer_b`: 404 on every read sub-resource.
- `test_customer_a_cannot_modify_customer_b`
- `test_goal_id_from_another_customer_is_not_reachable_via_own_path`
- `test_feedback_on_another_customers_recommendation_rejected`
- `test_advisor_is_read_only`

`test_hardening.py` (11 cases):
- `test_privileged_values_never_returned`
- `test_wrong_password_and_unknown_user_look_identical`
- `test_login_rate_limited`
- `test_refresh_rate_limited`
- `test_local_login_disabled_in_supabase_mode`
- `test_injection_style_input_is_treated_as_data`
- `test_oversized_body_rejected`
- `test_validation_errors_do_not_echo_input`
- `test_cors_allows_only_configured_origins`
- `test_security_headers_present`
- `test_audit_log_has_no_free_text_or_tokens`

Related tests elsewhere:
- `tests/unit/test_config_and_tokens.py`: production config rejection, wildcard CORS and weak-secret rejection,
  token round trip, invalid claims, wrong secret and `alg=none`, Supabase HS256 issuer and audience, the rate
  limiter, and log redaction.
- `tests/integration/test_postgres.py`: `test_row_level_security_isolates_customers` and
  `test_audit_events_are_append_only`.

## 13. Remaining limitations (honest list)

1. **Rate limiter** is in-memory and per process (keyed per user for sensitive routes; per IP + email for
   login). It is not suitable for multiple instances.
2. **No MFA**, no account lockout beyond rate limiting, and no password policy in local mode.
3. **Local demo login uses one shared password** (`LOCAL_DEMO_PASSWORD`) for every synthetic user. It is meant
   only for local demos and is blocked in production.
4. **Advisor is a demo concept.** There is no advisor-to-customer assignment, no consent-scoped access, and no
   access review. A real bank would need relationship-based access, supervision and logging of every read.
5. **Reads are not audited.** Only logins, consent changes, goal changes, refreshes and feedback are audited.
6. **No field-level encryption.** The application relies on the database provider's encryption at rest and on
   TLS in transit (verify the provider's settings).
7. **No Content-Security-Policy** is configured on the frontend, and no HSTS header is set by Next.js itself
   (the hosting platform may add one).
8. **No automated dependency or vulnerability scanning in CI** beyond running `npm audit` manually. There is no
   SAST, no container scanning, and no secret scanning hook.
9. **Body-size check depends on `Content-Length`.** A chunked request without that header is not counted before
   it is parsed. Request bodies are small Pydantic models, which limits the impact.
10. **Request timeout does not cancel work.** Synchronous handlers run in a thread pool, so a 504 is returned but
    the thread can keep running until the database `statement_timeout` stops it.
11. **Re-seeding breaks Supabase links.** Profile links have to be maintained manually with SQL (section 2).
12. **No penetration test or formal threat-model review** has been performed. Nothing has been deployed.
13. Withdrawing consent stops **new** insights immediately. Already-stored pending items stay visible until the
    next refresh expires them (the settings page tells the user to re-check).
