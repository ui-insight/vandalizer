"""Tests for the empty-workflow guard on validation and export.

A workflow with no steps used to run the whole validation flow: it would
synthesize a seed input, draft a plan from the name alone, grade a run whose
only output was an internal id, and hand back an F with suggestions about
extraction fields that didn't exist — all of it paid for in LLM calls. These
tests pin the refusal at each entry point. Mocked models — no DB.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.services.workflow_service import (
    generate_validation_plan,
    require_workflow_steps,
    validate_workflow,
    workflow_has_executable_steps,
    workflow_has_steps,
)
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")

_STEP = {"id": "s1", "name": "Summarize", "is_output": True, "tasks": []}


def _make_user(user_id="testuser"):
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
    return user


def _auth(user_id="testuser"):
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


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def test_workflow_has_steps():
    assert workflow_has_steps({"steps": [_STEP]}) is True
    assert workflow_has_steps({"steps": []}) is False
    assert workflow_has_steps({}) is False
    assert workflow_has_steps(None) is False


def test_workflow_has_steps_ignores_the_hidden_trigger_step():
    """The empty "Document" step is the run's input placeholder, and the canvas
    hides it — a workflow carrying only that one reads as empty to the user."""
    trigger = {"name": "Document", "is_output": False, "tasks": []}
    assert workflow_has_steps({"steps": [trigger]}) is False
    assert workflow_has_steps({"steps": [trigger, _STEP]}) is True
    # A step the user named "Document" that actually does something counts.
    assert workflow_has_steps({
        "steps": [{"name": "Document", "tasks": [{"name": "Prompt", "data": {}}]}],
    }) is True


def _stub_step_lookup(found):
    """Patch the one query workflow_has_executable_steps makes."""
    step_cls = MagicMock()
    step_cls.find.return_value.to_list = AsyncMock(return_value=found)
    return patch("app.services.workflow_service.WorkflowStep", step_cls)


@pytest.mark.asyncio
async def test_workflow_has_executable_steps_resolves_step_ids():
    wf = MagicMock()
    wf.steps = ["s1", "s2"]
    trigger = MagicMock(); trigger.name = "Document"; trigger.tasks = []
    real = MagicMock(); real.name = "Summarize"; real.tasks = ["t1"]

    with _stub_step_lookup([trigger, real]):
        assert await workflow_has_executable_steps(wf) is True

    with _stub_step_lookup([trigger]):
        assert await workflow_has_executable_steps(wf) is False


@pytest.mark.asyncio
async def test_workflow_has_executable_steps_skips_the_query_when_empty():
    """The run path pays for this check on every run — no steps, no query."""
    wf = MagicMock()
    wf.steps = []
    step_cls = MagicMock()

    with patch("app.services.workflow_service.WorkflowStep", step_cls):
        assert await workflow_has_executable_steps(wf) is False

    step_cls.find.assert_not_called()


@pytest.mark.asyncio
async def test_workflow_has_executable_steps_handles_dangling_ids():
    """Step ids whose documents are gone resolve to nothing, so they don't count."""
    wf = MagicMock()
    wf.steps = ["missing"]
    with _stub_step_lookup([]):
        assert await workflow_has_executable_steps(wf) is False


def test_require_workflow_steps_names_the_action():
    require_workflow_steps({"steps": [_STEP]}, "validating it")  # does not raise
    with pytest.raises(ValueError, match="no steps yet — add at least one step before validating it"):
        require_workflow_steps({"steps": []}, "validating it")


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_plan_rejects_workflow_with_no_steps():
    user = _make_user()
    agent = MagicMock()

    with (
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.workflow_service.get_workflow",
              new=AsyncMock(return_value={"id": "wf", "name": "X", "steps": []})),
        patch("app.services.llm_service.create_chat_agent", new=AsyncMock(return_value=agent)),
    ):
        with pytest.raises(ValueError, match="no steps yet"):
            await generate_validation_plan("wf", user)

    agent.run.assert_not_called()


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_rejects_workflow_with_no_steps_even_with_a_plan():
    """A plan can outlive the steps it was drafted from (import, step deletion),
    so the step check has to come before the plan check."""
    user = _make_user()
    wf = MagicMock()
    wf.validation_plan = [{"id": "c1", "description": "Output names the award"}]

    with (
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=wf)),
        patch("app.services.workflow_service.get_workflow",
              new=AsyncMock(return_value={"id": "wf", "name": "X", "steps": []})),
    ):
        with pytest.raises(ValueError, match="no steps yet"):
            await validate_workflow("wf", user=user)


@pytest.mark.asyncio
async def test_validate_still_reports_a_missing_plan_when_steps_exist():
    user = _make_user()
    wf = MagicMock()
    wf.validation_plan = []

    with (
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=wf)),
        patch("app.services.workflow_service.get_workflow",
              new=AsyncMock(return_value={"id": "wf", "name": "X", "steps": [_STEP]})),
    ):
        with pytest.raises(ValueError, match="No validation plan"):
            await validate_workflow("wf", user=user)


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def _step(name="Summarize", tasks=("t1",)):
    step = MagicMock()
    step.name = name  # can't go through the MagicMock ctor — `name` is reserved
    step.tasks = list(tasks)
    return step


