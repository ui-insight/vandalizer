"""Shared fixtures for integration tests."""

import os
from uuid import uuid4

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Tier 1: Celery eager mode
# ---------------------------------------------------------------------------

@pytest.fixture
def celery_eager():
    """Run Celery tasks synchronously in-process."""
    from app.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


# ---------------------------------------------------------------------------
# Tier 2: Real MongoDB via Motor / Beanie
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mongo_db_name():
    """Generate a unique test database name for the session."""
    return f"osp_test_{uuid4().hex[:8]}"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def mongo_client(mongo_db_name):
    """Session-scoped: init Beanie with a disposable test database."""
    from motor.motor_asyncio import AsyncIOMotorClient

    from beanie import init_beanie
    from app.database import ALL_MODELS

    client = AsyncIOMotorClient("mongodb://localhost:27017/")
    await init_beanie(database=client[mongo_db_name], document_models=ALL_MODELS)
    yield client
    await client.drop_database(mongo_db_name)
    client.close()


@pytest.fixture(scope="session")
def sync_mongo(mongo_db_name, mongo_client):
    """Sync pymongo client for the same test database."""
    from pymongo import MongoClient

    client = MongoClient("mongodb://localhost:27017/")
    yield client[mongo_db_name]
    client.close()


@pytest_asyncio.fixture(autouse=True)
async def clean_collections(request, mongo_db_name):
    """Drop all documents between tests (only for tier2 tests)."""
    # Only run for tests that use MongoDB (have mongo_client in their fixtures)
    if "mongo_client" not in request.fixturenames:
        yield
        return

    yield

    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient("mongodb://localhost:27017/")
    db = client[mongo_db_name]
    for name in await db.list_collection_names():
        await db[name].delete_many({})
    client.close()
