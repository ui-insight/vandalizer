.DEFAULT_GOAL := help

BACKEND_DIR := backend
FRONTEND_DIR := frontend

.PHONY: help backend-install backend-lint backend-typecheck backend-test backend-security backend-audit review-graph endpoint-map endpoint-map-check backend-static backend-backlog backend-ci backend-test-integration-t1 backend-test-integration-t2 backend-test-integration-t3 backend-test-integration-t4 backend-judge-calibration frontend-install frontend-typecheck frontend-lint frontend-test frontend-build frontend-audit frontend-ci ci docker-build release-check security security-gate security-built-images

help:
	@printf "Common targets:\n"
	@printf "  make backend-install   Install backend dev dependencies\n"
	@printf "  make backend-ci        Run the backend release-gating test suite\n"
	@printf "  make backend-static    Run release-gating backend lint and security checks\n"
	@printf "  make backend-backlog   Run backend typecheck and dependency audit backlog\n"
	@printf "  make endpoint-map      Write the UI-to-endpoint map for reading\n"
	@printf "  make frontend-install  Install frontend dependencies\n"
	@printf "  make frontend-ci       Run frontend typecheck, lint, tests, and build\n"
	@printf "  make ci                Run backend and frontend CI checks\n"
	@printf "  make release-check     Run CI checks and both Docker builds\n"
	@printf "  make security          Full vulnerability report (deps, images, secrets, config)\n"
	@printf "  make security-gate     Release-gating scan: fails on CRITICAL or a leaked secret\n"
	@printf "  make security-built-images  Scan the published images (run after docker-build)\n"
	@printf "  make review-graph      Build/refresh the optional local code graph\n"

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

# Optional local code graph for review navigation. Deliberately not a
# prerequisite of any other target: it needs a third-party tool, so nothing
# here runs unless a person types it. See docs/review-graph.md.
#
# Absent a graph, `update` would create the database, index HEAD~1..HEAD, and
# exit 0 -- leaving a one-file graph that answers every query confidently and
# wrongly. Hence the explicit build branch. ORIG_HEAD (set by git across a
# pull) is the right base for a refresh; HEAD~1, the tool's default, would
# index only the last commit of a multi-commit pull.
review-graph:
	@command -v code-review-graph >/dev/null 2>&1 || { \
	  printf 'review-graph: code-review-graph is not installed.\n' >&2; \
	  printf '  install it with: uv tool install code-review-graph\n' >&2; \
	  printf '  it is optional -- no other make target needs it.\n' >&2; \
	  exit 1; }
	@if [ ! -f .code-review-graph/graph.db ]; then \
	  code-review-graph build; \
	else \
	  base=$${CRG_BASE:-$$(git rev-parse --verify --quiet ORIG_HEAD || echo HEAD~1)}; \
	  code-review-graph update --base "$$base"; \
	fi

# Writes scripts/ui_endpoint_map.md and .json for reading; regenerate on demand,
# never commit (see .gitignore).
endpoint-map:
	cd $(BACKEND_DIR) && uv run python ../scripts/map_ui_endpoints.py

# --stdout keeps the check read-only: plain --check still writes both timestamped
# output files, which would dirty the tree on every CI run.
endpoint-map-check:
	cd $(BACKEND_DIR) && uv run python ../scripts/map_ui_endpoints.py --check --stdout >/dev/null

backend-static: backend-lint backend-security endpoint-map-check

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

# Run the LLM-judge calibration suite against the fixture in
# tests/fixtures/judge_calibration.json. Opt-in (INTEGRATION_LLM=1 required)
# because it makes ~50 real LLM calls per run. Use to verify that the judge
# meets agreement / accuracy / length-bias thresholds before relying on it as
# an optimizer fitness function. Override thresholds via:
#   JUDGE_CALIBRATION_MIN_KAPPA, MIN_ACCURACY, MAX_LENGTH_BIAS
backend-judge-calibration:
	cd $(BACKEND_DIR) && INTEGRATION_LLM=1 uv run pytest tests/integration/test_tier3_llm.py::TestExtractionJudgeCalibration -x -v

backend-ci: backend-test backend-test-integration-t1

frontend-install:
	cd $(FRONTEND_DIR) && npm ci

frontend-typecheck:
	cd $(FRONTEND_DIR) && npm run typecheck

frontend-lint:
	cd $(FRONTEND_DIR) && npm run lint

# Coverage denominator is the whole frontend/src tree (see vitest.config.ts),
# not just what a test happens to import, so this number is honest and
# monotonic. Thresholds live in vitest.config.ts (single source) — bump them
# there as more components/hooks/api modules get tests.
frontend-test:
	cd $(FRONTEND_DIR) && npm run test:coverage

frontend-build:
	cd $(FRONTEND_DIR) && npm run build