def _run_workflow_patches(stored_steps):
    """Patch everything run_workflow touches, resolving its steps to *stored_steps*."""
    wf = MagicMock()
    wf.id = "wf-oid"
    wf.steps = [f"step-{i}" for i in range(len(stored_steps))]
    doc = MagicMock()
    doc.uuid = "doc-uuid"

    return wf, (
        patch("app.services.workflow_service.get_authorized_workflow",
              new=AsyncMock(return_value=wf)),
        patch("app.services.workflow_service.get_team_access_context",
              new=AsyncMock(return_value=MagicMock())),
        patch("app.services.workflow_service.get_authorized_document",
              new=AsyncMock(return_value=doc)),
        _stub_step_lookup(stored_steps),
        patch("app.services.workflow_service.get_user_model_name",
              new=AsyncMock(return_value="test-model")),
    )


@pytest.mark.asyncio
async def test_run_rejects_workflow_with_no_steps():
    """The run used to complete in ~120ms and hand back the input document's
    uuid as its output, marked Completed in History."""
    from app.services.workflow_service import run_workflow

    user = _make_user()
    _, patches = _run_workflow_patches([])
    send_task = MagicMock()
    result_cls = MagicMock()

    with patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("app.services.workflow_service.celery_app.send_task", send_task), \
         patch("app.services.workflow_service.WorkflowResult", result_cls):
        with pytest.raises(ValueError, match="no steps yet"):
            await run_workflow("wf", ["doc-uuid"], "u", user=user)

    send_task.assert_not_called()
    result_cls.assert_not_called()  # no WorkflowResult, so nothing lands in History


@pytest.mark.asyncio
async def test_run_rejects_workflow_whose_only_step_is_the_trigger():
    from app.services.workflow_service import run_workflow

    user = _make_user()
    _, patches = _run_workflow_patches([_step(name="Document", tasks=())])
    send_task = MagicMock()

    with patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("app.services.workflow_service.celery_app.send_task", send_task), \
         patch("app.services.workflow_service.WorkflowResult", MagicMock()):
        with pytest.raises(ValueError, match="no steps yet"):
            await run_workflow("wf", ["doc-uuid"], "u", user=user)

    send_task.assert_not_called()


@pytest.mark.asyncio
async def test_run_dispatches_when_a_real_step_exists():
    from app.services.workflow_service import run_workflow

    user = _make_user()
    _, patches = _run_workflow_patches([_step(name="Document", tasks=()), _step()])
    send_task = MagicMock()
    result = MagicMock()
    result.id = "result-oid"
    result.insert = AsyncMock()

    with patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("app.services.workflow_service.celery_app.send_task", send_task), \
         patch("app.services.workflow_service.WorkflowResult", MagicMock(return_value=result)):
        session_id = await run_workflow("wf", ["doc-uuid"], "u", user=user)

    assert session_id
    send_task.assert_called_once()


@pytest.mark.asyncio
async def test_batch_run_rejects_workflow_with_no_steps():
    from app.services.workflow_service import run_workflow_batch

    user = _make_user()
    _, patches = _run_workflow_patches([])
    send_task = MagicMock()

    with patches[0], patches[1], patches[2], patches[3], patches[4], \
         patch("app.services.workflow_service.celery_app.send_task", send_task), \
         patch("app.services.workflow_service.WorkflowResult", MagicMock()):
        with pytest.raises(ValueError, match="no steps yet"):
            await run_workflow_batch("wf", ["doc-uuid"], "u", user=user)

    send_task.assert_not_called()


class TestRunRoute:
    @pytest.mark.asyncio
    async def test_run_route_returns_400_without_starting_an_activity(self, client):
        """A blocked click must not leave a failed activity behind in History."""
        user = _make_user()
        cookies, headers = _auth()
        wf = MagicMock()
        wf.name = "Empty WF"
        wf.steps = []
        activity_start = AsyncMock()

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.get_authorized_workflow", AsyncMock(return_value=wf)), \
             patch("app.routers.workflows.svc.workflow_has_executable_steps",
                   AsyncMock(return_value=False)), \
             patch("app.services.activity_service.activity_start", activity_start):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.post(
                "/api/workflows/wf-id/run",
                json={"document_uuids": ["doc-uuid"]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert "no steps yet" in resp.json()["detail"]
        activity_start.assert_not_awaited()


# ---------------------------------------------------------------------------
# Export route
# ---------------------------------------------------------------------------


class TestExportGuard:
    @pytest.mark.asyncio
    async def test_export_rejects_workflow_with_no_steps(self, client):
        user = _make_user()
        cookies, headers = _auth()
        wf = MagicMock()
        wf.steps = []

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.get_authorized_workflow", AsyncMock(return_value=wf)), \
             patch("app.routers.workflows.svc.workflow_has_executable_steps",
                   AsyncMock(return_value=False)):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get("/api/workflows/wf-id/export", cookies=cookies, headers=headers)

        assert resp.status_code == 400
        assert "no steps yet" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_succeeds_when_steps_exist(self, client):
        user = _make_user()
        cookies, headers = _auth()
        wf = MagicMock()
        wf.steps = ["step-id"]

        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.workflows.get_authorized_workflow", AsyncMock(return_value=wf)), \
             patch("app.routers.workflows.svc.workflow_has_executable_steps",
                   AsyncMock(return_value=True)), \
             patch("app.services.export_import_service.export_workflow",
                   AsyncMock(return_value={"items": [{"name": "My WF", "steps": [{"name": "Summarize"}]}]})):
            MockUser.find_one = AsyncMock(return_value=user)

            resp = await client.get("/api/workflows/wf-id/export", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        assert "My WF.vandalizer.json" in resp.headers["content-disposition"]
