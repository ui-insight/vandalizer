"""The engagement Celery tasks must be able to start up.

Each task opens its own event loop and calls ``init_db`` before running the
service. ``init_db`` requires settings; three tasks once called it bare and
raised ``TypeError`` on every run, so the scheduled v5 drip and power-user
emails never sent. These tests run each task body with a signature-checked
``init_db`` so a bare call fails here instead of in production.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.tasks import engagement_tasks

TASKS = [
    ("process_onboarding_drips", "process_onboarding_drips"),
    ("process_inactivity_nudges", "process_inactivity_nudges"),
    ("process_v5_launch_announcement", "process_v5_launch_announcement"),
    ("process_agentic_chat_drip", "process_agentic_chat_drip"),
    ("process_powerup_milestones", "process_powerup_milestones"),
]


@pytest.mark.parametrize("task_name,service_name", TASKS)
def test_task_initializes_the_database_and_runs_the_service(task_name, service_name):
    task = getattr(engagement_tasks, task_name)
    with patch("app.database.init_db", autospec=True) as init_db, \
         patch(f"app.services.engagement_service.{service_name}", AsyncMock(return_value=3)) as run:
        result = task.run()

    assert result == {"sent": 3}
    init_db.assert_awaited_once()
    run.assert_awaited_once()


def test_every_engagement_task_is_covered():
    registered = {
        name for name, obj in vars(engagement_tasks).items()
        if hasattr(obj, "run") and getattr(obj, "name", "").startswith("tasks.engagement.")
    }
    assert registered == {name for name, _ in TASKS}
