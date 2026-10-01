"""Tier 2: init_db across event loops, the way async Celery tasks call it.

Each task builds a fresh event loop and calls init_db, which makes a fresh
Motor client. After the first full init_beanie, later calls rebind the models
to the new client instead of re-running init_beanie (one buildInfo per model).
This checks the rebound models really work on the new client and loop.
Set INTEGRATION_MONGODB=1 to run.
"""

import asyncio
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("INTEGRATION_MONGODB"),
        reason="Set INTEGRATION_MONGODB=1 to run MongoDB integration tests",
    ),
    pytest.mark.integration_tier2,
]


def test_models_work_on_each_tasks_own_loop_after_rebinding():
    import app.database as database
    from app.config import Settings
    from app.models.system_config import SystemConfig

    db_name = f"osp_test_rebind_{uuid4().hex[:8]}"
    settings = Settings(
        jwt_secret_key="test-secret-key", environment="development",
        mongo_host="mongodb://localhost:27017/", mongo_db=db_name,
    )
    saved = (database._indexes_ensured, database._beanie_inited)
    database._indexes_ensured = database._beanie_inited = False

    async def task(i: int) -> int:
        await database.init_db(settings)
        await SystemConfig(llm_endpoint=f"http://example/{i}").insert()
        return await SystemConfig.find_all().count()

    real_init = database.init_beanie
    calls = []

    async def counting_init(**kwargs):
        calls.append(kwargs)
        return await real_init(**kwargs)

    try:
        with patch.object(database, "init_beanie", side_effect=counting_init):
            counts = []
            for i in range(3):
                loop = asyncio.new_event_loop()
                try:
                    counts.append(loop.run_until_complete(task(i)))
                finally:
                    loop.close()
        assert counts == [1, 2, 3]
        assert len(calls) == 1  # later tasks rebound instead
    finally:
        # Its own client: the last task's is bound to a loop that is closed.
        from pymongo import MongoClient

        cleanup = MongoClient("mongodb://localhost:27017/")
        cleanup.drop_database(db_name)
        cleanup.close()
        database._indexes_ensured, database._beanie_inited = saved
