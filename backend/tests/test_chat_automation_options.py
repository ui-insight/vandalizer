"""Chat automation settings survive approval and reach the folder-watch runner."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat_tools import create_automation


@pytest.fixture
def setup(monkeypatch):
    conversation = SimpleNamespace(pending_confirmations=[], save=AsyncMock())
    context = SimpleNamespace(deps=SimpleNamespace(
        user=SimpleNamespace(user_id="user", current_team=None), user_id="user",
        team_access=None, conversation=conversation, turn_marker=1,
    ))
    folders = AsyncMock(side_effect=lambda uuid, *args, **kwargs:
                        SimpleNamespace(uuid=uuid, title={"lab": "Certification Lab", "results": "Results"}.get(uuid, uuid)))
    monkeypatch.setattr("app.services.access_control.get_authorized_folder", folders)
    monkeypatch.setattr("app.services.access_control.get_authorized_search_set", AsyncMock(
        return_value=SimpleNamespace(title="NIH R01 Extraction")))
    monkeypatch.setattr("app.services.access_control.get_authorized_workflow", AsyncMock(
        return_value=SimpleNamespace(name="Review")))
    create = AsyncMock(return_value=SimpleNamespace(id="auto-1", name="NIH PDFs", enabled=False))
    monkeypatch.setattr("app.services.automation_service.create_automation", create)
    return context, create, folders


async def call(context, **options):
    return await create_automation(context, "NIH PDFs", "extraction", "nih-r01", folder_uuid="lab", **options)


@pytest.mark.asyncio
async def test_pdf_only_preview_approval_and_actual_folder_watch_filter(setup):
    context, create, _ = setup
    preview = await call(context, file_types=[".PDF", "pdf"], exclude_patterns="draft*, temp_*")
    assert preview["needs_confirmation"] is True
    assert preview["trigger_config"]["file_types"] == ["pdf"]
    assert {"label": "File types", "value": ".pdf"} in preview["automation_settings"]
    create.assert_not_awaited()
    # An LLM cannot approve itself in the same user turn.
    assert (await call(context, file_types=["pdf"], exclude_patterns="draft*, temp_*", confirmed=True))["needs_confirmation"]
    create.assert_not_awaited()
    context.deps.turn_marker = 2
    result = await call(context, file_types=["pdf"], exclude_patterns="draft*, temp_*", confirmed=True)
    assert result["id"] == "auto-1"
    assert "Paused" in result["message"]
    config = create.call_args.kwargs["trigger_config"]
    assert config == preview["trigger_config"]

    from app.tasks.document_tasks import _check_folder_watch_automations
    db = MagicMock()
    db.automation.find.return_value = [{"_id": "auto-1", "name": "NIH PDFs", "action_type": "extraction", "action_id": "nih-r01", "trigger_config": config}]
    with patch("app.tasks.document_tasks._run_automation_extraction") as run:
        for extension, title in [("docx", "proposal.docx"), ("pdf", "draft_proposal.pdf"), ("pdf", "proposal.pdf")]:
            db.smart_document.find_one.return_value = {"uuid": title, "folder": "lab", "extension": extension, "title": title}
            _check_folder_watch_automations(db, title)
        run.assert_called_once()
        assert run.call_args.args[-1]["title"] == "proposal.pdf"


@pytest.mark.asyncio
async def test_editor_options_are_visible_and_persisted(setup):
    context, create, folders = setup
    options = dict(file_types=["pdf"], exclude_patterns="draft*", batch_mode=True,
                   output_folder_uuid="results", output_format="json", output_file_naming="{document_name}_{date}",
                   email_recipients=["reviewer@example.org"], notify_owner=True, email_condition="failure")
    preview = await call(context, **options)
    settings = {row["label"]: row["value"] for row in preview["automation_settings"]}
    assert settings["Batch mode"].startswith("On")
    assert "files currently run individually" in settings["Batch mode"]
    assert settings["Save results to"] == "Results"
    assert settings["Result format"] == "json"
    assert settings["File naming pattern"] == "{document_name}_{date}"
    assert settings["Email notification"] == "Automation owner, reviewer@example.org"
    assert settings["Send email"] == "On failure only"
    assert settings["Status"] == "Paused"
    folders.assert_any_await("results", context.deps.user, contribute=True, team_access=None)
    context.deps.turn_marker = 2
    await call(context, confirmed=True, **options)
    create.assert_awaited_once()
    assert create.call_args.kwargs["trigger_config"]["batch_mode"] is True
    assert create.call_args.kwargs["output_config"] == {
        "storage": {"enabled": True, "destination_folder": "results", "format": "json", "file_naming": "{document_name}_{date}"},
        "notifications": [{"channel": "email", "recipients": ["reviewer@example.org"], "notify_owner": True, "conditions": "failure"}],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"file_types": ["docx"]}, {"exclude_patterns": "draft*"}, {"batch_mode": True},
    {"output_folder_uuid": "lab"}, {"output_format": "pdf"}, {"output_file_naming": "changed"},
    {"email_recipients": ["other@example.org"]}, {"notify_owner": False}, {"email_condition": "failure"},
    {"description": "Changed description"},
])
async def test_changed_options_require_new_approval(setup, change):
    context, create, _ = setup
    options = dict(file_types=["pdf"], output_folder_uuid="results", notify_owner=True,
                   email_recipients=["reviewer@example.org"])
    await call(context, **options)
    context.deps.turn_marker = 2
    changed = await call(context, confirmed=True, **(options | change))
    assert changed["needs_confirmation"] is True
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("options", [
    {"file_types": ["html"]}, {"file_types": [""]}, {"email_recipients": ["not-an-email"]},
    {"email_condition": "sometimes"}, {"email_condition": "failure"},
    {"output_format": "pdf"}, {"output_folder_uuid": "results", "output_format": "docx"},
    {"trigger_type": "schedule", "cron_expression": "0 9 * * 1", "file_types": ["pdf"]},
])
async def test_invalid_or_inapplicable_options_are_not_silently_dropped(setup, options):
    context, create, _ = setup
    result = await call(context, **options)
    assert "error" in result
    create.assert_not_awaited()
    assert context.deps.conversation.pending_confirmations == []


@pytest.mark.asyncio
async def test_destination_permissions_rechecked_on_confirmation(setup):
    context, create, folders = setup
    await call(context, output_folder_uuid="results")
    context.deps.turn_marker = 2
    folders.side_effect = lambda uuid, *args, **kwargs: None if uuid == "results" else SimpleNamespace(uuid="lab", title="Certification Lab")
    result = await call(context, output_folder_uuid="results", confirmed=True)
    assert "permission" in result["error"]
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_omitted_filters_mean_all_types_and_outputs_remain_off(setup):
    context, _, _ = setup
    preview = await call(context)
    assert preview["trigger_config"]["file_types"] == []
    assert preview["output_config"] == {}
    assert {"label": "File types", "value": "All supported file types"} in preview["automation_settings"]


def test_tool_schema_exposes_editor_options():
    from pydantic_ai.tools import Tool
    properties = Tool(create_automation).function_schema.json_schema["properties"]
    assert {"file_types", "exclude_patterns", "batch_mode", "output_folder_uuid", "output_format",
            "output_file_naming", "email_recipients", "notify_owner", "email_condition"} <= properties.keys()
