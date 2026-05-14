.DEFAULT_GOAL := help

BACKEND_DIR := backend
FRONTEND_DIR := frontend

.PHONY: help backend-install backend-lint backend-typecheck backend-test backend-security backend-audit backend-static backend-backlog backend-ci backend-test-integration-t1 backend-test-integration-t2 backend-test-integration-t3 backend-test-integration-t4 frontend-install frontend-typecheck frontend-lint frontend-test frontend-build frontend-audit frontend-ci ci docker-build release-check

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

# Coverage gate set just below current measured (~51%). Bump as untested
# modules (m365_tasks, demo_tasks, support_service, passive_tasks, etc.)
# get test coverage. Don't drop below 50% without an explicit reason.
backend-test:
	cd $(BACKEND_DIR) && uv run pytest -q --cov=app --cov-report=term-missing --cov-fail-under=50

backend-security:
	cd $(BACKEND_DIR) && uv run bandit -r app/ -s B101 -q -ll -ii

backend-audit:
	cd $(BACKEND_DIR) && uv run pip-audit

backend-static: backend-lint backend-security

backend-backlog: backend-typecheck backend-audit

# Advisory jobs split for independent progress tracking. Both are non-blocking
# in CI today: backend-typecheck has ~924 errors (mypy was added late), and
# backend-audit has open CVEs in indirect deps. As either reaches zero, flip
# the corresponding `continue-on-error` to `false` in .github/workflows/ci.yaml.

backend-test-integration-t1:
	cd $(BACKEND_DIR) && uv run pytest tests/integration/test_tier1_engine.py -x -q

backend-test-integration-t2:
	cd $(BACKEND_DIR) && INTEGRATION_MONGODB=1 uv run pytest tests/integration/test_tier2_mongodb.py -x -q

backend-test-integration-t3:
	cd $(BACKEND_DIR) && INTEGRATION_LLM=1 uv run pytest tests/integration/test_tier3_llm.py -x -q

backend-test-integration-t4:
	cd $(BACKEND_DIR) && INTEGRATION_CHROMA=1 uv run pytest tests/integration/test_tier4_chroma.py -x -q

backend-ci: backend-test backend-test-integration-t1

frontend-install:
	cd $(FRONTEND_DIR) && npm ci

frontend-typecheck:
	cd $(FRONTEND_DIR) && npm run typecheck

frontend-lint:
	cd $(FRONTEND_DIR) && npm run lint

# Coverage gate set just below current measured (~44%). Bump as more
# components/hooks/api modules get tests.
frontend-test:
	cd $(FRONTEND_DIR) && npm run test:coverage -- --coverage.thresholds.lines=40

frontend-build:
	cd $(FRONTEND_DIR) && npm run build

frontend-audit:
	cd $(FRONTEND_DIR) && npm audit --audit-level=critical

frontend-ci: frontend-typecheck frontend-lint frontend-audit frontend-test frontend-build

ci: backend-ci frontend-ci

docker-build:
	docker build -t vandalizer-backend ./backend
	# Forward Sentry build-args from the shell. Unset vars expand to empty,
	# which makes initSentry() a no-op (matches the no-DSN dev case).
	docker build \
		--build-arg VITE_SENTRY_DSN="$$VITE_SENTRY_DSN" \
		--build-arg VITE_SENTRY_ENVIRONMENT="$$VITE_SENTRY_ENVIRONMENT" \
		--build-arg VITE_SENTRY_RELEASE="$$VITE_SENTRY_RELEASE" \
		-t vandalizer-frontend ./frontend

release-check: backend-static ci docker-build
