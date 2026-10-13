"""Chat edits a workflow in place instead of creating a second one.

Support ticket: chat built "NSF Subaward Compliance Scan"; asked to "change
the workflow to check for USDA compliance, not NSF", it built "USDA Subaward
Compliance Scan" beside it. update_workflow edits the workflow and records a
version; these tests cover its planning and gating with the database patched
out (tests/integration/test_workflow_versions_mongodb.py covers storage).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tests.test_chat_tools import _make_context

CURRENT = {
    "name": "NSF Subaward Compliance Scan",
    "description": "Evaluates against NSF rules.",
    "input_config": {},
    "output_config": {},
    "steps": [
        {"name": "Extract terms", "is_output": False, "data": {}, "tasks": [
            {"name": "Extraction", "data": {"search_set_uuid": "ss-1", "input_sources": ["workflow_documents"]}},
        ]},
        {"name": "Check NSF rules", "is_output": True, "data": {}, "tasks": [
            {"name": "Prompt", "data": {"prompt": "Check against NSF PAPPG.", "input_sources": ["step_input"]}},
        ]},
    ],
}


class _Conversation:
    pending_confirmations: list = []
    messages: list = []

    async def save(self):
        pass


def _wf():
    return SimpleNamespace(
        id="wf-1", name=CURRENT["name"], user_id="user1", team_id="team1",
        validation_plan=[], validation_plan_definition_hash=None,
    )


def _patches(*, manage=True, taken=False):
    from app.services import workflow_versions

    wf = _wf()
    apply_edit = AsyncMock(return_value=SimpleNamespace(number=3))
    return wf, apply_edit, [
        patch("app.services.access_control.get_authorized_workflow",
              AsyncMock(side_effect=lambda _id, _user, manage_=False, **kw: wf if (manage or not kw.get("manage")) else None)),
        patch.object(workflow_versions, "current_definition", AsyncMock(return_value=CURRENT)),
        patch.object(workflow_versions, "apply_edit", apply_edit),
        patch("app.services.name_conflicts.workflow_name_taken", AsyncMock(return_value=taken)),
    ]


async def _run(ctx, *args, patches, **kwargs):
    from app.services.chat_workflow_tools import update_workflow

    for p in patches:
        p.start()
    try:
        return await update_workflow(ctx, *args, **kwargs)
    finally:
        for p in reversed(patches):
            p.stop()


USDA_STEPS = [
    {"keep": "Extract terms"},
    {"name": "Check USDA rules", "type": "prompt", "prompt": "Check against USDA NIFA terms.", "is_output": True},
]


@pytest.mark.asyncio
async def test_an_edit_previews_then_updates_the_same_workflow():
    ctx = _make_context(conversation=_Conversation(), turn_marker=5)
    wf, apply_edit, patches = _patches()
    preview = await _run(ctx, "wf-1", "Check USDA rules instead of NSF", steps=USDA_STEPS,
                         name="USDA Subaward Compliance Scan", patches=patches)
    assert preview["needs_confirmation"] is True
    assert "Extract terms (unchanged)" in preview["preview"]
    assert "Check USDA rules (prompt, new)" in preview["preview"]
    assert "version history" in preview["preview"]
    apply_edit.assert_not_awaited()

    ctx.deps.turn_marker = 6  # the user approves on the next turn
    wf, apply_edit, patches = _patches()
    done = await _run(ctx, "wf-1", "Check USDA rules instead of NSF", steps=USDA_STEPS,
                      name="USDA Subaward Compliance Scan", confirmed=True, patches=patches)
    assert done["workflow_id"] == "wf-1" and done["version"] == 3
    (edited_wf, definition), kwargs = apply_edit.await_args
    assert edited_wf is wf
    assert kwargs == {"note": "Check USDA rules instead of NSF", "source": "chat", "user_id": "user1"}
    assert definition["name"] == "USDA Subaward Compliance Scan"
    kept, changed = definition["steps"]
    assert kept == CURRENT["steps"][0]  # kept exactly, settings chat can't see included
    assert changed["tasks"][0]["name"] == "Prompt"
    # The kept step already reads the documents, so the new step reads its output.
    assert changed["tasks"][0]["data"]["input_sources"] == ["step_input"]
    assert changed["is_output"] is True


@pytest.mark.asyncio
async def test_an_unknown_kept_step_names_the_real_ones():
    ctx = _make_context()
    _, apply_edit, patches = _patches()
    result = await _run(ctx, "wf-1", "x", steps=[{"keep": "Extract fields"}], patches=patches)
    assert "no step named \"Extract fields\"" in result["error"]
    assert "Extract terms, Check NSF rules" in result["error"]
    apply_edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_viewer_is_told_they_cannot_edit():
    ctx = _make_context()
    _, apply_edit, patches = _patches(manage=False)
    result = await _run(ctx, "wf-1", "x", name="Other", patches=patches)
    assert "not edit it" in result["error"]
    apply_edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_rename_to_a_taken_name_is_refused():
    ctx = _make_context()
    _, apply_edit, patches = _patches(taken=True)
    result = await _run(ctx, "wf-1", "Rename", name="Existing Flow", confirmed=True, patches=patches)
    assert "already named" in result["error"]
    apply_edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_edit_that_changes_nothing_is_refused():
    ctx = _make_context()
    _, apply_edit, patches = _patches()
    result = await _run(ctx, "wf-1", "No-op", steps=[{"keep": "Extract terms"}, {"keep": "Check NSF rules"}],
                        confirmed=True, patches=patches)
    assert "exactly as it is" in result["error"]
    apply_edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_change_summary_is_required():
    ctx = _make_context()
    _, _, patches = _patches()
    result = await _run(ctx, "wf-1", "  ", name="Other", patches=patches)
    assert "change_summary" in result["error"]


def test_chat_is_told_to_edit_rather_than_create():
    from app.services import chat_tools, llm_service
    from app.services.chat_tools import PARALLEL_SAFE_TOOLS, TOOLS

    names = [t.__name__ for t in TOOLS]
    assert "update_workflow" in names and "get_workflow_definition" in names
    assert "update_workflow" not in PARALLEL_SAFE_TOOLS  # a gated write serializes
    assert "update_workflow" in chat_tools.create_workflow.__doc__
    prompt = " ".join(v for v in vars(llm_service).values() if isinstance(v, str))
    assert "Never call create_workflow for an edit" in prompt
    assert chat_tools.approve_button_label("update_workflow") == "Update workflow"
