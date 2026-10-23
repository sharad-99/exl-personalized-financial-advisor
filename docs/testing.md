# Testing

## 1. Strategy

| Level | Scope | Database | Location |
|---|---|---|---|
| Unit | Pure services: classification, analytics, data quality, goal planning, rules, explanations, money and date utilities, config and tokens, synthetic data | none | `backend/tests/unit` |
| Integration | The real FastAPI app through `TestClient`, seeded with the synthetic generator (seed 42, `as_of = 2026-10-24`, fixed through a dependency override) | in-memory SQLite | `backend/tests/integration` |
| Security | Authentication, authorisation, hardening | in-memory SQLite | `backend/tests/security` |
| PostgreSQL | Migrations, constraints, append-only audit, RLS, exact NUMERIC, API on PostgreSQL | real PostgreSQL (`-m postgres`) | `backend/tests/integration/test_postgres.py` |
| Static checks | ruff lint and format (backend). TypeScript, ESLint and the production build (frontend) | – | CI and `make check` |
| End-to-end | Playwright browser journey against the running backend and frontend | seeded SQLite | `frontend/e2e/customer-journey.spec.ts` |

Determinism: the test settings are forced in `tests/conftest.py`:
- `ENVIRONMENT=test`, `AUTH_MODE=local`, in-memory SQLite, and test-only secrets
- the evaluation date is overridden to `2026-10-24`
- the rate limiter is reset for each client

pytest runs with `--strict-markers`, and `DeprecationWarning` raised from `app.*` is treated as an error.

## 2. Commands

Backend (from the repository root, after `make setup`):
```bash
cd backend && .venv/bin/python -m pytest          # unit + integration + security (Postgres tests skip)
cd backend && .venv/bin/python -m pytest -q --cov=app --cov-report=term-missing
cd backend && .venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
backend/.venv/bin/python scripts/validate_synthetic_data.py --seed 42
```

PostgreSQL tests. **They drop and recreate the `public` schema of the target database. Use a throwaway database
only.**
```bash
cd backend
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54329/exl_test .venv/bin/python -m pytest -m postgres
```
How these were verified:
- **Locally**, against PGlite served over the PostgreSQL wire protocol (`@electric-sql/pglite-socket`), started as
  `pglite-server --port=54329 --max-connections=10 --extensions=pgcrypto`, for example with `npx`.
- **In CI**, against a `postgres:17` service container (the `backend-postgres` job).
- `docker compose up -d db` (from `docker-compose.yml`) also provides a local PostgreSQL 17 on port 54329. Point
  `TEST_DATABASE_URL` at a separate, disposable database.

Frontend:
```bash
cd frontend
npm run typecheck     # next typegen && tsc --noEmit
npm run lint          # eslint .
npm run build         # next build
```

End-to-end (Playwright). The backend must be running on :8000 with seeded data, and the frontend on :3000:
```bash
# terminal 1
cd backend && .venv/bin/python -m app.synthetic_data.seed --seed 42 --reset && .venv/bin/uvicorn app.main:app --port 8000
# terminal 2
cd frontend && npm run dev            # or: npm run build && npm run start
# terminal 3
cd frontend && E2E_PASSWORD=<LOCAL_DEMO_PASSWORD> npm run e2e
```
- `E2E_PASSWORD` must equal the backend's `LOCAL_DEMO_PASSWORD`. Without it, the tests are skipped.
- By default the tests use the locally installed **Google Chrome** (`channel: "chrome"`), so no browser download
  is needed. Set `E2E_BROWSER_CHANNEL=""` to use Playwright's bundled Chromium, after
  `npx playwright install chromium`. CI does this.
- `E2E_BASE_URL` overrides `http://localhost:3000`.

Run all quality gates at once: `make check`, which runs `python3 scripts/run_quality_checks.py`. It executes ruff
lint and format, synthetic data validation, the backend tests, and the frontend typecheck, lint and build.

## 3. Verified results

These results were recorded when this documentation was written:

| Check | Result |
|---|---|
| Backend tests with `TEST_DATABASE_URL` set (PGlite) | **203 passed**, including the 6 PostgreSQL tests |
| Backend tests without `TEST_DATABASE_URL` | **197 passed, 6 skipped** |
| Frontend `typecheck`, `lint`, `build` | clean |
| Playwright e2e | **4 passed** |

The GitHub Actions workflow (`.github/workflows/tests.yml`) defines four jobs: `backend`, `backend-postgres`,
`frontend` and `e2e`. These results come from local runs. This document does not claim any CI run status.

## 4. Test inventory

Counts come from `pytest --collect-only`. Parametrised tests are counted once per case.

