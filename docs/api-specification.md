# API Specification

Base path: `/api/v1`, plus `/health`. The API runs on FastAPI and the source of truth is the code in
`backend/app/api/routes/*.py`, `backend/app/schemas/api.py` and `backend/app/schemas/analytics.py`.

- **OpenAPI.** The schema is served at `/openapi.json` in every environment. The interactive Swagger UI (`/docs`)
  and ReDoc (`/redoc`) are available only when `ENVIRONMENT` is not `production`.
- **Data.** All data is synthetic. Customer and analytics responses carry `is_synthetic` or `is_synthetic_data` flags.
- **Browser access.** Browsers call these endpoints only through the Next.js proxy at `/api/backend/<path>`. The
  proxy forwards to `/api/v1/<path>` and adds the bearer token (see `architecture.md`).

## 1. Conventions

### Authentication
Every `/api/v1` endpoint except `POST /api/v1/auth/local/login` requires `Authorization: Bearer <access token>`.
The token is a Supabase Auth JWT, or a local dev-only token in local mode. After the token is verified, the
backend looks up the profile whose `auth_user_id` equals the token's `sub`.

| Situation | Status |
|---|---|
| Missing or malformed header, invalid, expired, or wrong-algorithm token | 401 `unauthenticated` with `WWW-Authenticate: Bearer` |
| Valid token but no linked profile | 403 `forbidden` ("No customer profile is linked to this account") |

### Authorisation
| Role | Read | Write |
|---|---|---|
| `customer` | Own record only. Another customer's ID returns **404** (existence is not disclosed) | Own goals, own recommendations (refresh, feedback), own consent |
| `advisor` (EXL analyst demo role) | All synthetic customers | **403** on customer writes: goals, refresh, feedback. An advisor may update their own consent via `/me/consent` |

### Money and numbers
- Money is serialised as a **JSON string with two decimal places**, for example `"12345.67"` (Pydantic `Decimal`).
  Clients must not parse money into binary floats for arithmetic.
- Money inputs are decimals with at most 14 digits and 2 decimal places. They can be sent as JSON strings or numbers.
- Percentages are decimal strings such as `"34.5"`. Values in `evidence` are strings too.
- A value that cannot be computed is returned as `null`, usually with a `status` or `reason`. It is never `0`.

### Pagination
List endpoints that paginate accept `page` (1–10,000, default 1) and `page_size` (1–200, default 50). A
`page_size` above 200 returns 422. The response looks like this:

```json
{ "items": [ ... ], "meta": { "page": 1, "page_size": 50, "total": 1234, "total_pages": 25 } }
```
`total_pages` is at least 1.

