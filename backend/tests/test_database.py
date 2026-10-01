"""Tests for app.database.init_db index-management behavior.

Beanie's per-collection index management (the listIndexes round-trips) is
idempotent and only needs to run once per process. Re-running it on every
short-lived async Celery task is an N+1 in the span waterfall
(tasks.document.classify et al.), so init_db ensures indexes once then
auto-skips.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.database as database
from app.config import Settings


def _settings() -> Settings:
    return Settings(jwt_secret_key="test-secret-key", environment="development")


@pytest.fixture(autouse=True)
def _reset_indexes_flag():
    database._indexes_ensured = False
    database._beanie_inited = False
    yield
    database._indexes_ensured = False
    database._beanie_inited = False


@pytest.mark.asyncio
async def test_indexes_ensured_once_then_auto_skipped():
    with patch("app.database.AsyncIOMotorClient"), \
         patch("app.database.init_beanie", new_callable=AsyncMock) as mock_init:
        await database.init_db(_settings())
        await database.init_db(_settings())
        await database.init_db(_settings())

    skips = [c.kwargs["skip_indexes"] for c in mock_init.call_args_list]
    # First call ensures indexes; every subsequent call in the process skips
    # the listIndexes round-trips.
    assert skips == [False, True, True]
    assert database._indexes_ensured is True


@pytest.mark.asyncio
async def test_explicit_skip_does_not_mark_ensured():
    with patch("app.database.AsyncIOMotorClient"), \
         patch("app.database.init_beanie", new_callable=AsyncMock) as mock_init:
        await database.init_db(_settings(), skip_indexes=True)
        # An explicit skip must not claim indexes were ensured, so a later
        # default call still runs index management once.
        assert database._indexes_ensured is False
        await database.init_db(_settings())

    skips = [c.kwargs["skip_indexes"] for c in mock_init.call_args_list]
    assert skips == [True, False]
    assert database._indexes_ensured is True


# --- rebinding instead of re-running init_beanie ---------------------------
# init_beanie issues one buildInfo per model (~70) even with skip_indexes, and
# every async Celery task gets a fresh client (Sentry 7598699011, N+1 on
# tasks.document.classify). After the first full init a task only rebinds.


def _model(name, **settings):
    model = MagicMock()
    model.get_settings.return_value = SimpleNamespace(
        name=name, timeseries=settings.get("timeseries"), union_doc=settings.get("union_doc"),
    )
    return model


@pytest.mark.asyncio
async def test_later_inits_rebind_models_instead_of_rerunning_init_beanie():
    models = [_model("users"), _model("smart_document")]
    with patch("app.database.AsyncIOMotorClient") as client_cls, \
         patch("app.database.init_beanie", new_callable=AsyncMock) as mock_init, \
         patch.object(database, "ALL_MODELS", models):
        await database.init_db(_settings())
        await database.init_db(_settings())
        await database.init_db(_settings())

    assert mock_init.await_count == 1
    new_db = client_cls.return_value.__getitem__.return_value
    for model in models:
        assert model.set_database.call_count == 2
        model.set_database.assert_called_with(new_db)
        model.set_collection.assert_called_with(new_db[model.get_settings().name])


@pytest.mark.asyncio
async def test_a_default_call_still_ensures_indexes_after_an_explicit_skip():
    """A process whose first init skipped indexes has not ensured them, so the
    next default call runs init_beanie with indexes rather than rebinding."""
    models = [_model("users")]
    with patch("app.database.AsyncIOMotorClient"), \
         patch("app.database.init_beanie", new_callable=AsyncMock) as mock_init, \
         patch.object(database, "ALL_MODELS", models):
        await database.init_db(_settings(), skip_indexes=True)
        await database.init_db(_settings())
        await database.init_db(_settings())

    assert [c.kwargs["skip_indexes"] for c in mock_init.call_args_list] == [True, False]
    assert database._indexes_ensured is True


@pytest.mark.asyncio
async def test_a_model_rebinding_cannot_cover_falls_back_to_init_beanie():
    models = [_model("users"), _model("metrics", timeseries=object())]
    with patch("app.database.AsyncIOMotorClient"), \
         patch("app.database.init_beanie", new_callable=AsyncMock) as mock_init, \
         patch.object(database, "ALL_MODELS", models):
        await database.init_db(_settings())
        await database.init_db(_settings())

    assert mock_init.await_count == 2
    models[0].set_database.assert_not_called()


# --- connection pool warmth ---------------------------------------------------
# Sentry 7764120249: per-task clients pre-filled a 10-connection pool in the
# background; a Mongo stutter cancelled those half-open connects and pymongo
# logged each as an error. Only the long-lived web client keeps a warm pool.


@pytest.mark.asyncio
async def test_task_clients_open_connections_on_demand():
    with patch("app.database.AsyncIOMotorClient") as client_cls, \
         patch("app.database.init_beanie", new_callable=AsyncMock):
        await database.init_db(_settings())
    assert client_cls.call_args.kwargs["minPoolSize"] == 0


@pytest.mark.asyncio
async def test_the_web_app_keeps_a_warm_pool():
    with patch("app.database.AsyncIOMotorClient") as client_cls, \
         patch("app.database.init_beanie", new_callable=AsyncMock):
        await database.init_db(_settings(), warm_pool=True)
    assert client_cls.call_args.kwargs["minPoolSize"] == 10


def test_the_web_app_asks_for_the_warm_pool():
    import inspect

    import app.main as main

    assert "warm_pool=True" in inspect.getsource(main.lifespan)
