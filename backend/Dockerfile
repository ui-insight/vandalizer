FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --create-home appuser

WORKDIR /app

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder /app/.venv /app/.venv

COPY app ./app
COPY scripts ./scripts
COPY seeds ./seeds
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
