import pytest
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session", autouse=True)
def _celery_in_memory():
    """Keep unit tests off a real broker and result backend.

    Without this, every ``.delay()``/``send_task()`` a test reaches blocks ~19s
    retrying the redis *result backend* (20 retries, 1s ceiling) before raising.
    CI runs no redis service, so that is the default experience there.

    Overriding the broker alone does not help: the broker publish already fails
    fast on ECONNREFUSED, and it is the result backend that retries. See #615.

    Deliberately not ``task_always_eager`` — that would run tasks inline and
    change semantics. These tests only care that a dispatch was attempted.
    """
    from app.celery_app import celery

    celery.conf.result_backend = "cache+memory://"
    celery.conf.broker_url = "memory://"


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