| File | Functions | Collected cases | Focus |
|---|---|---|---|
| `unit/test_categorization.py` | 11 | 11 | Flows, duplicates, reversals, transfers, keyword rules, order independence, merchant normalisation |
| `unit/test_config_and_tokens.py` | 9 | 11 | Production config rules, CORS parsing, local token round trip, invalid claims (3 cases), `alg=none` and wrong secret, Supabase HS256 issuer and audience, rate limiter, log redaction |
| `unit/test_financial_analytics.py` | 17 | 17 | Period, totals, averages, savings rate, exclusions, missing and stale data, emergency fund, reconciliation, obligations and provision, capacity, recurring detection, month-over-month, exact sums |
| `unit/test_goal_planning.py` | 8 | 8 | Achieved, on track, behind, capacity cap, unknown or zero capacity, overdue, inactive, shared capacity pool |
| `unit/test_money_and_formatting.py` | 6 | 12 | HALF_UP rounding, float rejection, paise round trip, `safe_ratio` returning None, INR grouping (7 cases), month arithmetic |
| `unit/test_recommendation_engine.py` | 15 | 74 | Every rule, suppression, consent, reproducibility, plus a 60-case run over every synthetic customer for safety and traceability |
| `unit/test_synthetic_data.py` | 8 | 8 | Volume, reproducibility, persona coverage, 12+ months, no real-looking identifiers, validator catches injected errors, reference SQL matches code, `--reset` keeps linked auth users |
| `integration/test_api.py` | 17 | 17 | Health, OpenAPI, scoping, schemas, pagination and filters, invalid inputs, 404s, analytics, goals, recommendations, feedback, consent, low confidence, rule catalogue, data-quality events |
| `integration/test_database_failures.py` | 2 | 2 | Health reports `degraded`. A protected route returns 503 without leaking details |
| `integration/test_schema_parity.py` | 2 | 2 | SQL vs ORM table and column names |
| `integration/test_postgres.py` | 6 | 6 | Re-runnable migrations, constraints, append-only audit, RLS isolation, exact NUMERIC, API on PostgreSQL |
| `security/test_authorization.py` | 8 | 23 | 401 on all 16 protected routes, invalid tokens, 403 without a profile, cross-customer reads and writes, foreign goal IDs, foreign feedback, advisor read-only |
| `security/test_hardening.py` | 12 | 12 | No secrets in responses, identical login errors, login and refresh rate limits, per-user rate-limit buckets, local login disabled in Supabase mode, injection, oversized body, no input echo, CORS, headers, audit hygiene |
| **Total** | **121** | **203** | 141 unit, 27 integration (6 of them PostgreSQL), 35 security |

The e2e spec (`frontend/e2e/customer-journey.spec.ts`) contains 4 tests:
1. Unauthenticated visitors are redirected to login.
2. A wrong password shows an error.
3. Customer journey: dashboard, money coach, feedback, goals, sign out.
4. The advisor is read-only (no "New goal" button).

## 5. Requirement-to-test map

