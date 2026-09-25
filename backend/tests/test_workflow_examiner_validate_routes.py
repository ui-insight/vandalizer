"""Route tests for the examiner-validates-a-submission path.

A verification reviewer opens a submitted workflow, runs it, and then grades it
on the Validate tab. Those routes used to require manage rights, so the
reviewer got "Workflow not found" on a workflow they had just run. They now
take the ``validate`` access level; applying an optimizer's winner still needs
manage rights. Mocked authz — no DB.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(user_id="examiner"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Examiner"
    user.is_admin = False
    user.is_examiner = True
    user.current_team = None
    user.is_demo_user = False
    user.token_version = 0
    user.demo_status = None
    return user


def _auth(user_id="examiner"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


def _validate_only_authz(wf):
    """View and validate pass; manage does not — the reviewer's situation."""
    async def _authz(workflow_id, user, **kwargs):
        return None if kwargs.get("manage") else wf
    return AsyncMock(side_effect=_authz)


class TestGeneratePlanRoute:
    @pytest.mark.asyncio
    async def test_view_only_user_gets_403_not_404(self, client):
        user = _make_user("member")
        user.is_examiner = False
        cookies, headers = _auth("member")

        async def _authz(workflow_id, user, **kwargs):
            return None if kwargs.get("validate") else MagicMock()

        with patch("app.dependencies.decode_token", return_value={"sub": "member", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.services.workflow_service.get_authorized_workflow", AsyncMock(side_effect=_authz)):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/workflows/wf-id/validation-plan/generate",
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 403
        assert "Workflow not found" not in resp.json()["detail"]
        assert "examiner reviewing" in resp.json()["detail"]


class TestOptimizeRoute:
    @pytest.mark.asyncio
    async def test_reviewer_cannot_auto_apply(self, client):
        """Scoring a submission is fine; rewriting its config is not."""
        user = _make_user()
        cookies, headers = _auth()
        wf = MagicMock()
        wf.validation_plan = [{"id": "c1"}]

        with patch("app.dependencies.decode_token", return_value={"sub": "examiner", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.get_authorized_workflow", _validate_only_authz(wf)), \
             patch("app.services.workflow_optimizer._resolve_test_inputs", AsyncMock(return_value=[{}])) as inputs:
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/workflows/wf-id/optimize",
                json={"apply_on_finish": True},
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 403
        assert "owner or a team admin" in resp.json()["detail"]
        # Refused before any precondition work.
        inputs.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reviewer_start_uses_validate_level(self, client):
        """The start route asks for ``validate`` access, so a reviewer with an
        open verification request gets past authz (and on to the precondition
        checks, which fail here on purpose so no run is queued)."""
        user = _make_user()
        cookies, headers = _auth()
        wf = MagicMock()
        wf.validation_plan = []  # trips the "no plan" precondition
        authz = _validate_only_authz(wf)

        with patch("app.dependencies.decode_token", return_value={"sub": "examiner", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.get_authorized_workflow", authz):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/workflows/wf-id/optimize",
                json={},
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 400
        assert "no validation plan" in resp.json()["detail"].lower()
        assert authz.await_args_list[0].kwargs.get("validate") is True

    @pytest.mark.asyncio
    async def test_apply_still_requires_manage(self, client):
        user = _make_user()
        cookies, headers = _auth()
        wf = MagicMock()

        with patch("app.dependencies.decode_token", return_value={"sub": "examiner", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.get_authorized_workflow", _validate_only_authz(wf)):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/workflows/wf-id/optimize/run-1/apply",
                json={},
                cookies=cookies, headers=headers,
            )

        assert resp.status_code == 404


class TestCancelOptimizationRoute:
    """A reviewer can stop the run they started, not the owner's."""

    async def _cancel(self, client, run_owner):
        user = _make_user()
        cookies, headers = _auth()
        run = MagicMock(user_id=run_owner, status="running", cancel_requested=False, save=AsyncMock())
        with patch("app.dependencies.decode_token", return_value={"sub": "examiner", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.get_authorized_workflow", _validate_only_authz(MagicMock())), \
             patch("app.models.workflow_optimization_run.WorkflowOptimizationRun", **{"find_one": AsyncMock(return_value=run)}):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post("/api/workflows/wf-id/optimize/run-1/cancel", cookies=cookies, headers=headers)
        return resp, run

    @pytest.mark.asyncio
    async def test_reviewer_cannot_cancel_the_owners_run(self, client):
        resp, run = await self._cancel(client, run_owner="owner")
        assert resp.status_code == 403
        assert run.cancel_requested is False

    @pytest.mark.asyncio
    async def test_reviewer_can_cancel_their_own_run(self, client):
        resp, run = await self._cancel(client, run_owner="examiner")
        assert resp.status_code == 200
        assert run.cancel_requested is True
