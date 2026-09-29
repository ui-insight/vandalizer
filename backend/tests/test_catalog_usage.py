import json
from types import SimpleNamespace as Row
from unittest.mock import AsyncMock, patch

import pytest

from app.models.library import LibraryItemKind
from app.services.catalog_usage import describe_catalog_usage


def test_workflow_summary_distinguishes_text_no_input_and_fixed_documents_without_exposing_them():
    step = Row(name="Findings", tasks=["task"], is_output=False)
    workflow = Row(input_config={"trigger_type": "text_input", "fixed_documents": [{"uuid": "private-id", "title": "Private file title"}]})
    usage = describe_catalog_usage("workflow", workflow, [step])
    assert usage["input"].startswith("Paste or type")
    assert usage["output_names"] == ["Findings"]
    assert "access is checked" in usage["notes"][0]
    assert "private-id" not in json.dumps(usage) and "Private file" not in json.dumps(usage)
    workflow.input_config = {"trigger_type": "no_input"}
    assert "No manual run input" in describe_catalog_usage("workflow", workflow, [step])["input"]
    workflow.input_config = {}
    assert "active project's files" in describe_catalog_usage("workflow", workflow, [step])["input"]


def test_empty_workflow_and_unindexed_kb_do_not_advertise_usable_output():
    placeholder = Row(name="Document", tasks=[], is_output=False)
    assert "No executable" in describe_catalog_usage("workflow", Row(input_config={}), [placeholder])["output"]
    usage = describe_catalog_usage("knowledge_base", Row(total_chunks=0))
    assert usage["notes"] == ["No indexed content is available for chat yet."]


def test_prompt_is_not_described_as_an_extraction():
    assert "saved prompt" in describe_catalog_usage("search_set", Row(set_type="prompt"))["output"]
    assert "extraction fields" in describe_catalog_usage("search_set", Row(set_type="extraction"))["output"]


@pytest.mark.asyncio
async def test_public_catalog_includes_definition_summaries_and_real_prompt_type():
    from app.services.verification_service import list_verified_items

    items = [Row(id="row-" + key, item_id=key, kind=kind, tags=[], verified=True, created_at=None)
             for key, kind in [("wf", LibraryItemKind.WORKFLOW), ("prompt", LibraryItemKind.SEARCH_SET), ("kb", LibraryItemKind.KNOWLEDGE_BASE)]]
    wf = Row(id="wf", name="Budget review", description="Find missing budget explanations.", resource_config={}, user_id="owner", created_by_user_id=None, input_config={"trigger_type": "text_input"}, steps=["step"])
    prompt = Row(id="prompt", uuid="prompt-uuid", title="Rewrite instructions", extraction_config={}, user_id="owner", verified=True, set_type="prompt")
    kb = Row(id="kb", uuid="kb-uuid", title="Policies", description="Award policy reference.", resource_config={}, user_id="owner", verified=True, total_sources=2, sources_ready=2, total_chunks=40, status="ready")
    with (
        patch("app.services.verification_service.LibraryItem") as library,
        patch("app.services.verification_service.Workflow") as workflows,
        patch("app.services.verification_service.WorkflowStep") as steps,
        patch("app.services.verification_service.SearchSet") as search_sets,
        patch("app.services.verification_service.KnowledgeBase") as kbs,
        patch("app.services.verification_service.KnowledgeBaseReference") as refs,
        patch("app.services.verification_service.VerifiedItemMetadata") as metadata,
        patch("app.services.verification_service.VerificationRequest") as requests,
        patch("app.services.verification_service.resolve_authors", AsyncMock(return_value={})),
    ):
        library.find.return_value.sort.return_value.to_list = AsyncMock(return_value=items)
        library.find.return_value.to_list = AsyncMock(return_value=[])
        workflows.find.return_value.to_list = AsyncMock(return_value=[wf])
        steps.find.return_value.to_list = AsyncMock(return_value=[Row(id="step", name="Review findings", tasks=["task"], is_output=False)])
        search_sets.find.return_value.to_list = AsyncMock(return_value=[prompt])
        kbs.find.return_value.to_list = AsyncMock(return_value=[kb])
        refs.find.return_value.to_list = AsyncMock(return_value=[])
        metadata.find_all.return_value.to_list = AsyncMock(return_value=[])
        requests.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
        result = await list_verified_items()
        filtered = await list_verified_items(search="missing budget")
        assert [item["item_id"] for item in filtered["items"]] == ["wf"]
        steps.find.return_value.to_list = AsyncMock(return_value=[])
        missing_step = await list_verified_items(search="missing budget")
        assert "incomplete" in missing_step["items"][0]["usage"]["output"]
    by_id = {item["item_id"]: item for item in result["items"]}
    assert by_id["wf"]["description"] == wf.description
    assert by_id["wf"]["usage"]["output_names"] == ["Review findings"]
    assert by_id["prompt"]["set_type"] == "prompt"
    assert "saved prompt" in by_id["prompt"]["usage"]["output"]
    assert by_id["kb"]["usage"]["input"] == "Ask a question about the indexed sources."
