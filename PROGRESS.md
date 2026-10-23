# Progress log

Last updated: 2026-10-24. Resume from "Next actions" below.

## Stage status

| Stage | Status | Evidence |
|---|---|---|
| 0 Inspect directory | Done | Parent folder `EXL/` held an earlier small scaffold plus the progress report PDF and questionnaire DOCX. They were left untouched; this project was created in the new subfolder `exl-personalized-financial-advisor/`. |
| 1 Monorepo, config, docs | Done | Root configs, Makefile, docker-compose, env templates, `docs/` (9 files). |
| 2 Schema, migrations, synthetic data | Done | 3 SQL migrations (12 tables, constraints, indexes, RLS, reference data); generator (60 customers, 8 personas, 13 months + partial, ~23k transactions); validator passes with 0 errors. |
| 3 Analytics | Done | `services/financial_analytics.py`, `spending_categorization.py`, `data_quality.py`, `goal_planning.py`; unit tests with hand-computed expectations. |
| 4 Recommendation engine | Done | 8 rules v1, explanations separate, persistence with stable IDs and dedup; tests run every rule over all 60 personas for safety and traceability. |
| 5 FastAPI + DB | Done | All required endpoints plus `/me`, consent, obligations, data-quality events, rule catalogue, single recommendation. |
| 6 Frontend | Done | Login, dashboard, profile, money coach, goals, history, settings; loading/error/empty/stale states; responsive. |
| 7 Auth & security | Done (local + Supabase code paths) | Local mode verified end-to-end. Supabase mode verified only by unit tests (HS256 token verification); not run against a live Supabase project. |
| 8 Tests, quality, CI | Done locally | Backend 203 passed (incl. 6 PostgreSQL tests via PGlite); ruff clean; frontend typecheck/lint/build clean; Playwright 4 passed (dev and production build). CI workflow written but not yet run on GitHub. |
| 9 Local end-to-end | Done | Manual browser walkthrough as customer and advisor; mobile layout; cross-customer URL blocked. |
| 10 Deployment | Prepared, not executed | Needs your Supabase, hosting and GitHub accounts plus explicit go-ahead. See docs/deployment.md. |

## Decisions worth knowing

- **SQLite for the zero-setup local demo**, PostgreSQL/Supabase everywhere else. No Docker was
  available on the build machine, so PostgreSQL behaviour was verified with PGlite (real Postgres
  compiled to WASM). CI runs the same tests against a `postgres:17` service.
- **Local demo auth** (`AUTH_MODE=local`) exists so the app runs without a Supabase account. It is
  rejected at start-up when `ENVIRONMENT=production`.
- **Backend-for-frontend proxy**: the browser never holds an access token or the backend URL.
- **Advisor role** is a demo concept (EXL analyst view): read-only across synthetic customers.
- Next.js 16 with Cache Components: the authenticated shell sits behind `<Suspense>`; data is
  fetched client-side through the proxy.

## Known limitations

See docs/security.md ("Remaining limitations"). Highlights: in-memory rate limiter (single
instance only), no MFA, no Content-Security-Policy yet, local demo password is shared by all demo
users, Supabase user-to-profile linking is a manual SQL step.

## Next actions

1. Create a GitHub repository and push (needs your account; then confirm CI passes).
2. Create a Supabase project; apply migrations; create the `exl_api` login role; create demo users
   and link them to profiles (docs/deployment.md).
3. Deploy the backend (e.g. Render) and the frontend (Vercel) with the documented variables.
4. Optional hardening: CSP header, shared rate-limit store, dependency scanning in CI.
