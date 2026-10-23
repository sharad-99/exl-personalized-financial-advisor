# Deployment

> **Status: nothing has been deployed.** No Supabase project, backend service or Vercel project exists for this
> repository yet, and no public URLs exist. This guide describes the intended deployment. Every step requires the
> project owner's own accounts and explicit go-ahead. Placeholders such as `<project-ref>`, `<backend-host>` and
> `<vercel-domain>` must be replaced with real values.

Target topology:

```
Browser --> Vercel (Next.js frontend + BFF route handlers) --> Python host (FastAPI) --> Supabase PostgreSQL
                      |                                              ^
                      +--> Supabase Auth (sign-in, sessions) --------+ (JWKS for token verification)
```

The deployed demo runs on **synthetic data only**.

## 1. Supabase

### 1.1 Create the project
1. Create a project in the Supabase dashboard. Choose a region close to the backend host, and record the project
   ref and database password.
2. Note these values (Project Settings):
   - **Project URL** `https://<project-ref>.supabase.co`, used as `SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_URL`
   - **Publishable (anon) key**, used as `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. It is public by design and
     protected by RLS.
   - **Database connection strings**: direct, and pooled (Supavisor)
   - The **service-role key is not needed** and must not be configured anywhere in this project.

### 1.2 Apply migrations
Use either method. Both read `supabase/migrations/*.sql`:
```bash
# Option A: Supabase CLI (after `supabase link --project-ref <project-ref>`)
supabase db push

# Option B: the project's runner, using the owner (postgres) connection string
cd backend
DATABASE_URL='postgresql://postgres:<db-password>@db.<project-ref>.supabase.co:5432/postgres' \
  .venv/bin/python -m app.db.migrate
```
Option B loads the normal backend settings, so they must validate. Either run it from `backend/` with a local
`.env` present, or also set `AUTH_MODE=supabase SUPABASE_URL=https://<project-ref>.supabase.co`. Option B records
the files it applied in `public.schema_migrations`. Do not mix the two methods on the same
database: each tracks applied migrations in its own way.

### 1.3 Create the least-privilege backend role
The migration creates `exl_api` as `NOLOGIN`. Enable it with a long random password in the SQL editor:
```sql
alter role exl_api with login password '<generate-a-long-random-password>';
```
The backend's `DATABASE_URL` then uses this role, typically through the pooler:
`postgresql://exl_api.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres`.
Check the current pooler host, port and mode in the dashboard. `exl_api` has no DELETE privilege and cannot run
migrations.

### 1.4 Auth settings
In Authentication, then Providers / URL Configuration:
- Enable the **Email** provider (email and password). For a closed demo, consider turning off public sign-ups and
  creating users manually.
- **Site URL**: `https://<vercel-domain>`.
- **Redirect URLs**: `https://<vercel-domain>/**` and `http://localhost:3000/**`.
- The backend verifies tokens through the project's JWKS (RS256 or ES256). Set `SUPABASE_JWT_SECRET` on the
  backend only if the project still signs with the legacy HS256 shared secret.

### 1.5 Create demo users and link them to profiles
1. Create the demo users in Authentication > Users, for example one customer and one advisor. Use addresses you
   control and strong passwords, and share them only with the evaluation team.
2. Seed the synthetic data (section 1.6).
3. Link each user to a synthetic profile (see `security.md`, section 2):
```sql
update public.profiles set auth_user_id = '<supabase-user-uuid>' where email = 'customer01@demo.exl.test';
update public.profiles set auth_user_id = '<supabase-user-uuid>' where email = 'advisor@demo.exl.test';
```
A user who has not been linked can sign in but gets `403 No customer profile is linked to this account` from the
API. Re-seeding with `--reset` keeps these links: the seeder re-applies existing `auth_user_id` values by email.

### 1.6 Seed synthetic data
Run from a trusted machine with the **owner** connection string. `--reset` needs DELETE, which `exl_api` does not have:
```bash
cd backend
ENVIRONMENT=production AUTH_MODE=supabase SUPABASE_URL=https://<project-ref>.supabase.co \
DATABASE_URL='postgresql://postgres:<db-password>@db.<project-ref>.supabase.co:5432/postgres' \
  .venv/bin/python -m app.synthetic_data.seed --seed 42 --reset --allow-production
```
The seeder refuses to run with `ENVIRONMENT=production` unless `--allow-production` is given. `--reset` removes
only rows that belong to `is_synthetic = true` profiles. Add `--as-of YYYY-MM-DD` to pin the dataset date.

## 2. Backend (FastAPI) on a Python host

Any host that runs a Python ASGI app works. The repository includes a Render Blueprint, `render.yaml`:

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Runtime | Python 3.12+ (CI uses 3.14; choose a version the host supports) |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` (returns 200 with `status: degraded` if the database is down) |

Railway or Fly.io are reasonable alternatives with the same build and start commands. Fly.io additionally needs a
Dockerfile or buildpack configuration, which this repository does not include.

Run a **single instance**. The rate limiter is in-memory (`security.md`, section 8).

### Backend environment variables

| Variable | Value | Secret? |
|---|---|---|
| `ENVIRONMENT` | `production` (turns off `/docs` and `/redoc`, adds HSTS, enforces production configuration checks) | no |
| `DATABASE_URL` | `exl_api` pooled connection string | **yes** |
| `AUTH_MODE` | `supabase` (required in production) | no |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` | no |
| `SUPABASE_JWT_SECRET` | Only for legacy HS256 projects; otherwise leave unset | **yes** |
| `SUPABASE_JWT_AUDIENCE` | default `authenticated` | no |
| `CORS_ALLOWED_ORIGINS` | `https://<vercel-domain>` (comma-separated, explicit, https, no `*`) | no |
| `LOG_LEVEL` | `INFO` | no |
| Optional tuning | `REQUEST_TIMEOUT_SECONDS` (15), `MAX_REQUEST_BODY_BYTES` (65536), `RATE_LIMIT_SENSITIVE_PER_MINUTE` (20), `RATE_LIMIT_LOGIN_PER_MINUTE` (5) | no |

Do **not** set `LOCAL_JWT_SECRET` or `LOCAL_DEMO_PASSWORD` in production. Local authentication is rejected there.

## 3. Frontend on Vercel

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Framework preset | Next.js (build `npm run build`, Node >= 20.9) |

| Variable | Value | Exposure |
|---|---|---|
| `API_BASE_URL` | `https://<backend-host>` (no trailing slash) | server-only |
| `AUTH_MODE` | `supabase` | server-only |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<project-ref>.supabase.co` | public |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | publishable (anon) key | public (RLS-protected) |

Never add the service-role key or any `NEXT_PUBLIC_` variable that points to the backend. After the first deploy,
put the Vercel domain into the backend's `CORS_ALLOWED_ORIGINS` and into the Supabase Site URL and redirect URLs.

## 4. CORS

The browser calls only the same-origin Vercel BFF (`/api/backend/...`), and the BFF calls the backend from the
server. CORS on the backend therefore matters only for direct browser clients. Keep it limited to the Vercel
production domain. Preview deployments use different domains: add them explicitly only if needed. Wildcards are
rejected.

## 5. Post-deploy smoke test

1. `curl https://<backend-host>/health` returns `{"status":"ok","database":"ok","auth_mode":"supabase",...}`.
2. `https://<backend-host>/docs` returns 404 in production. `/openapi.json` is still served.
3. Open `https://<vercel-domain>`. You should be redirected to `/login`. Sign in as the linked demo customer and
   check that the dashboard, money coach (accept or dismiss), goals, history and settings work.
4. Sign in as the advisor. You should see the customer list, with no write buttons.
5. Confirm that a user who has not been linked receives a "no linked profile" error, not data.

## 6. Logs and troubleshooting

- **Backend logs:** one JSON line per request (method, path, status, duration_ms, request_id) on stdout, visible in
  the host's log viewer. Every response carries `X-Request-ID`. Error bodies contain `request_id`, so you can
  search the logs for it.
- **Frontend logs:** Vercel function logs for the route handlers.

| Symptom | Likely cause |
|---|---|
| Backend fails to start with a validation error | Production configuration rule violated: SQLite URL, `AUTH_MODE=local`, `http` CORS origin, `*` in CORS, or missing `SUPABASE_URL` |
| `/health` shows `database: unavailable` | Wrong `DATABASE_URL`, `exl_api` without LOGIN or with the wrong password, pooler host or port, or a paused project |
| 401 "Invalid access token" | `SUPABASE_URL` mismatch (issuer), wrong audience, legacy HS256 project without `SUPABASE_JWT_SECRET`, clock skew |
| 403 "No customer profile is linked" | Run the linking SQL (section 1.5) |
| 503 from the frontend "advisor service is unavailable" | Wrong `API_BASE_URL`, backend asleep or cold-starting, or backend down |
| 504 | Backend slow (cold start or slow query). Both the BFF and backend time out at 15 s |
| 429 for many users at once | The shared in-memory rate-limit bucket (`security.md`, section 8) |
| Login loop on Vercel | Supabase Site URL or redirect URLs missing the Vercel domain, or wrong `NEXT_PUBLIC_SUPABASE_*` values |

## 7. Rollback and recovery

- **Frontend:** use Vercel's instant rollback to promote a previous production deployment.
- **Backend:** redeploy the previous commit or deploy from the host's dashboard (on Render: "Rollback" or redeploy
  an earlier deploy).
- **Database migrations only move forward.** No down migrations exist. To revert a schema change, write and review
  explicit down SQL, test it on a copy, take a backup, and then apply it. Prefer additive, backward-compatible
  migrations so the previous backend version keeps working.
- **Backups:** check the backup options of your Supabase plan. Before risky changes, take a manual dump:
  ```bash
  pg_dump '<owner-connection-string>' --schema=public --no-owner -Fc -f exl_backup_$(date +%F).dump
  ```
- **Data:** the data is synthetic and reproducible (`--seed 42 --as-of <date>`). Recovering it means re-running
  migrations and the seeder, then re-linking users. Feedback, goals created during the demo, and audit history
  would be lost unless they were backed up.

## 8. Free-tier considerations (verify at deployment time)

Free and hobby plans change often. **Verify the current limits of each provider when you deploy.** This document
deliberately does not state specific numbers. Things to check:
- **Backend host:** whether free instances sleep when idle and how long cold starts take (the first request may
  hit the 15 s timeout), monthly hour or bandwidth allowances, and supported Python versions.
- **Supabase:** whether inactive free projects are paused (the API will then return 503 until the project is
  resumed), database size, connection and pooler limits, Auth email sending limits, and backup retention.
- **Vercel:** function execution time limits, bandwidth, and whether the Hobby plan's terms fit an academic
  project.
- Region placement: keep the backend and the database in the same region to reduce latency.
