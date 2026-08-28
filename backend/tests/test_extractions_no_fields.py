"""An extraction with no fields must not run, and a run that extracts nothing
must not be recorded as completed.

Support ticket: with no fields defined, Run started an extraction that
finished in milliseconds, toasted "returned no values — see the History tab
for details", and left a green "completed" run in History that opened
nothing — once per click. Mocked models — no DB.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.models.activity import ActivityStatus
from app.routers.extractions import EXTRACTION_NO_VALUES_ERROR
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="user1"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.token_version = 0
    user.demo_status = None
    user.api_token_hash = None
    user.api_token_created_at = None
    user.api_token_expires_at = None
    return user


def _auth(user_id="user1"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


def _run_sync_patches(user, *, keys, results):
    """The run-sync route with auth, document access, activity and the
    service stubbed. Returns the context stack + the mocks that matter."""
    search_set = MagicMock()
    search_set.title = "Award Terms"
    search_set.uuid = "ss-1"
    document = MagicMock()
    document.uuid = "doc-1"
    activity = MagicMock()
    activity.id = "activity-1"

    ctx = [
        patch("app.dependencies.decode_token", return_value={"sub": user.user_id, "type": "access"}),
        patch("app.dependencies.User"),
        patch("app.routers.extractions.access_control.get_authorized_search_set", new_callable=AsyncMock, return_value=search_set),
        patch("app.routers.extractions.access_control.get_team_access_context", new_callable=AsyncMock, return_value=MagicMock()),
        patch("app.routers.extractions.access_control.get_authorized_document", new_callable=AsyncMock, return_value=document),
        patch("app.routers.extractions.activity_service"),
        patch("app.routers.extractions.svc"),
        patch("app.services.metering.metered_async"),
        patch("app.tasks.quality_tasks.auto_validate_extraction"),
    ]
    return ctx, activity, keys, results


async def _post_run(client, user, keys, results):
    cookies, headers = _auth(user.user_id)
    ctx, activity, keys, results = _run_sync_patches(user, keys=keys, results=results)
    from contextlib import AsyncExitStack, ExitStack

    with ExitStack() as stack:
        mocks = [stack.enter_context(c) for c in ctx]
        MockUser, mock_activity, mock_svc, mock_metered = mocks[1], mocks[5], mocks[6], mocks[7]
        MockUser.find_one = AsyncMock(return_value=user)
        mock_activity.activity_start = AsyncMock(return_value=activity)
        mock_activity.activity_finish = AsyncMock()
        mock_activity.activity_update = AsyncMock()
        mock_svc.get_extraction_keys = AsyncMock(return_value=keys)
        mock_svc.run_extraction_sync = AsyncMock(return_value=results)
        # metered_async is an async context manager; make the stub one too.
        mock_metered.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_metered.return_value.__aexit__ = AsyncMock(return_value=False)
        async with AsyncExitStack():
            resp = await client.post(
                "/api/extractions/run-sync",
                json={"search_set_uuid": "ss-1", "document_uuids": ["doc-1"]},
                cookies=cookies, headers=headers,
            )
        return resp, mock_activity, mock_svc


class TestRunSyncWithoutFields:
    @pytest.mark.asyncio
    async def test_no_fields_is_refused_before_any_run_is_recorded(self, client):
        user = _make_user()
        resp, mock_activity, mock_svc = await _post_run(client, user, keys=[], results=[])

        assert resp.status_code == 400
        assert "no fields yet" in resp.json()["detail"]
        mock_activity.activity_start.assert_not_called()
        mock_svc.run_extraction_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_with_no_values_is_recorded_as_failed_and_says_so(self, client):
        user = _make_user()
        resp, mock_activity, mock_svc = await _post_run(client, user, keys=["award_number"], results=[])

        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []
        assert body["error"] == EXTRACTION_NO_VALUES_ERROR
        mock_activity.activity_finish.assert_awaited_once_with(
            "activity-1", ActivityStatus.FAILED, error=EXTRACTION_NO_VALUES_ERROR,
        )

    @pytest.mark.asyncio
    async def test_empty_entities_count_as_no_values(self, client):
        user = _make_user()
        resp, mock_activity, _ = await _post_run(client, user, keys=["award_number"], results=[{}, {}])
        assert resp.status_code == 200
        assert resp.json()["error"] == EXTRACTION_NO_VALUES_ERROR
        assert mock_activity.activity_finish.await_args.args[1] == ActivityStatus.FAILED

    @pytest.mark.asyncio
    async def test_run_with_values_still_completes(self, client):
        user = _make_user()
        resp, mock_activity, _ = await _post_run(
            client, user, keys=["award_number"], results=[{"award_number": "R01-123"}],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == [{"award_number": "R01-123"}]
        assert "error" not in body
        mock_activity.activity_finish.assert_awaited_once_with("activity-1", ActivityStatus.COMPLETED)
