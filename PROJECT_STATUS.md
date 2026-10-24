# Project status — EXL Personalized Financial Advisor

Audit date: 2026-10-24 (local time, IST). Repository: https://github.com/sharad-99/exl-personalized-financial-advisor
(public), branch `main`. Section 0 is the latest update; sections 1–6 are the earlier full audit (commits `58618ca`,
`111d9c0`). Everything was re-run when written; nothing is
reported from memory. `PROGRESS.md` holds the original stage log and design decisions.

## 0c. Latest update — deployed on Vercel (2026-10-24)

| Component | Where | Status |
|---|---|---|
| Database + Auth | Supabase project `exl-advisor` (Mumbai, ap-south-1) | live; migrated, seeded (synthetic), RLS verified, sign-ups disabled, 2 linked demo users |
| Backend (FastAPI) | Vercel project `exl-personalized-financial-advisor` → https://exl-personalized-financial-advisor.vercel.app | **live**, region `bom1` (Mumbai) |
| Frontend (Next.js) | Vercel project `exl-financial-coach` | deploying (see next update) |

Backend environment (Vercel, Production): `ENVIRONMENT=production`, `AUTH_MODE=supabase`, `SUPABASE_URL`,
`CORS_ALLOWED_ORIGINS` (config) and `DATABASE_URL` (secret, entered by the account owner).

Live backend checks (run from this machine against the URL above):

