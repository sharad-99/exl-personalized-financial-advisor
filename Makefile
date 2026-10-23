# Developer shortcuts. Run `make help` for the list.
PY := backend/.venv/bin/python
SEED ?= 42

.PHONY: help setup setup-backend setup-frontend env seed data validate migrate api web test test-backend test-postgres lint typecheck build e2e check db-up db-down clean

help:
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-16s %s\n", $$1, $$2}'

setup: setup-backend setup-frontend env ## Install everything and create local env files

setup-backend: ## Create backend venv and install pinned dependencies
	python3 -m venv backend/.venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r backend/requirements-dev.txt

setup-frontend: ## Install frontend dependencies from the lockfile
	cd frontend && npm ci

env: ## Create backend/.env and frontend/.env.local with fresh local secrets (never overwrites)
	@test -f backend/.env || { \
	  SECRET=$$(python3 -c "import secrets;print(secrets.token_urlsafe(48))"); \
	  PW=$$(python3 -c "import secrets;print('demo-'+secrets.token_urlsafe(9))"); \
	  sed -e "s|^LOCAL_JWT_SECRET=.*|LOCAL_JWT_SECRET=$$SECRET|" -e "s|^LOCAL_DEMO_PASSWORD=.*|LOCAL_DEMO_PASSWORD=$$PW|" \
	      -e "s|^SUPABASE_URL=.*|SUPABASE_URL=|" backend/.env.example > backend/.env; \
	  echo "Created backend/.env (demo password: see LOCAL_DEMO_PASSWORD)"; }
	@test -f frontend/.env.local || { cp frontend/.env.example frontend/.env.local; echo "Created frontend/.env.local"; }

seed: ## Load reproducible synthetic data into DATABASE_URL (SQLite by default)
	cd backend && .venv/bin/python -m app.synthetic_data.seed --seed $(SEED) --reset

data: ## Export synthetic data to data/generated (CSV + JSON)
	$(PY) scripts/generate_synthetic_data.py --seed $(SEED) --out data/generated

validate: ## Validate the synthetic dataset
	$(PY) scripts/validate_synthetic_data.py --seed $(SEED)

migrate: ## Apply SQL migrations to the PostgreSQL DATABASE_URL in backend/.env
	cd backend && .venv/bin/python -m app.db.migrate

api: ## Run the FastAPI backend on :8000
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

web: ## Run the Next.js frontend on :3000
	cd frontend && npm run dev

test: test-backend ## Run backend tests (unit, integration, security)

test-backend:
	cd backend && .venv/bin/python -m pytest -q

test-postgres: ## Run PostgreSQL-backed tests (needs TEST_DATABASE_URL; drops its public schema!)
	cd backend && .venv/bin/python -m pytest -q -m postgres

lint: ## Lint backend and frontend
	cd backend && .venv/bin/ruff check app tests ../scripts && .venv/bin/ruff format --check app tests ../scripts
	cd frontend && npm run lint

typecheck: ## TypeScript type check
	cd frontend && npm run typecheck

build: ## Production build of the frontend
	cd frontend && npm run build

e2e: ## Playwright journey (needs api + web running; E2E_PASSWORD=<LOCAL_DEMO_PASSWORD>)
	cd frontend && npm run e2e

check: ## Run all quality gates
	python3 scripts/run_quality_checks.py

db-up: ## Start local PostgreSQL with docker compose
	docker compose up -d db

db-down: ## Stop local PostgreSQL
	docker compose down

clean: ## Remove local build artefacts and the SQLite demo DB
	rm -rf frontend/.next backend/data/local.db backend/.pytest_cache data/generated
