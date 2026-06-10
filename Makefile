# Haruspex — make targets
#
#   dev         run db (compose) + api/worker hot-reload + vite dev server
#   demo        full compose demo: stack up, backfill 40 runs, stream 8 live
#   test        all test suites with coverage gates (backend, sdk, frontend)
#   lint        ruff check + format --check, eslint
#   typecheck   mypy (backend, sdk --strict) + tsc --noEmit
#   hooks       install the pre-commit commit gate
#   ci          everything CI runs: lint, typecheck, test, audit, contract
#   audit       placeholder audit + pre-commit run --all-files + gitleaks
#   smoke       end-to-end curl smoke test against the compose stack
#   e2e         Playwright spec against the compose demo
#   migrate     alembic upgrade head against $HARUSPEX_DATABASE_URL
#   keys        mint an admin API key against the running db
#   clean       remove caches, coverage, build artifacts
#
# Every CI job executes a make target, so local `make ci` green => CI green.

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Compose interpolates ${VAR}s from the repo-root .env (when present) via an
# explicit --env-file; by default it would look for deploy/.env and silently
# find nothing. --project-directory is NOT used: it would re-anchor the
# compose file's relative build contexts and break image builds.
COMPOSE_ENV := $(if $(wildcard .env),--env-file .env,)
COMPOSE := docker compose $(COMPOSE_ENV) -f deploy/docker-compose.yml
# Imports via PYTHONPATH for local (non-container) entrypoints: immune to the
# macOS uv/UF_HIDDEN editable-install issue (see DECISIONS.md).
PY_ENV := PYTHONPATH=$(CURDIR)/backend/src:$(CURDIR)/sdk/src

help:
	@sed -n '2,20p' Makefile

# --- setup -------------------------------------------------------------------

hooks:
	uv run pre-commit install

# macOS: uv marks the venv UF_HIDDEN on installs and CPython >= 3.12.13 skips
# hidden .pth files, breaking editable imports for runtime entrypoints
# (uvicorn, haruspex-simulate, cli). No-op elsewhere.
fix-venv:
	@command -v chflags >/dev/null 2>&1 && chflags -R nohidden .venv 2>/dev/null || true

# --- lint / typecheck ----------------------------------------------------------

lint: lint-python lint-frontend

lint-python:
	uv run ruff check backend sdk
	uv run ruff format --check backend sdk

lint-frontend:
	pnpm -C frontend exec eslint . --max-warnings 0

typecheck: typecheck-backend typecheck-sdk typecheck-frontend

typecheck-backend:
	cd backend && uv run mypy src/haruspex_server

typecheck-sdk:
	cd sdk && uv run mypy --strict src/haruspex

typecheck-frontend:
	pnpm -C frontend exec tsc --noEmit

# --- tests ---------------------------------------------------------------------

test: test-backend test-sdk test-frontend

test-backend:
	cd backend && uv run pytest --cov --cov-fail-under=85 -q
	cd backend && uv run coverage report --include='*/forecaster/*' --fail-under=95 \
		| tail -2

test-sdk:
	cd sdk && uv run pytest --cov --cov-fail-under=90 -q

test-frontend:
	pnpm -C frontend run test

build-frontend:
	pnpm -C frontend run build

# --- audits ----------------------------------------------------------------------

audit:
	./scripts/check_no_placeholders.sh
	uv run pre-commit run --all-files
	@if command -v gitleaks >/dev/null 2>&1; then \
		gitleaks git --no-banner --redact .; \
	else \
		echo "gitleaks not installed locally; CI runs it (brew install gitleaks)"; \
	fi

vuln-audit:
	uvx pip-audit || true
	cd frontend && pnpm audit || true

# --- aggregate CI -----------------------------------------------------------------

ci: lint typecheck test audit

# --- demo / stack -------------------------------------------------------------------

demo:
	$(COMPOSE) --profile demo up -d --build
	@echo "Waiting for the demo seeder to mint a dashboard key..."
	@key_seen=0; for i in $$(seq 1 60); do \
		if $(COMPOSE) logs demo 2>/dev/null | grep -q 'DASHBOARD KEY:'; then key_seen=1; break; fi; \
		sleep 2; done; \
	if [ $$key_seen -eq 1 ]; then \
		$(COMPOSE) logs --no-log-prefix demo | sed -n '/HARUSPEX DEMO/,/^=*$$/p' | head -20; \
		echo ""; \
		echo "Follow the live runs: $(COMPOSE) logs -f demo"; \
	else \
		echo "Demo seeder did not report a key yet; check: $(COMPOSE) logs demo"; \
	fi

stack-up:
	$(COMPOSE) up -d --build db api worker frontend

stack-down:
	$(COMPOSE) --profile demo down

smoke:
	./scripts/smoke.sh

contract:
	./scripts/contract.sh

e2e:
	@KEY=$$($(COMPOSE) logs --no-log-prefix demo 2>/dev/null | grep 'DASHBOARD KEY:' | tail -1 | awk '{print $$NF}'); \
	if [ -z "$$KEY" ]; then echo "e2e needs the demo running: make demo"; exit 1; fi; \
	E2E_API_KEY=$$KEY pnpm -C frontend exec playwright test

# --- database / ops ----------------------------------------------------------------

db-up:
	$(COMPOSE) up -d db
	@until $(COMPOSE) exec db pg_isready -U haruspex -q 2>/dev/null; do sleep 1; done
	@echo "db ready on localhost:55432"

migrate: db-up fix-venv
	cd backend && uv run alembic upgrade head

keys: fix-venv
	cd backend && $(PY_ENV) uv run python -m haruspex_server.cli mint-key --name local-admin --scopes ingest,read,admin

dev: migrate
	@echo "Starting api (:8000), worker, and vite (:5173). Ctrl-C stops all."
	@trap 'kill 0' INT TERM; \
	(cd backend && $(PY_ENV) uv run uvicorn --factory haruspex_server.api.app:create_app --reload --port 8000) & \
	(cd backend && $(PY_ENV) uv run python -m haruspex_server.worker) & \
	pnpm -C frontend run dev & \
	wait

# --- housekeeping -----------------------------------------------------------------

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis htmlcov coverage.xml
	rm -rf backend/.pytest_cache backend/.mypy_cache backend/.coverage backend/htmlcov backend/coverage.xml
	rm -rf sdk/.pytest_cache sdk/.mypy_cache sdk/.coverage sdk/htmlcov sdk/coverage.xml
	rm -rf frontend/dist frontend/coverage frontend/test-results frontend/playwright-report
	find . -type d -name __pycache__ -not -path './node_modules/*' -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true

.PHONY: help hooks fix-venv lint lint-python lint-frontend typecheck typecheck-backend \
	typecheck-sdk typecheck-frontend test test-backend test-sdk test-frontend \
	build-frontend audit vuln-audit ci demo stack-up stack-down smoke contract e2e \
	db-up migrate keys dev clean
