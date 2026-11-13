"""Running a workflow on folders ticked in Files (support ticket: Files said
"2 selected", the workflow "0 selected", and Run stayed disabled). The run
route expands ticked folders into their documents; ticked folders with no
documents in them are refused with a reason instead of starting an empty run."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_workflow_empty_guard import _auth, _make_user, client  # noqa: F401


def _patches(user, folder_docs, activity_start, run, run_batch):
    wf = MagicMock()
    wf.name = "Award review"
    wf.steps = [MagicMock(), MagicMock()]
    return [
        patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
        patch("app.routers.workflows.get_authorized_workflow", AsyncMock(return_value=wf)),
        patch("app.routers.workflows.svc.workflow_has_executable_steps", AsyncMock(return_value=True)),
        patch("app.routers.workflows._authorize_documents", AsyncMock(side_effect=lambda uuids, user: list(uuids or []))),
        patch("app.services.folder_service.expand_folders_to_document_uuids", AsyncMock(return_value=folder_docs)),
        patch("app.services.activity_service.activity_start", activity_start),
        patch("app.routers.workflows.svc.run_workflow", run),
        patch("app.routers.workflows.svc.run_workflow_batch", run_batch),
    ]


async def _post(client, body, folder_docs):  # noqa: F811
    user = _make_user()
    cookies, headers = _auth()
    activity = MagicMock(id="act-1", save=AsyncMock())
    activity_start = AsyncMock(return_value=activity)
    run = AsyncMock(return_value="sess-1")
    run_batch = AsyncMock(return_value="batch-1")
    ps = _patches(user, folder_docs, activity_start, run, run_batch)
    with patch("app.dependencies.User") as MockUser:
        MockUser.find_one = AsyncMock(return_value=user)
        for p in ps:
            p.start()
        try:
            resp = await client.post("/api/workflows/64b000000000000000000001/run", json=body, cookies=cookies, headers=headers)
        finally:
            for p in reversed(ps):
                p.stop()
    return resp, activity_start, run, run_batch


@pytest.mark.asyncio
async def test_ticked_folders_run_on_their_documents(client):  # noqa: F811
    resp, activity_start, run, _ = await _post(
        client, {"document_uuids": ["D1"], "folder_uuids": ["F1", "F2"]}, ["D2", "D1", "D3"],
    )
    assert resp.status_code == 200
    assert run.await_args.args[1] == ["D1", "D2", "D3"]


@pytest.mark.asyncio
async def test_ticked_folders_can_run_per_document(client):  # noqa: F811
    resp, _, run, run_batch = await _post(
        client, {"folder_uuids": ["F1"], "batch_mode": True}, ["D1", "D2"],
    )
    assert resp.status_code == 200
    assert run_batch.await_args.args[1] == ["D1", "D2"]
    run.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("folders,detail", [
    (["F1"], "The selected folder has no documents in it."),
    (["F1", "F2"], "The selected folders have no documents in them."),
])
async def test_empty_folders_are_refused_before_any_activity(client, folders, detail):  # noqa: F811
    resp, activity_start, run, _ = await _post(client, {"folder_uuids": folders}, [])
    assert resp.status_code == 400
    assert resp.json()["detail"] == detail
    activity_start.assert_not_awaited()
    run.assert_not_awaited()