# Fails on a critical advisory; warns and passes when the registry is
# unreachable. `npm audit` cannot tell those apart by exit code, and this
# target gates the release. See the script's header.
frontend-audit:
	./scripts/npm_audit_gate.sh

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

release-check: backend-static ci security-gate docker-build

# ---------------------------------------------------------------------------
# Vulnerability scanning (Trivy)
# ---------------------------------------------------------------------------
# Covers three things bandit / pip-audit / npm audit cannot see:
#
#   1. OS packages inside the runtime container images. Nothing scanned these
#      before, and they are where the highest-severity findings usually live —
#      the backend runtime (python:3.12-slim) currently carries ~23 HIGH, most
#      of them one util-linux CVE fanning across several packages and already
#      fixed upstream, so `docker build --pull` clears the bulk.
#   2. Committed secrets.
#   3. Dockerfile / IaC misconfiguration.
#
# It also reads both lockfiles, so it is the one place to look for dependency
# CVEs across Python and npm rather than reading two tools' output.
#
# Install: brew install trivy  (or see https://trivy.dev/latest/getting-started/installation/)

TRIVY ?= trivy
# Base images to scan. The frontend *builder* (node:24-alpine) is deliberately
# absent: its packages never reach a shipped artifact, and including it would
# put findings in front of reviewers that they cannot act on and should not
# care about. Scan what runs in production.
RUNTIME_IMAGES := python:3.12-slim nginx:alpine

security:
	@printf "\n=== Dependencies, secrets, and config ===\n"
	-$(TRIVY) fs --scanners vuln,secret,misconfig --severity HIGH,CRITICAL .
	@printf "\n=== Runtime base images ===\n"
	@for img in $(RUNTIME_IMAGES); do \
		printf "\n--- %s ---\n" "$$img"; \
		$(TRIVY) image --scanners vuln --severity HIGH,CRITICAL "$$img" || true; \
	done

# Release gate. Deliberately narrower than `make security`:
#
#   CRITICAL-with-a-fix-available, and leaked secrets, fail the build. Both are
#   zero today, so this is enforceable from the day it lands rather than being
#   switched on "later" — which is how the existing HIGH backlog became
#   invisible in the first place.
#
#   --ignore-unfixed is load-bearing, not a loophole. python:3.12-slim carries
#   four CRITICAL perl-base CVEs that Debian has published no fix for
#   (CVE-2026-13221, -42496, -57433, -8376). A gate that fails on those cannot
#   be made to pass by any action a developer can take, so it would be disabled
#   or bypassed within a week and would protect nothing. `make security` still
#   reports them; the *gate* is scoped to what someone can actually act on.
#   Track the unfixed ones by rebasing the image when Debian ships fixes, or by
#   moving off a base that ships perl at all.
#
#   HIGH stays advisory *for now*, matching the backend-typecheck / backend-audit
#   convention above. The difference from before is that it is now reported
#   rather than hidden: `npm audit --audit-level=critical` silently passed six
#   HIGH findings, and pip-audit's twenty-nine sat in a non-blocking target
#   nobody read. Tighten `--severity` here to HIGH,CRITICAL once the backlog is
#   worked down.
security-gate:
	$(TRIVY) fs --scanners vuln --severity CRITICAL --ignore-unfixed --exit-code 1 .
	$(TRIVY) fs --scanners secret --exit-code 1 .
	@for img in $(RUNTIME_IMAGES); do \
		$(TRIVY) image --scanners vuln --severity CRITICAL --ignore-unfixed --exit-code 1 "$$img" || exit 1; \
	done
	@printf "\nNo fixable CRITICAL vulnerabilities and no leaked secrets.\n"

# Scans the images we *publish*, which is what a deploying campus actually
# pulls from ghcr.io. This is strictly broader than scanning the base images
# above, and the difference is not academic:
#
#   backend/Dockerfile runs `playwright install --with-deps chromium`, which
#   installs Chromium and its entire apt dependency tree into the shipped
#   runtime image. Those packages appear in neither uv.lock nor the
#   python:3.12-slim base scan, so until now nothing looked at them at all —
#   and the browser path they serve became more heavily used when the
#   blocked-URL fallback was fixed.
#
# Requires `make docker-build` first (the images must exist locally).
# Advisory rather than gating for now: the Chromium dependency set has never
# been scanned, so the finding count is unknown and a gate switched on blind
# would either be vacuous or block the release pipeline on day one. Promote it
# to security-gate once a few runs have established the real baseline.
BUILT_IMAGES := vandalizer-backend vandalizer-frontend

security-built-images:
	@for img in $(BUILT_IMAGES); do \
		printf "\n--- %s (published artifact) ---\n" "$$img"; \
		$(TRIVY) image --scanners vuln --severity HIGH,CRITICAL "$$img" || true; \
	done