### Error envelope
Every error uses one shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "request_id": "3f2a...",
    "details": [ { "loc": ["body", "target_amount"], "msg": "...", "type": "..." } ]
  }
}
```
`details` appears only for request-validation errors. It contains location, message and type, and never echoes
the submitted values. Internal exception details are logged on the server and never returned. Every response
includes an `X-Request-ID` header. A client may supply its own ID (8–64 characters, alphanumeric or hyphen).

| Status | code | When |
|---|---|---|
| 401 | `unauthenticated` | No or invalid token; invalid local login |
| 403 | `forbidden` | Advisor write; token with no linked profile. From the Next.js proxy: cross-site non-GET request |
| 404 | `not_found` | Unknown or foreign customer, goal or recommendation; unknown route; local login in Supabase or production mode |
| 405 | `method_not_allowed` | Wrong method |
| 409 | `conflict` | Duplicate goal name; goal limit reached; invalid recommendation status transition; DB integrity violation |
| 413 | `payload_too_large` | `Content-Length` > 65,536 bytes (proxy: body > 32,768 characters) |
| 422 | `validation_error` | Schema or business validation |
| 429 | `rate_limited` | Rate limit exceeded. Includes `Retry-After` (seconds) |
| 500 | `internal_error` | Unhandled error (generic message) |
| 503 | `service_unavailable` | Database unavailable or SQLAlchemy error. From the proxy: backend unreachable |
| 504 | `timeout` | Request exceeded `REQUEST_TIMEOUT_SECONDS` (15 s default; proxy also 15 s) |

### Rate limits (in-memory, per process, 60-second sliding window)
| Endpoint | Limit | Key |
|---|---|---|
| `POST /auth/local/login` | `RATE_LIMIT_LOGIN_PER_MINUTE` = **5/min** | client IP + email |
| `POST .../recommendations/refresh` (bucket `refresh`) | `RATE_LIMIT_SENSITIVE_PER_MINUTE` = **20/min** | see note |
| `POST .../goals`, `PATCH .../goals/{id}` (shared bucket `goals`) | 20/min | see note |
| `POST /recommendations/{id}/feedback` (bucket `feedback`) | 20/min | see note |

Note: the sensitive limits (`deps.rate_limit`) depend on the authenticated principal, so each bucket is keyed
by the user's profile ID. Users behind the same Next.js proxy IP do not share a bucket
(`tests/security/test_hardening.py::test_rate_limits_are_per_user_not_shared`).

## 2. Endpoints

All paths below are under `/api/v1` unless shown otherwise. "C" means customer (own record only) and "A" means
advisor.

### Health

#### `GET /health` (public)
Reports liveness and database readiness. Returns 200 even when the database is down; in that case
`status` is `degraded`.
```json
{ "status": "ok", "version": "0.1.0", "environment": "development", "database": "ok", "auth_mode": "local" }
```
`status` is `ok` or `degraded`. `database` is `ok` or `unavailable`.

### Auth and profile

#### `POST /auth/local/login` (public, development only)
Signs in as a seeded synthetic user. Returns 404 unless `AUTH_MODE=local` and `ENVIRONMENT` is not `production`.

| Body field | Rules |
|---|---|
| email | 3–254 chars, pattern `^[^@\s]+@[^@\s]+\.[^@\s]+$` |
| password | 1–128 chars |

Unknown fields are rejected (422). The password is compared in constant time with `LOCAL_DEMO_PASSWORD`. The
profile must exist, be synthetic, and have an `auth_user_id`. Every failure returns the same
`401 Invalid email or password`. Limited to 5/min per IP and email. Writes the audit event `auth.local_login`.

Response 200: `{ "access_token": "...", "token_type": "bearer", "expires_in": 28800 }`. `expires_in` is
`LOCAL_TOKEN_TTL_MINUTES` × 60, with a default of 480 minutes.

#### `GET /me` (C, A)
Returns the current user's profile and consent settings (`MeOut`): `profile_id`, `role`, `display_name`,
`email`, `customer_id` (null for advisors), `is_synthetic`, `data_sharing_consent`, `marketing_consent`,
`consent_updated_at`. `auth_user_id` is never returned.

#### `PATCH /me/consent` (C, A; own profile)
Body: `{ "data_sharing_consent"?: bool, "marketing_consent"?: bool }`. At least one field is required, otherwise
422. Unknown fields are rejected. Sets `consent_updated_at`, writes the audit event `consent.updated`, and returns
`MeOut`. Withdrawing `data_sharing_consent` immediately expires every pending recommendation, and later refreshes suppress every rule ("Customer has not consented to personalised insights.").

### Customers

#### `GET /customers` (C, A), paginated
Lists customers visible to the caller. A customer sees only themselves.

| Query | Rules |
|---|---|
| search | 1–60 chars. Case-insensitive match on display name or email |
| segment | `^[a-z_]{3,40}$` (persona segment) |
| page, page_size | see Pagination |

Items (`CustomerSummary`): `id`, `display_name`, `persona_segment`, `income_pattern`, `is_synthetic`.

#### `GET /customers/{customer_id}` (C own, A)
Returns `CustomerDetail`:
- `id`, `display_name`, `is_synthetic`, `data_sharing_consent`
- `financial_profile`: persona, income pattern, `declared_monthly_income`, age band, dependents, city tier,
  risk preference, currency, `profile_updated_at`. Null if missing.
- `accounts[]`: `id`, `account_type`, `nickname`, `masked_number`, `currency`, `current_balance`,
  `balance_as_of`, `is_liquid`, `status`
- `obligations[]`
- `goals[]`: cancelled goals excluded
- `transaction_summary`: `transaction_count`, `first_transaction_date`, `last_transaction_date`

A malformed UUID returns 422. An unknown ID, or another customer's ID, returns 404.

#### `GET /customers/{customer_id}/obligations` (C own, A)
Returns `ObligationOut[]`: `id`, `obligation_type`, `name`, `amount`, `frequency`, `next_due_date`, `end_date`,
`is_essential`, `outstanding_principal`, `interest_rate_apr`, `status`.

#### `GET /customers/{customer_id}/data-quality-events` (C own, A)
Returns up to 100 recorded findings, newest first: `id`, `check_code`, `severity`, `details`, `detected_at`.

### Transactions

#### `GET /customers/{customer_id}/transactions` (C own, A), paginated
| Query | Rules |
|---|---|
| start_date, end_date | ISO dates. If both are given, `start_date <= end_date`, otherwise 422 |
| category | `^[a-z_]{3,30}$` (stored category) |
| direction | `credit` or `debit` |
| account_id | UUID |

Sorted by `posted_on` descending, then `external_ref` descending. Each item (`TransactionOut`) includes the
stored fields plus the classification computed over the customer's full history:
- `effective_category`
- `category_source`: `provided`, `keyword_rule`, or `fallback`
- `counted_as`: `income`, `expense`, `refund`, or `excluded`
- `exclusion_reason`: `internal_transfer`, `unmatched_transfer`, `probable_duplicate`, `reversed`, `reversal`,
  `orphan_reversal`, or null

### Analytics

#### `GET /customers/{customer_id}/analytics` (C own, A)
Computed on every request and never stored. Evaluated as of today's date in UTC.

| Query | Rules |
|---|---|
| months | 1–12, default 6. The last *n* complete calendar months before the current month |
| start_date, end_date | Optional, but both or neither (422 otherwise). `start_date <= end_date`. `end_date` not in the future. The span may cover at most 24 months |

Response (`AnalyticsResult`, money as strings):

| Field | Content |
|---|---|
| `customer_id`, `currency` (`INR`), `is_synthetic_data` | |
| `period` | `start_date`, `end_date`, `as_of`, `months_in_period`, `months_with_data` |
| `totals` | `total_income`, `total_expenses` (net of refunds), `refunds_netted`, `net_observed_cash_flow`, `excluded_internal_transfers`, `excluded_duplicates`, `excluded_reversal_pairs`, `note` |
| `monthly_averages` | `income`, `expenses`, `essential_expenses`, `discretionary_expenses`, `net_observed_cash_flow`, `basis_months`. Averages use only months that have data |
| `savings_rate` | `value_pct` or null, `status` (`calculated`, `insufficient_data`, `no_income`), `formula`, `reason` |
| `spending_by_category[]` | `category`, `group`, `amount`, `share_pct`, `transaction_count` |
| `monthly_trend[]` | One point per month from the period start to as_of, including the current partial month (`is_partial`) and `has_data` |
| `month_over_month[]` | `month`, `expenses`, `previous_expenses`, `change_amount`, `change_pct` |
| `recurring_expenses[]` | `merchant`, `category`, `average_amount`, `occurrences`, `months_observed`, `last_date`, `next_expected_date`, `is_subscription`, `amount_variation_pct` |
| `income_stability` | `months_with_income`, `coefficient_of_variation`, `pattern` (`stable`, `variable`, `insufficient_data`), `declared_monthly_income` |
| `balances` | `reported_liquid_balance`, `liquid_balance_status` (`fresh`, `stale`, `missing`), `credit_card_outstanding`, `accounts[]` (reported vs estimated balance, `reconciliation_difference`, `balance_is_stale`) |
| `emergency_fund` | `liquid_balance`, `average_monthly_essential_expenses`, `coverage_months`, `target_months`, `target_amount`, `gap_amount`, `status` (`sufficient`, `building`, `insufficient`, `unknown`), `reason`, `assumptions` |
| `savings_capacity` | `average_monthly_net_cash_flow`, `recent_3_month_net_cash_flow`, `non_monthly_obligation_provision`, `estimated_monthly_capacity`, `observed_monthly_transfers_to_savings`, `reason`, `calculation` |
| `upcoming_obligations` | `horizon_days` (30), `items[]`, `total_due` |
| `goals[]` | `GoalProgress` (see the goals endpoint) |
| `data_quality` | `latest_transaction_date`, `days_since_last_transaction`, `freshness` (`fresh`, `aging`, `stale`, `no_data`), `history_months`, `profile_age_days`, `balance_status`, `issues[]`, `confidence`, `confidence_reasons` |

Formulas are documented in `recommendation-engine.md`, section 9.

### Goals

#### `GET /customers/{customer_id}/goals` (C own, A)
Returns `[{ "goal": GoalOut, "plan": GoalProgress | null }]` for goals that are not cancelled.

- `GoalOut`: `id`, `name`, `goal_type`, `target_amount`, `saved_amount`, `monthly_contribution`, `target_date`,
  `priority`, `status`, `created_at`, `updated_at`.
- `plan` includes `remaining_amount`, `progress_pct`, `months_remaining`, `required_monthly`, `planned_monthly`,
  `plan_status` (`achieved`, `on_track`, `behind`, `no_target_date`, `overdue`, `inactive`),
  `projected_completion`, `suggested_increase`, `suggested_target_date`, `guidance`, `calculation`, `assumptions`.

#### `POST /customers/{customer_id}/goals` (C own; advisor gets 403). Rate-limited (`goals`).
| Field | Rules |
|---|---|
| name | 1–80 chars, no control characters, whitespace stripped. Must be unique per customer (case-insensitive) among non-cancelled goals, otherwise 409 |
| goal_type | `emergency_fund`, `home_purchase`, `education`, `retirement`, `vehicle`, `travel`, `wedding`, `debt_payoff`, `other` |
| target_amount | > 0, <= 100,000,000,000, 2 decimal places |
| saved_amount | >= 0, <= 100,000,000,000, default 0. Must not exceed `target_amount` (422) |
| monthly_contribution | null or 0 – 100,000,000 |
| target_date | null or a date strictly after today (422) |
| priority | 1–5, default 3 |

Unknown fields are rejected. A customer can have at most 20 non-cancelled goals; a 21st returns 409. The new
goal gets status `active`. Writes the audit event `goal.created` (metadata: `goal_type`). Returns 201 with `GoalOut`.

#### `PATCH /customers/{customer_id}/goals/{goal_id}` (C own; advisor gets 403). Rate-limited (`goals`).
All fields are optional: `name`, `target_amount`, `saved_amount`, `monthly_contribution`, `target_date`,
`priority`, and `status` (`active`, `achieved`, `paused`, `cancelled`). The same limits as POST apply.
`saved_amount > target_amount` is allowed only together with `status: "achieved"`. A goal that does not belong to
this customer returns 404. Writes the audit event `goal.updated` (metadata: the sorted names of the changed
fields). Returns `GoalOut`.

### Recommendations

#### `GET /customers/{customer_id}/recommendations` (C own, A), paginated
Query: `status` (repeatable; `pending`, `accepted`, `dismissed`, `completed`, `expired`), `page`, `page_size`.

**The first GET generates recommendations once.** If the customer has no stored recommendations at all, the
endpoint evaluates the rules as of today and stores the results before listing them. This happens even when an
advisor makes the call. Recommendation IDs are deterministic, so this step is idempotent and cannot create
duplicates. Later GETs never re-evaluate; use refresh for that.

Sorted by `period_key` descending, then priority (high to low), then `rule_id`, then `subject_key`.
Response: `{ "items": RecommendationOut[], "meta": PageMeta, "is_synthetic_data": true }`.

`RecommendationOut`:
- `id`, `customer_id`, `rule_id`, `rule_version`, `category`
- `title`, `explanation`, `reason`
- `priority` (`high`, `medium`, `low`), `priority_reason`
- `evidence`: `{ inputs, calculations, thresholds }`
- `assumptions[]`, `suggested_actions[]`
- `confidence`, `confidence_reason`
- `data_as_of`, `analytics_as_of`, `period_key`
- `status`, `status_changed_at`, `created_at`, `updated_at`

#### `POST /customers/{customer_id}/recommendations/refresh` (C own; advisor gets 403). Rate-limited (`refresh`).
Re-evaluates the rules against current data. No body. Response (`RefreshOut`):
```json
{ "created": 0, "updated": 1, "unchanged": 4, "expired": 0, "as_of": "2026-10-24",
  "confidence": "high", "confidence_reason": "...",
  "suppressed_rules": [ { "rule_id": "CASH_FLOW_CONSISTENCY", "reason": "..." } ],
  "active": [ RecommendationOut, ... ] }
