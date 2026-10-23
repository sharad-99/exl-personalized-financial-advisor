# Project status — EXL Personalized Financial Advisor

Audit date: 2026-10-24 (local time, IST). Repository: https://github.com/sharad-99/exl-personalized-financial-advisor
(public), branch `main`, commits `58618ca` and `111d9c0`. Everything below was re-run for this audit; nothing is
reported from memory. `PROGRESS.md` holds the original stage log and design decisions.

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
| 7 Authentication & security | **Partially verified** | Local auth mode verified end-to-end. Supabase auth mode: HS256 token verification unit-tested only; JWKS (asymmetric) verification and browser sign-in via Supabase **not yet exercised** |
| 8 Tests, quality, CI | Complete | Local results above; GitHub Actions green |
| 9 Local end-to-end | Complete | Playwright 4/4 plus manual walkthrough |
| 10 Deployment | **In progress** | GitHub repo created and pushed. Supabase database migrated, seeded and RLS-checked. **Not done:** Supabase Auth users + profile linking, backend hosting (Render), frontend hosting (Vercel), production smoke test |

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
1. Supabase Auth users not yet created; therefore not linked to profiles; sign-up not yet disabled.
2. Backend not deployed (needs a Render or similar account and secret entry by the owner).
3. Frontend not deployed (needs a Vercel account; depends on the backend URL).

Not yet verified:
4. Supabase-mode sign-in end to end (browser → Supabase Auth → proxy → JWKS verification in FastAPI).
5. `docker-compose.yml` local PostgreSQL path (Docker is not installed on this machine).
6. The Python version to pin on Render (`PYTHON_VERSION`) — must be checked against Render's supported list.

Known limitations (documented in `docs/security.md`; not failures):
7. In-memory rate limiter — per process, unsuitable for multiple instances.
8. No Content-Security-Policy header; no MFA.
9. Request-body limit relies on `Content-Length`; a 504 timeout does not cancel the work already running.
10. Emergency-fund rule and an emergency-fund goal can both suggest an amount for the same need.
11. The `balance_mismatch` data-quality warning does not lower the confidence level.
12. The synthetic "missing declared income" personas still receive salary credits, so the `missing_income` path is
    covered by unit tests but not exercised by the seeded data.
13. No frontend unit/component tests; UI is covered by typecheck, build, Playwright and manual checks.
14. `supabase/seed.sql` is a pointer to the Python seeder rather than SQL inserts.
15. Commit author email is the machine-local default (`sharad@Sharads-MacBook-Air.local`).

Failed tests: **none**.

## 6. Recommended next step

Finish the Supabase Auth setup, because it unblocks the only unverified security path and both hosting steps:
create `advisor@demo.exl.test` and `customer01@demo.exl.test` in Supabase Auth (auto-confirm), disable public
sign-ups, then link the users to their synthetic profiles and verify a Supabase-issued token against the backend
locally (`AUTH_MODE=supabase`) **before** deploying to Render and Vercel.
