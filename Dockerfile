FROM python:3.13 AS builder

RUN pip install uv

WORKDIR /app

COPY pyproject.toml ./

RUN uv sync

FROM python:3.13-alpine AS runtime

WORKDIR /app

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

COPY app ./app
COPY certs ./
COPY gunicorn.conf.py ./
COPY run_celery.sh ./

EXPOSE 8000

CMD ["gunicorn"]