```
`active` lists up to 100 `pending` and `accepted` items. Writes the audit event `recommendations.refreshed`.

#### `GET /recommendations/{recommendation_id}` (C own, A)
Returns `RecommendationDetail`: `RecommendationOut` plus `feedback[]` (`id`, `action`, `reason_code`, `comment`,
`created_at`, oldest first). An unknown ID, or another customer's recommendation, returns 404.

#### `POST /recommendations/{recommendation_id}/feedback` (owner customer only). Rate-limited (`feedback`).
| Field | Rules |
|---|---|
| action | `accepted`, `dismissed`, `completed`, or `correction` |
| reason_code | null or `not_relevant`, `already_doing_this`, `cannot_afford`, `income_incorrect`, `expense_incorrect`, `goal_outdated`, `transaction_miscategorized`, `other`. **Required when `action = correction`** (422) |
| comment | <= 500 chars |

Allowed status transitions: `pending` can go to `accepted`, `dismissed` or `completed`. `accepted` can go to
`completed` or `dismissed`. `dismissed`, `completed` and `expired` are terminal. Any other transition returns 409.
A `correction` records feedback without changing the status.

Other responses:
- Another customer's recommendation, or an unknown one: 404.
- Advisor: 403.

The free-text comment is stored in `recommendation_feedback` but is not copied into the audit log. Writes the audit
event `recommendation.feedback.<action>`. Returns 201:
`{ "recommendation": RecommendationOut, "feedback": FeedbackOut }`.

#### `GET /recommendation-rules` (C, A)
Returns the versioned rule catalogue (`RuleOut[]`): `rule_id`, `version`, `category`, `name`, `description`,
`parameters`, `is_active`. Ordered by `rule_id` and then version. Missing rule rows are created on first call.

## 3. Endpoint summary

| Method | Path | Auth | Customer | Advisor | Rate limit |
|---|---|---|---|---|---|
| GET | `/health` | none | – | – | – |
| POST | `/api/v1/auth/local/login` | none (dev only) | – | – | 5/min |
| GET | `/api/v1/me` | bearer | self | self | – |
| PATCH | `/api/v1/me/consent` | bearer | self | self | – |
| GET | `/api/v1/customers` | bearer | self only | all | – |
| GET | `/api/v1/customers/{id}` | bearer | own (else 404) | read | – |
| GET | `/api/v1/customers/{id}/obligations` | bearer | own | read | – |
| GET | `/api/v1/customers/{id}/data-quality-events` | bearer | own | read | – |
| GET | `/api/v1/customers/{id}/transactions` | bearer | own | read | – |
| GET | `/api/v1/customers/{id}/analytics` | bearer | own | read | – |
| GET | `/api/v1/customers/{id}/goals` | bearer | own | read | – |
| POST | `/api/v1/customers/{id}/goals` | bearer | own | 403 | 20/min |
| PATCH | `/api/v1/customers/{id}/goals/{goal_id}` | bearer | own | 403 | 20/min |
| GET | `/api/v1/customers/{id}/recommendations` | bearer | own | read (may trigger first generation) | – |
| POST | `/api/v1/customers/{id}/recommendations/refresh` | bearer | own | 403 | 20/min |
| GET | `/api/v1/recommendations/{rec_id}` | bearer | own (else 404) | read | – |
| POST | `/api/v1/recommendations/{rec_id}/feedback` | bearer | own (else 404) | 403 | 20/min |
| GET | `/api/v1/recommendation-rules` | bearer | yes | yes | – |

`tests/security/test_authorization.py::test_every_protected_route_requires_authentication` builds its list of
routes from the OpenAPI document. It checks that all 16 protected `/api` operations return 401 without a token.
