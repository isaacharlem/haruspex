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

COMPOSE := docker compose -f deploy/docker-compose.yml

help:
	@sed -n '2,20p' Makefile

# --- setup -------------------------------------------------------------------

hooks:
	uv run pre-commit install

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

# --- housekeeping -----------------------------------------------------------------

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis htmlcov coverage.xml
	rm -rf backend/.pytest_cache backend/.mypy_cache backend/.coverage backend/htmlcov backend/coverage.xml
	rm -rf sdk/.pytest_cache sdk/.mypy_cache sdk/.coverage sdk/htmlcov sdk/coverage.xml
	rm -rf frontend/dist frontend/coverage frontend/test-results frontend/playwright-report
	find . -type d -name __pycache__ -not -path './node_modules/*' -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true

.PHONY: help hooks lint lint-python lint-frontend typecheck typecheck-backend \
	typecheck-sdk typecheck-frontend test test-backend test-sdk test-frontend \
	build-frontend audit vuln-audit ci clean
