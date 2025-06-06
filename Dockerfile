FROM python:3.13 AS builder

RUN pip install uv

WORKDIR /app

COPY pyproject.toml ./
RUN touch README.md

RUN uv sync

FROM python:3.13-slim AS runtime

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}

COPY . .

EXPOSE 8000

ENTRYPOINT ["gunicorn"]