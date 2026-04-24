"""Tests for pure helpers in app.services.export_import_service.

The async import/export paths are covered by router-level integration tests.
Here we exercise the envelope builder, the envelope validator, and the
task-reference resolver — the functions that don't need a live database.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.export_import_service import (
    SCHEMA_VERSION,
    _envelope,
    _resolve_task_references,
    validate_export_data,
)


class TestEnvelope:
    def test_envelope_has_expected_top_level_shape(self):
        env = _envelope("workflow", "alice@example.edu", [{"a": 1}])
        assert env["vandalizer_export"] is True
        assert env["schema_version"] == SCHEMA_VERSION
        assert env["export_type"] == "workflow"
        assert env["exported_by"] == "alice@example.edu"
        assert env["items"] == [{"a": 1}]
        # exported_at should be an ISO-8601 UTC timestamp string
        assert "T" in env["exported_at"]
        assert env["exported_at"].endswith("+00:00")

    def test_envelope_empty_items_list_still_valid_shape(self):
        env = _envelope("catalog", "sys@example.edu", [])
        assert env["items"] == []
        assert env["export_type"] == "catalog"


class TestValidateExportData:
    def test_non_dict_rejected(self):
        assert validate_export_data([]) == "Invalid JSON: expected an object"
        assert validate_export_data("hello") == "Invalid JSON: expected an object"

    def test_missing_flag_rejected(self):
        err = validate_export_data({"items": [{}]})
        assert err is not None
        assert "vandalizer_export" in err

    def test_unsupported_schema_version_rejected(self):
        err = validate_export_data({
            "vandalizer_export": True,
            "schema_version": 99,
            "export_type": "workflow",
            "items": [{}],
        })
        assert err is not None
        assert "schema version" in err

    def test_supports_v1_and_current_version(self):
        for ver in (1, SCHEMA_VERSION):
            env = {
                "vandalizer_export": True,
                "schema_version": ver,
                "export_type": "workflow",
                "items": [{}],
            }
            assert validate_export_data(env) is None

    def test_unknown_export_type_rejected(self):
        err = validate_export_data({
            "vandalizer_export": True,
            "schema_version": SCHEMA_VERSION,
            "export_type": "nonsense",
            "items": [{}],
        })
        assert err == "Unknown export_type"

    def test_all_recognized_export_types_accepted(self):
        for etype in ("workflow", "search_set", "knowledge_base", "catalog"):
            env = {
                "vandalizer_export": True,
                "schema_version": SCHEMA_VERSION,
                "export_type": etype,
                "items": [{}],
            }
            assert validate_export_data(env) is None, f"{etype} should be valid"

    def test_empty_items_list_rejected(self):
        err = validate_export_data({
            "vandalizer_export": True,
            "schema_version": SCHEMA_VERSION,
            "export_type": "workflow",
            "items": [],
        })
        assert err == "Export file contains no items"

    def test_items_not_a_list_rejected(self):
        err = validate_export_data({
            "vandalizer_export": True,
            "schema_version": SCHEMA_VERSION,
            "export_type": "workflow",
            "items": {"wrong": "shape"},
        })
        assert err == "Export file contains no items"


class TestResolveTaskReferences:
    """The resolver embeds SearchSet / KB / document data into task payloads.

    Beanie calls are patched; we care about the task data transformation only.
    """

    @pytest.mark.asyncio
    async def test_non_extraction_task_passed_through_unchanged(self):
        task_data = {"prompt": "Summarize the document"}
        result = await _resolve_task_references(task_data, "LLMCall")
        assert result == task_data
        # Ensure the helper returned a copy, not the same dict
        assert result is not task_data

    @pytest.mark.asyncio
    async def test_extraction_without_search_set_uuid_is_a_noop(self):
        result = await _resolve_task_references({"other": "data"}, "Extraction")
        assert "_embedded_search_set" not in result

    @pytest.mark.asyncio
    async def test_extraction_task_embeds_search_set_definition(self):
        ss = MagicMock()
        ss.title = "Grant Fields"
        ss.extraction_config = {"mode": "two_pass"}
        ss.domain = "research_admin"
        ss.cross_field_rules = []
        ss.item_order = ["id_a", "id_b"]

        item_a = MagicMock(searchphrase="pi_name", searchtype="extraction",
            title="PI Name", is_optional=False, enum_values=[])
        item_a.id = "id_a"
        item_b = MagicMock(searchphrase="amount", searchtype="extraction",
            title="Amount", is_optional=True, enum_values=[])
        item_b.id = "id_b"

        items_query = MagicMock()
        items_query.to_list = AsyncMock(return_value=[item_b, item_a])  # out of order

        with patch("app.services.export_import_service.SearchSet") as MockSS, \
             patch("app.services.export_import_service.SearchSetItem") as MockSSI:
            MockSS.find_one = AsyncMock(return_value=ss)
            MockSSI.find = MagicMock(return_value=items_query)

            result = await _resolve_task_references(
                {"search_set_uuid": "ss-1"}, "Extraction",
            )

        embedded = result["_embedded_search_set"]
        assert embedded["title"] == "Grant Fields"
        assert embedded["extraction_config"] == {"mode": "two_pass"}
        # item_order is respected — id_a comes before id_b regardless of
        # the DB's returned order.
        searchphrases = [it["searchphrase"] for it in embedded["items"]]
        assert searchphrases == ["pi_name", "amount"]

    @pytest.mark.asyncio
    async def test_extraction_with_missing_search_set_skips_embed(self):
        with patch("app.services.export_import_service.SearchSet") as MockSS:
            MockSS.find_one = AsyncMock(return_value=None)
            result = await _resolve_task_references(
                {"search_set_uuid": "ghost"}, "Extraction",
            )
        assert "_embedded_search_set" not in result
        # search_set_uuid is still present for v1 import fallback
        assert result["search_set_uuid"] == "ghost"

    @pytest.mark.asyncio
    async def test_knowledge_base_query_embeds_kb_metadata(self):
        kb = MagicMock()
        kb.title = "NIH Policies"
        kb.description = "Official policy docs"

        with patch("app.models.knowledge.KnowledgeBase") as MockKB:
            MockKB.find_one = AsyncMock(return_value=kb)
            result = await _resolve_task_references(
                {"kb_uuid": "kb-1"}, "KnowledgeBaseQuery",
            )

        assert result["_embedded_knowledge_base"] == {
            "title": "NIH Policies",
            "description": "Official policy docs",
        }

    @pytest.mark.asyncio
    async def test_selected_document_marked_non_portable_with_title(self):
        doc = MagicMock()
        doc.title = "Proposal.pdf"
        with patch("app.models.document.SmartDocument") as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=doc)
            result = await _resolve_task_references(
                {
                    "input_source": "select_document",
                    "selected_document_uuid": "doc-1",
                },
                "Extraction",
            )

        ref = result["_embedded_document_ref"]
        assert ref["title"] == "Proposal.pdf"
        assert ref["uuid"] == "doc-1"
        assert ref["_portable"] is False
        assert "re-selected" in ref["_note"]