| Requirement category | Tests |
|---|---|
| Financial calculations | `unit/test_financial_analytics.py` (`test_totals_averages_and_savings_rate`, `test_emergency_fund_coverage_and_target`, `test_upcoming_obligations_roll_forward_and_capacity_provision`, `test_capacity_uses_lower_recent_average`, `test_recurring_subscription_detection`, `test_month_over_month_change`, `test_default_period_is_last_complete_months`); `unit/test_goal_planning.py`; `integration/test_api.py::test_analytics_schema_and_values` |
| Transaction classification | `unit/test_categorization.py` (`test_income_expense_and_refund_flows`, `test_keyword_rules_recover_uncategorised_transactions`, `test_classification_is_order_independent`, `test_normalize_merchant_strips_reference_tokens`); `integration/test_api.py::test_transactions_pagination_filters_and_classification` |
| Duplicates, transfers, reversals, refunds | `unit/test_categorization.py` (`test_duplicate_import_is_excluded_once`, `test_same_amount_different_description_is_not_a_duplicate`, `test_reversal_neutralises_both_legs`, `test_orphan_reversal_is_flagged`, `test_card_bill_payment_is_an_internal_transfer_not_an_expense`, `test_unbalanced_or_one_legged_transfer_is_unmatched`, `test_transfer_into_deposit_is_marked_as_savings`); `unit/test_financial_analytics.py::test_refunds_transfers_duplicates_and_reversals_do_not_inflate_totals` |
| Recommendation rules | `unit/test_recommendation_engine.py` (`test_healthy_customer_gets_no_corrective_advice`, `test_emergency_fund_rule_with_traceable_evidence`, `test_no_savings_amount_when_capacity_is_zero`, `test_goal_rule_and_celebration`, `test_discretionary_spending_rule`, `test_upcoming_lumpy_obligation_rule`, `test_obligations_exceeding_balance_are_high_priority`, `test_subscription_rule`, `test_cash_flow_rule_for_negative_months`, `test_consent_withdrawn_produces_nothing`, `test_evaluation_is_reproducible`) |
| Traceability and safety | `unit/test_recommendation_engine.py::test_every_synthetic_customer_gets_safe_traceable_recommendations` (60 cases: rule id and version, inputs, calculations, assumptions, actions, no banned phrases, no "None", suggestions <= capacity); `integration/test_api.py::test_recommendations_generated_once_and_refresh_is_idempotent` |
| Missing and stale data | `unit/test_financial_analytics.py` (`test_missing_months_are_not_treated_as_zero`, `test_short_history_produces_explicit_unknowns`, `test_missing_balance_makes_emergency_fund_unknown_not_zero`, `test_stale_transactions_lower_confidence`, `test_no_income_gives_explicit_status`); `unit/test_recommendation_engine.py` (`test_low_confidence_suppresses_dependent_rules_and_requests_data`, `test_missing_income_is_requested_not_assumed_zero`, `test_missing_balance_suppresses_emergency_rule_with_reason`); `integration/test_api.py` (`test_low_confidence_customer_only_gets_data_request`, `test_data_quality_events_recorded`) |
| Goals | `unit/test_goal_planning.py` (all 8); `integration/test_api.py` (`test_goal_lifecycle`, `test_goal_validation`); `unit/test_recommendation_engine.py::test_goal_rule_and_celebration` |
| Monetary precision | `unit/test_money_and_formatting.py`; `unit/test_financial_analytics.py::test_many_small_amounts_sum_exactly`; `integration/test_postgres.py::test_money_is_exact_numeric` |
| API schemas | `integration/test_api.py` (`test_openapi_documents_core_endpoints`, `test_customer_detail_schema`, `test_analytics_schema_and_values`, `test_health`) |
| Invalid inputs | `integration/test_api.py` (`test_invalid_inputs_return_consistent_errors`, `test_goal_validation`); `security/test_hardening.py` (`test_validation_errors_do_not_echo_input`, `test_injection_style_input_is_treated_as_data`, `test_oversized_body_rejected`); `unit/test_financial_analytics.py::test_invalid_period_rejected` |
| Unknown IDs | `integration/test_api.py::test_unknown_customer_is_404`; `security/test_authorization.py::test_goal_id_from_another_customer_is_not_reachable_via_own_path` |
| Database failures | `integration/test_database_failures.py` (`test_health_reports_degraded_database`, `test_protected_route_returns_503_without_leaking_details`) |
| Persistence and feedback | `integration/test_api.py` (`test_recommendations_generated_once_and_refresh_is_idempotent`, `test_feedback_flow_and_status_transitions`, `test_dismissed_subject_not_reraised`, `test_withdrawing_consent_expires_pending_recommendations`); `integration/test_postgres.py::test_api_against_postgres` |
| Authentication | `security/test_authorization.py` (`test_every_protected_route_requires_authentication` (16 cases), `test_invalid_tokens_rejected`, `test_valid_token_without_profile_is_forbidden`); `unit/test_config_and_tokens.py`; `security/test_hardening.py` (`test_wrong_password_and_unknown_user_look_identical`, `test_login_rate_limited`, `test_local_login_disabled_in_supabase_mode`) |
| Cross-customer isolation | `security/test_authorization.py` (`test_customer_a_cannot_read_customer_b`, `test_customer_a_cannot_modify_customer_b`, `test_goal_id_from_another_customer_is_not_reachable_via_own_path`); `integration/test_postgres.py::test_row_level_security_isolates_customers`; `integration/test_api.py::test_me_and_customer_list_scoping` |
| Unauthorised feedback | `security/test_authorization.py` (`test_feedback_on_another_customers_recommendation_rejected`, `test_advisor_is_read_only`) |
| Secrets not returned or logged | `security/test_hardening.py` (`test_privileged_values_never_returned`, `test_audit_log_has_no_free_text_or_tokens`); `unit/test_config_and_tokens.py::test_log_redaction` |
| Database schema integrity | `integration/test_schema_parity.py`; `integration/test_postgres.py` (`test_migrations_re_runnable`, `test_constraints_enforced`, `test_audit_events_are_append_only`) |
| Synthetic data quality | `unit/test_synthetic_data.py`; `scripts/validate_synthetic_data.py` (CI step) |

## 6. Known gaps in testing

- No frontend unit or component tests. The UI is covered by the typecheck, lint, build and the 4 Playwright tests.
- No load or performance tests, and no test of the in-memory rate limiter across processes.
- Supabase-mode login is not exercised end to end. JWKS verification is not tested against a live Supabase
  project. HS256 Supabase verification is unit-tested.
- The parity test compares table and column names only. Types and constraints are covered only when the
  PostgreSQL tests run.
