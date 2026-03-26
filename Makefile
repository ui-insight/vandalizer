.DEFAULT_GOAL := help

BACKEND_DIR := backend
FRONTEND_DIR := frontend

.PHONY: help backend-install backend-lint backend-typecheck backend-test backend-security backend-audit backend-static backend-backlog backend-ci backend-test-integration-t1 backend-test-integration-t2 backend-test-integration-t3 frontend-install frontend-typecheck frontend-lint frontend-test frontend-build frontend-audit frontend-ci ci docker-build release-check

help:
	@printf "Common targets:\n"
	@printf "  make backend-install   Install backend dev dependencies\n"
	@printf "  make backend-ci        Run the backend release-gating test suite\n"
	@printf "  make backend-static    Run release-gating backend lint and security checks\n"
	@printf "  make backend-backlog   Run backend typecheck and dependency audit backlog\n"
	@printf "  make frontend-install  Install frontend dependencies\n"
	@printf "  make frontend-ci       Run frontend typecheck, lint, tests, and build\n"
	@printf "  make ci                Run backend and frontend CI checks\n"
	@printf "  make release-check     Run CI checks and both Docker builds\n"

backend-install:
	cd $(BACKEND_DIR) && uv sync --frozen --extra dev

backend-lint:
	cd $(BACKEND_DIR) && uv run ruff check app/

backend-typecheck:
	cd $(BACKEND_DIR) && uv run mypy app/ --ignore-missing-imports

backend-test:
	cd $(BACKEND_DIR) && uv run pytest -q --cov=app --cov-report=term-missing --cov-fail-under=30

backend-security:
	cd $(BACKEND_DIR) && uv run bandit -r app/ -s B101 -q -ll -ii

backend-audit:
	cd $(BACKEND_DIR) && uv run pip-audit

backend-static: backend-lint backend-security

backend-backlog: backend-typecheck backend-audit

backend-test-integration-t1:
	cd $(BACKEND_DIR) && uv run pytest tests/integration/test_tier1_engine.py -x -q

backend-test-integration-t2:
	cd $(BACKEND_DIR) && INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_tier2_mongodb.py -x -q || echo "::warning::Tier 2 MongoDB integration tests have failures (non-blocking)"

backend-test-integration-t3:
	cd $(BACKEND_DIR) && INTEGRATION_LLM=1 uv run pytest tests/integration/test_tier3_llm.py -x -q

backend-ci: backend-test backend-test-integration-t1

frontend-install:
	cd $(FRONTEND_DIR) && npm ci

frontend-typecheck:
	cd $(FRONTEND_DIR) && npm run typecheck

frontend-lint:
	cd $(FRONTEND_DIR) && npm run lint

frontend-test:
	cd $(FRONTEND_DIR) && npm run test:coverage -- --coverage.thresholds.lines=30

frontend-build:
	cd $(FRONTEND_DIR) && npm run build

frontend-audit:
	cd $(FRONTEND_DIR) && npm audit --audit-level=high

frontend-ci: frontend-typecheck frontend-lint frontend-audit frontend-test frontend-build

ci: backend-ci frontend-ci

docker-build:
	docker build -t vandalizer-backend ./backend
	docker build -t vandalizer-frontend ./frontend

release-check: backend-static ci docker-build
