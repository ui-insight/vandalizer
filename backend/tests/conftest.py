import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient


class _Field:
    """Stand-in for a Beanie ExpressionField.

    Every comparison yields a sentinel instead of a real query expression, so
    services' filters (``Model.recapture_step < N``, ``Model.due <= now``)
    build without ``init_beanie``. The ordering operators are why this exists
    rather than the plain string sentinel used elsewhere in the suite.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def _expr(self, op: str, other: object) -> str:
        return f"<field:{self.name} {op} {other!r}>"

    def __eq__(self, other):  # type: ignore[override]
        return self._expr("==", other)

    def __ne__(self, other):  # type: ignore[override]
        return self._expr("!=", other)

    def __lt__(self, other):
        return self._expr("<", other)

    def __le__(self, other):
        return self._expr("<=", other)

    def __gt__(self, other):
        return self._expr(">", other)

    def __ge__(self, other):
        return self._expr(">=", other)

    __hash__ = object.__hash__


class _FieldMeta(type):
    """Return a comparable sentinel for any unset class attribute."""

    def __getattr__(cls, name):
        return _Field(name)


def fake_model(docs: list | None = None, *, find_one_result=None):
    """A stand-in Beanie Document class with mocked find()/find_one()."""

    query = MagicMock()
    query.to_list = AsyncMock(return_value=docs or [])

    class _Fake(metaclass=_FieldMeta):
        pass

    _Fake.find = MagicMock(return_value=query)
    _Fake.find_one = AsyncMock(return_value=find_one_result)
    return _Fake


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
