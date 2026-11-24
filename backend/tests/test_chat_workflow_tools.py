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


FLAG = {"name": "Flag F&A rate above 50%", "type": "prompt", "prompt": "Flag if the F&A rate is above 50%."}


@pytest.mark.asyncio
async def test_a_step_inserted_mid_chain_keeps_the_next_step_reading_its_old_input():
    """Support ticket: the summary kept "unchanged" saw only the new flag step's line."""
    import copy

    before = copy.deepcopy(CURRENT)
    ctx = _make_context(conversation=_Conversation(), turn_marker=5)
    steps = [{"keep": "Extract terms"}, FLAG, {"keep": "Check NSF rules"}]
    _, apply_edit, patches = _patches()
    preview = await _run(ctx, "wf-1", "Flag a high F&A rate", steps=steps, patches=patches)
    assert "3. Check NSF rules (unchanged)" not in preview["preview"]
    assert ('3. Check NSF rules (input rewired: now reads all earlier steps, so it still gets '
            '"Extract terms" and not only "Flag F&A rate above 50%")') in preview["preview"]

    ctx.deps.turn_marker = 6
    _, apply_edit, patches = _patches()
    await _run(ctx, "wf-1", "Flag a high F&A rate", steps=steps, confirmed=True, patches=patches)
    extract, flag, summary = apply_edit.await_args.args[1]["steps"]
    assert extract == CURRENT["steps"][0]
    assert flag["tasks"][0]["data"]["input_sources"] == ["step_input"]  # the flag reads the extraction
    assert summary["tasks"][0]["data"]["input_sources"] == ["earlier_steps"]
    assert summary["tasks"][0]["data"]["prompt"] == "Check against NSF PAPPG."
    assert summary["is_output"] is True
    assert CURRENT == before  # the stored definition isn't mutated


@pytest.mark.asyncio
async def test_a_check_added_at_the_end_leaves_kept_steps_unchanged():
    ctx = _make_context(conversation=_Conversation(), turn_marker=5)
    _, _, patches = _patches()
    preview = await _run(ctx, "wf-1", "Flag a high F&A rate",
                         steps=[{"keep": "Extract terms"}, {"keep": "Check NSF rules"}, FLAG], patches=patches)
    assert "1. Extract terms (unchanged)" in preview["preview"]
    assert "2. Check NSF rules (unchanged)" in preview["preview"]


def test_a_first_step_moved_later_still_reads_the_documents():
    from app.services.chat_workflow_tools import _rewire_moved_steps

    legacy_first = {"name": "Summarize", "is_output": True, "data": {}, "tasks": [
        {"name": "Prompt", "data": {"prompt": "Summarize."}},  # no input_sources: the trigger's documents
    ]}
    intro = {"name": "Intro", "is_output": False, "data": {}, "tasks": [{"name": "Prompt", "data": {"input_sources": ["workflow_documents"]}}]}
    approval = {"name": "Sign off", "is_output": False, "data": {}, "tasks": [{"name": "Approval", "data": {}}]}
    built = [intro, legacy_first, approval]
    notes = _rewire_moved_steps([legacy_first, approval], built, {1, 2})
    assert built[1]["tasks"][0]["data"]["input_sources"] == ["workflow_documents"]
    assert "still reads the workflow documents" in notes[1]
    assert 2 not in notes and built[2] is approval  # approvals don't read input_sources
    assert "input_sources" not in legacy_first["tasks"][0]["data"]


def test_removing_the_step_a_kept_step_read_is_named():
    from app.services.chat_workflow_tools import _rewire_moved_steps

    extract, summary = CURRENT["steps"]
    flag = {"name": "Flag", "is_output": False, "data": {}, "tasks": [{"name": "Prompt", "data": {"input_sources": ["step_input"]}}]}
    built = [extract, summary]
    notes = _rewire_moved_steps([extract, flag, summary], built, {0, 1})
    assert built[1]["tasks"][0]["data"]["input_sources"] == ["earlier_steps"]
    assert notes == {1: 'input rewired: "Flag", the step it read, is removed; it now reads all earlier steps'}


def test_a_step_that_becomes_first_reads_the_documents_and_says_so():
    from app.services.chat_workflow_tools import _rewire_moved_steps

    _, summary = CURRENT["steps"]
    built = [summary]
    notes = _rewire_moved_steps(CURRENT["steps"], built, {0})
    assert built[0] is summary  # step_input on a first step already means the documents
    assert notes == {0: 'input changed: now first, it reads the workflow documents instead of "Extract terms"'}
