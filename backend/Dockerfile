FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Build-time version identifier (release tag, SHA, or "dev"). Written to
# /app/VERSION so the app can self-report its version at runtime.
ARG VERSION=dev

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home appuser

WORKDIR /app

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    VANDALIZER_VERSION=${VERSION} \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

RUN echo "${VERSION}" > /app/VERSION

COPY --from=builder /app/.venv /app/.venv

# Install headless Chromium for the web_fetcher's JS-rendering fallback.
# ``--with-deps`` pulls in the system libraries Chromium needs (libnss3,
# libdrm2, libxkbcommon0, libgbm1, libasound2, fontconfig, etc.).  Browsers
# are written to PLAYWRIGHT_BROWSERS_PATH so they're readable by appuser.
#
# WEB_FETCHER_BROWSER_ENABLED=false disables the *feature* at runtime. It does
# NOT skip this install -- it is an application env var and cannot affect a
# build-time RUN. A deployment that turns the feature off still ships the whole
# Chromium dependency tree: measured at ~1.04 GB and 112 OS packages on top of
# the base image (87 -> 199), including two CRITICAL CVEs with no Debian fix
# (libglib2.0-0t64 CVE-2026-58016, libxml2 CVE-2026-6653).
#
# INSTALL_BROWSER=false skips the install and is the only way to not ship it.
# Default true, so an existing build is byte-identical and opting out is
# explicit.
#
# The same arg sets the runtime default immediately below, which is what keeps
# the two in step: an image built without the browser must not attempt to launch
# one. Note the Python ``playwright`` package is a plain runtime dependency
# (pyproject.toml) and is installed by ``uv sync`` either way -- so a browserless
# build does NOT take _render_with_browser's ImportError branch. It reaches
# ``p.chromium.launch()``, which raises, is caught and logged, and returns None;
# both call sites handle that (the blocked-URL path re-raises the original status
# error, the thin-content path keeps its static text). Correct, but it costs a
# failed launch and a warning per qualifying fetch -- hence the runtime default.
ARG INSTALL_BROWSER=true
ENV WEB_FETCHER_BROWSER_ENABLED=${INSTALL_BROWSER}
# The install below tests for the literal string "true", while the ENV above
# takes the raw value and pydantic reads 1/yes/on/TRUE as true. Any spelling
# but the two literals therefore splits them: no Chromium in the image, and an
# app configured to launch one -- a failed launch and a warning per qualifying
# fetch. compose.yaml routes operator environment into this arg, so "1" is a
# reachable thing to type. Reject it here rather than ship the split.
RUN case "$INSTALL_BROWSER" in \
      true|false) ;; \
      *) echo "INSTALL_BROWSER must be exactly 'true' or 'false' (got '$INSTALL_BROWSER')" >&2; exit 1 ;; \
    esac; \
    if [ "$INSTALL_BROWSER" = "true" ]; then \
        playwright install --with-deps chromium && \
        chmod -R a+rx /opt/ms-playwright; \
    fi

COPY app ./app
COPY certification-data ./certification-data
COPY scripts ./scripts
COPY seeds ./seeds
# The κ-drift ledger. Without it the admin Quality panel reads an empty
# history in every deployment and reports every model as unmeasured —
# including one running exactly the model CI measured.
COPY tests/fixtures/judge_drift_history.jsonl ./tests/fixtures/judge_drift_history.jsonl
COPY bootstrap_install.py ./
COPY celery_worker.py ./
COPY create_admin.py ./
COPY run_celery.sh ./
COPY setup_default_team.py ./

RUN mkdir -p /app/static/uploads /app/static/db && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8001

ENV WEB_WORKERS=2

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/health')" || exit 1

CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers ${WEB_WORKERS}"