| Check | Result |
|---|---|
| `GET /health` | `{"status":"ok","environment":"production","database":"ok","auth_mode":"supabase"}` |
| `/docs`, `/redoc`, `/openapi.json` | 404 |
| `POST /api/v1/auth/local/login` | 404 (local demo login disabled) |
| `/api/v1/me`, `/api/v1/customers`, `/api/v1/recommendation-rules` without token | 401 with standard error body |
| Forged token | 401 |
| CORS preflight from `https://evil.example` | no `Access-Control-Allow-Origin` |
| Security headers | HSTS, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` |
| Latency, 10 × `/health` | ~1.9 s each in default region `iad1` → **~0.2 s** after pinning `bom1` (commit `1c9ca77`) |

Notes: the first deployment was accidentally started before environment variables were set; the app refused to
start (500) as designed and was redeployed after configuration. The project kept the default name.

## 0b. Earlier update — backend prepared for Vercel (2026-10-24)

Render's Blueprint flow required a paid plan and the first free deploy failed because Root Directory was empty
(`Could not open requirements file`). Decision: host the FastAPI backend on Vercel (free Hobby, Python 3.14
supported, FastAPI auto-detected in `app/main.py`).

| Change | Files |
|---|---|
| Serverless mode (auto when `VERCEL=1`): `NullPool`, one DB connection per request | `backend/app/db/connection.py`, `backend/app/core/config.py` |
| Supabase transaction pooler (port 6543) supported: prepared statements and startup options disabled there | `backend/app/db/connection.py` |
| `/openapi.json` hidden in production (was still public; `/docs` already hidden) | `backend/app/main.py` |
| Bundle excludes tests/local data; packaging no longer references a README outside `backend/` | `backend/vercel.json`, `backend/pyproject.toml` |
| Tests: pool modes, pooler connect args, `VERCEL` detection, docs/schema hidden in production | `backend/tests/unit/test_connection.py`, `backend/tests/security/test_hardening.py` |
| Docs: Vercel backend section; Render kept as alternative | `docs/deployment.md` |

Verification:

| Check | Result |
|---|---|
| Clean venv from `requirements.txt` only | installs; 208 MB (Vercel limit 500 MB); no test tools included |
| That build with `VERCEL=1 ENVIRONMENT=production AUTH_MODE=supabase` on the Supabase DB | `/health` ok; `/docs` 404; local demo login 404; no token / forged token 401; HSTS + security headers; 8 sequential requests 200; 0 idle connections left |
| Frontend (Supabase mode) against that backend, signed in as customer01 | money coach loads 5 recommendations with evidence; two concurrent refreshes both 200; other customer's analytics and feedback 404 |
| `TEST_DATABASE_URL=<throwaway PGlite> pytest -q` | **236 passed**, 0 failed |
| `ruff check` / `ruff format --check` (app, tests, scripts) | clean |

## 0a. Earlier update — Supabase sign-in verified end to end (2026-10-24)

| Step | Result |
|---|---|
| Account owner reset the Supabase DB password and created `advisor@demo.exl.test`, `customer01@demo.exl.test` (auto-confirmed) | done by owner |
| `scripts/link_supabase_users.py --apply` | 2 profiles linked (advisor, customer01) |
| Local run in Supabase mode (`AUTH_MODE=supabase`, backend → Supabase Postgres, frontend → Supabase Auth) | `/health` ok, `auth_mode: supabase`; local demo login endpoint returns 404 |
| First sign-in attempt | **Failed**: backend returned 401 on every request. Cause: python.org macOS Python has no CA store, so fetching Supabase's JWKS (ES256 keys) failed TLS verification |
| Fix | `core/security.py`: JWKS client verifies TLS with the `certifi` bundle (now a direct dependency); rejected tokens log the reason (never the token) |
| Second sign-in (owner, in browser) | customer01 and advisor both signed in; dashboards load from Supabase |
| Live isolation check from customer01's browser session | own analytics 200; another customer's profile / analytics / transactions 404; creating a goal for another customer 404; customer list size 1 |
| Advisor session | read other customers (allowed, read-only) |
| Bug found in logs | concurrent first loads of recommendations → one request 409 (duplicate insert of deterministic IDs). Fixed: refresh retries once after rolling back an `IntegrityError` |
| New tests | ES256 tokens via JWKS (valid accepted; wrong audience, issuer or signing key rejected); certifi-backed JWKS client; concurrent first-generation retry |
| `cd backend && TEST_DATABASE_URL=<throwaway PGlite> .venv/bin/python -m pytest -q` | **231 passed**, 0 failed |
| Same without `TEST_DATABASE_URL` | **219 passed, 12 skipped** |

Stage 7 (authentication & security) is now **verified for both auth modes**.

## 0. Earlier update — database & synthetic-data milestone (2026-10-24)

The milestone's core (12-table normalized schema with FKs, CHECK/UNIQUE constraints, indexes, NUMERIC(14,2) money
and RLS; deterministic 60-persona generator with 13 months + partial month; seeder; validator; docs) already
existed and was verified in the audit below. This update re-checked every requirement and closed the gaps found:

| Change | Files |
|---|---|
| Validator now runs the production transaction classifier: category/type consistency, duplicate detector must find exactly the injected duplicates, no unmatched transfers or orphan reversals, ≤2% uncategorised after rules; classifier stats added | `backend/app/synthetic_data/validation.py` |
| Real incomplete-data scenario: 4 `stale_profile` customers now have no declared income **and** no income credits (salary paid elsewhere) — previously `missing_income` never fired | `backend/app/synthetic_data/generator.py` |
| Bug fix: when no income is observed, average income and net cash flow are now `null` (unknown) instead of `0.00` | `backend/app/services/financial_analytics.py` |
| Bug fix: on local SQLite, money CHECK constraints compared decimal *text* with numbers and never fired; they now cast (`CAST(amount AS NUMERIC) > 0`); added direction and saved-amount checks | `backend/app/models/tables.py` |
| New tests: golden record counts + SHA-256 fingerprint, scenario coverage, validator inconsistency detection, seeding, SQLite constraints (19 cases); 6 more PostgreSQL constraint cases | `backend/tests/unit/test_synthetic_data_quality.py`, `backend/tests/integration/test_postgres.py`, `backend/tests/unit/test_financial_analytics.py` |
| Supabase user-linking script (dry run by default) | `scripts/link_supabase_users.py` |
| `scripts/` now linted (fixed an unused import) in Makefile, CI and quality script | `Makefile`, `.github/workflows/tests.yml`, `scripts/run_quality_checks.py` |
| Docs: scenario table, determinism/golden values, classification checks, actual stats, Supabase load commands, test map, SQLite constraint note, test counts | `docs/synthetic-data.md`, `docs/database-design.md`, `docs/testing.md`, `README.md`, `docs/product-requirements.md` |

Commands run for this update and results:

| Command | Result |
|---|---|
| `backend/.venv/bin/python scripts/validate_synthetic_data.py --seed 42 --as-of 2026-10-24` | PASS, 0 errors, 4 expected warnings; 22,872 transactions; 1,249 income / 20,118 expense / 15 refund / 1,490 excluded; 20 duplicates detected = 20 injected; 0 uncategorised after rules |
| `cd backend && TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54329/postgres .venv/bin/python -m pytest -q` (throwaway PGlite) | **228 passed**, 0 failed (includes 12 PostgreSQL tests) |
| `python3 scripts/run_quality_checks.py` (no `TEST_DATABASE_URL`) | all 7 gates PASS: ruff lint, ruff format, data validation, backend tests (**216 passed, 12 skipped**), frontend typecheck, lint, build |
| `E2E_PASSWORD=<LOCAL_DEMO_PASSWORD> npx playwright test` (local SQLite re-seeded) | **4 passed** |
| Failed tests | **none** |

Supabase (project `exl-advisor`, Mumbai):

| Step | Result |
|---|---|
| `python -m app.db.migrate` | nothing to apply (up to date) |
| `python -m app.synthetic_data.seed --seed 42 --as-of 2026-10-24 --reset` | 61 profiles, 119 accounts, 22,872 transactions, 85 goals, 146 obligations, 40 data-quality events |
| Public sign-ups | **disabled**; `POST /auth/v1/signup` returns `422 signup_disabled` |
| Anonymous REST API (`/rest/v1/<table>` with the publishable key) | `transactions`, `profiles`, `accounts`, `schema_migrations`, `recommendation_rules` all denied (`42501`) |
| Auth users / profile links | **not yet created** — `scripts/link_supabase_users.py` reports no users. Blocked on the account owner choosing passwords |

The recommendation engine was not modified in this update.

## 1. Project structure (146 tracked files)

| Path | Contents |
|---|---|
| `backend/app/` (48 files) | FastAPI app: `api/routes` (health, auth, customers, transactions, analytics, goals, recommendations, feedback), `api/deps.py` (authn/authz, pagination, rate limits), `core/` (config, security, logging, errors), `db/` (engine, migration runner), `models/` (ORM tables, domain dataclasses), `repositories/`, `schemas/`, `services/` (analytics, categorisation, data quality, goal planning, recommendation engine, explanations, persistence), `synthetic_data/` (generator, seeder, validator, reference data), `utils/` |
| `backend/tests/` (19 files) | `unit/` (7 modules), `integration/` (4 modules incl. PostgreSQL), `security/` (2 modules), shared fixtures |
| `backend/` other | `pyproject.toml`, `requirements.txt` (pinned lock), `requirements-dev.txt`, `.env.example` |
| `frontend/src/` (38 files) | App Router pages: `login`, `(app)/dashboard`, `customers`, `customers/[customerId]`, `insights` (money coach), `goals`, `recommendations` (history), `settings`; route handlers `api/auth/login`, `api/auth/logout`, `api/backend/[...path]` (proxy); `proxy.ts`; components (`charts`, `customers`, `dashboard`, `goals`, `layout`, `recommendations`, `shared`); `hooks`; `lib` (api-client, auth, formatting, validation, server session/config); `types` |
| `frontend/` other | `package.json` + `package-lock.json`, `next.config.ts`, `tsconfig.json`, `eslint.config.mjs`, `playwright.config.ts`, `e2e/customer-journey.spec.ts`, `.env.example` |
| `supabase/` | `migrations/` (initial schema, row-level security, generated reference data), `config.toml`, `seed.sql` (pointer to the Python seeder) |
| `docs/` (9 files) | architecture, database design, API specification, recommendation engine, synthetic data, security, testing, deployment, product requirements |
| `scripts/` | `generate_synthetic_data.py`, `validate_synthetic_data.py`, `run_quality_checks.py` |
| root | `README.md`, `PROGRESS.md`, `Makefile`, `docker-compose.yml`, `render.yaml`, `.github/workflows/tests.yml`, `.gitignore`, `.editorconfig`, `.env.example`, `.claude/launch.json` (local preview config) |

Size: backend app ≈ 6.8k lines, backend tests ≈ 1.9k, frontend src + e2e ≈ 2.8k, docs + SQL ≈ 2.7k.

## 2. Commands executed for this audit and results

Backend (`cd backend`, with `TEST_DATABASE_URL` and `DATABASE_URL` unset):

| Command | Result |
|---|---|
| `.venv/bin/ruff check app tests` | All checks passed (exit 0) |
| `.venv/bin/ruff format --check app tests` | 67 files already formatted (exit 0) |
| `.venv/bin/python ../scripts/validate_synthetic_data.py --seed 42 --as-of 2026-10-24` | RESULT: PASS — 0 errors; 4 expected warnings (deliberate duplicates, short histories, missing income, missing balances) |
| `.venv/bin/python -m pytest -p no:cacheprovider -q --cov=app --cov-report=term` | **197 passed, 6 skipped**, 0 failed; line coverage **95 %** (2972 statements, 155 missed) |
| `TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54329/postgres .venv/bin/python -m pytest -p no:cacheprovider -m postgres -v` (throwaway PGlite server, real PostgreSQL engine) | **6 passed**: re-runnable migrations, constraints, append-only audit, RLS isolation, exact NUMERIC, API flow on PostgreSQL |

The 6 skipped tests in the first run are exactly these PostgreSQL tests (they need `TEST_DATABASE_URL`). They drop
the target database's `public` schema, so they must never point at Supabase.

Frontend (`cd frontend`):

| Command | Result |
|---|---|
| `npm run typecheck` (`next typegen && tsc --noEmit`) | exit 0, no type errors |
| `npm run lint` (`eslint .`) | exit 0, no errors or warnings |
| `npm run build` (`next build`) | exit 0, compiled successfully, 13/13 static pages generated |
| `npm audit --omit=dev` | found 0 vulnerabilities |
| `E2E_PASSWORD=<LOCAL_DEMO_PASSWORD> npx playwright test` (after `python -m app.synthetic_data.seed --seed 42 --reset` on the local SQLite DB; backend :8000 and frontend :3000 running) | **4 passed**: unauthenticated redirect, wrong-password error, full customer journey, advisor read-only |

GitHub Actions (`gh run list`): workflow `tests` **succeeded on both commits** (`58618ca`, `111d9c0`); all four jobs
green — Backend (SQLite), Backend against PostgreSQL 17, Frontend (typecheck/lint/build), End-to-end (Playwright).

Live Supabase project `exl-advisor` (Mumbai) — checks run from this machine:

| Check | Result |
|---|---|
| `python -m app.db.migrate` (twice) | 3 migrations applied; second run "nothing (up to date)" |
| `python -m app.synthetic_data.seed --seed 42 --reset` | 61 profiles, 119 accounts, 22,882 transactions, 87 goals, 146 obligations, 36 data-quality events |
| RLS as role `authenticated` with customer01's subject | sees only own 430 transactions and 1 profile; 0 rows of customer02; UPDATE blocked |
| RLS as role `anon` | `transactions`, `profiles`, `schema_migrations` all blocked |

## 3. Stage status (verified)

| Stage | Status | Basis |
|---|---|---|
| 0 Inspect directory | Complete | Earlier scaffold and documents in the parent `EXL/` folder left untouched |
| 1 Monorepo, configuration, docs | Complete | Files above; 9 docs present |
| 2 Schema, migrations, synthetic data | Complete | Migrations apply on PGlite, CI Postgres 17 and Supabase; validator PASS |
| 3 Financial analytics | Complete | Unit tests with hand-computed expectations pass |
| 4 Recommendation engine | Complete | Rule, suppression, reproducibility and 60-persona safety tests pass |
| 5 FastAPI endpoints + DB | Complete | Integration tests pass on SQLite and PostgreSQL |
| 6 Frontend | Complete for local mode | Build passes; e2e passes; every screen checked manually as customer and advisor |
| 7 Authentication & security | Complete | Local auth verified end-to-end; Supabase auth verified end-to-end (ES256/JWKS, browser sign-in, live isolation) — see section 0a |
| 8 Tests, quality, CI | Complete | Local results above; GitHub Actions green |
| 9 Local end-to-end | Complete | Playwright 4/4 plus manual walkthrough |
| 10 Deployment | **In progress** | GitHub repo created and pushed. Supabase database migrated, seeded and RLS-checked; public sign-ups disabled; anonymous REST access verified denied. Demo users created and linked. **Not done:** backend hosting (Render), frontend hosting (Vercel), production smoke test |

## 4. Secrets and data audit

| Check (whole git history, all commits) | Result |
|---|---|
| `.env`, `.env.local`, `.env.supabase`, `*.db`, keys ever committed | None. Only the three `.env.example` placeholder templates |
| Actual values of `LOCAL_JWT_SECRET`, `LOCAL_DEMO_PASSWORD`, Supabase DB password (raw and URL-encoded), GitHub CLI token | 0 matches |
| Secret-shaped strings (GitHub tokens, `sb_secret_`, `service_role`, JWTs, private keys, AWS keys) | 0 matches |
| Email addresses | Only `@demo.exl.test` (reserved) plus one `demo.customer@example.com` placeholder in a docs SQL example |
| 10+ digit runs (account/card/phone-like) | None outside lockfiles/UUIDs |
| CI workflow | Contains only throwaway, CI-only test values (`ci-only-throwaway`, `ci-demo-password`) |

All customer data is synthetic (generator-produced, `is_synthetic = true`). No real customer data exists in the
repository or the Supabase project.

## 5. Missing functionality, known gaps and blockers

Blockers (need the account owner):
1. ~~Supabase Auth users~~ — created and linked (section 0a).
2. Backend not deployed (needs a Render or similar account and secret entry by the owner).
3. Frontend not deployed (needs a Vercel account; depends on the backend URL).

Not yet verified:
4. ~~Supabase-mode sign-in end to end~~ — verified (section 0a).
5. `docker-compose.yml` local PostgreSQL path (Docker is not installed on this machine).
6. The Python version to pin on Render (`PYTHON_VERSION`) — must be checked against Render's supported list.

Known limitations (documented in `docs/security.md`; not failures):
7. In-memory rate limiter — per process, unsuitable for multiple instances.
8. No Content-Security-Policy header; no MFA.
9. Request-body limit relies on `Content-Length`; a 504 timeout does not cancel the work already running.
10. Emergency-fund rule and an emergency-fund goal can both suggest an amount for the same need.
11. The `balance_mismatch` data-quality warning does not lower the confidence level.
12. ~~Missing-income personas still received salary credits~~ — fixed in section 0.
13. No frontend unit/component tests; UI is covered by typecheck, build, Playwright and manual checks.
14. `supabase/seed.sql` is a pointer to the Python seeder rather than SQL inserts.
15. Commit author email is the machine-local default (`sharad@Sharads-MacBook-Air.local`).

Failed tests: **none**.

## 6. Recommended next step

Deploy the backend to **Vercel** (project root `backend`; see `docs/deployment.md` section 2) with `ENVIRONMENT=production`, `AUTH_MODE=supabase`,
`SUPABASE_URL`, `DATABASE_URL` (Session pooler) and `CORS_ALLOWED_ORIGINS`, then the frontend to Vercel (root
`frontend`, `AUTH_MODE=supabase`, `API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`),
add the Vercel URL to Supabase Auth URL configuration, and run a production smoke test.
