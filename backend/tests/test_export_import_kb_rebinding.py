"""Knowledge bases referenced by an exported workflow are rebound on import.

The exported uuid never exists on the target install. The importer binds the
task to a local base with the same catalog ``seed_id`` (then the exact
title) that the importing user can see; otherwise it clears the reference
and leaves the note the editor shows. A grounded task's per-base queries
travel with each base.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.export_import_service import (
    _reconstruct_task_references,
    _resolve_task_references,
)


def _kb(uuid: str, title: str, seed_id: str | None = None):
    kb = MagicMock()
    kb.uuid = uuid
    kb.title = title
    kb.description = "desc"
    kb.resource_config = {"seed_id": seed_id} if seed_id else {}
    return kb


def _find_one_for(local: list):
    """A ``find_one`` that answers a {"$and": [visible, condition]} query
    from a list of local bases, matching on seed_id or title."""

    async def find_one(query, *args, **kwargs):
        if isinstance(query, dict) and "$and" in query:
            condition = query["$and"][-1]
        else:
            condition = {}
        for kb in local:
            if "resource_config.seed_id" in condition and kb.resource_config.get("seed_id") == condition["resource_config.seed_id"]:
                return kb
            if "title" in condition and kb.title == condition["title"]:
                return kb
        return None

    return find_one


class TestExportEmbedsSeedIds:
    @pytest.mark.asyncio
    async def test_kb_query_carries_the_catalog_seed(self):
        with patch("app.models.knowledge.KnowledgeBase") as MockKB:
            MockKB.find_one = AsyncMock(return_value=_kb("u1", "OMB Uniform Guidance", "uniform_guidance"))
            result = await _resolve_task_references({"kb_uuid": "u1"}, "KnowledgeBaseQuery")
        assert result["_embedded_knowledge_base"] == {
            "title": "OMB Uniform Guidance", "description": "desc", "seed_id": "uniform_guidance",
        }

    @pytest.mark.asyncio
    async def test_grounded_task_embeds_every_base_with_its_queries(self):
        bases = {"u1": _kb("u1", "OMB Uniform Guidance", "uniform_guidance"), "u2": _kb("u2", "UI OSP")}
        with patch("app.models.knowledge.KnowledgeBase") as MockKB:
            # One lookup per listed base, in order.
            MockKB.find_one = AsyncMock(side_effect=[bases["u1"], bases["u2"]])
            result = await _resolve_task_references(
                {"kb_grounding": {
                    "knowledge_bases": [
                        {"kb_uuid": "u1", "queries": ["cost sharing 200.306"]},
                        {"kb_uuid": "u2", "queries": ["approval routing"]},
                    ],
                    "_kb_meta": {"u1": {}},
                }},
                "Prompt",
            )
        embedded = result["kb_grounding"]["_embedded_knowledge_bases"]
        assert [(e["title"], e["queries"]) for e in embedded] == [
            ("OMB Uniform Guidance", ["cost sharing 200.306"]),
            ("UI OSP", ["approval routing"]),
        ]
        assert embedded[0]["seed_id"] == "uniform_guidance"
        assert "seed_id" not in embedded[1]
        assert "_kb_meta" not in result["kb_grounding"]

    @pytest.mark.asyncio
    async def test_flat_form_export_gives_each_base_the_shared_queries(self):
        bases = {"u1": _kb("u1", "OMB UG"), "u2": _kb("u2", "UI OSP")}
        with patch("app.models.knowledge.KnowledgeBase") as MockKB:
            MockKB.find_one = AsyncMock(side_effect=[bases["u1"], bases["u2"]])
            result = await _resolve_task_references(
                {"kb_grounding": {"knowledge_bases": ["u1", "u2"], "queries": ["cost sharing"]}},
                "Prompt",
            )
        embedded = result["kb_grounding"]["_embedded_knowledge_bases"]
        assert [e["queries"] for e in embedded] == [["cost sharing"], ["cost sharing"]]


class TestImportRebinding:
    @pytest.mark.asyncio
    async def test_kb_query_binds_to_the_same_catalog_base(self):
        local = [_kb("local-ug", "OMB Uniform Guidance (2 CFR 200)", "uniform_guidance")]
        with patch("app.models.knowledge.KnowledgeBase") as MockKB:
            MockKB.find_one = AsyncMock(side_effect=_find_one_for(local))
            result = await _reconstruct_task_references(
                {
                    "kb_uuid": "exported-uuid",
                    "_embedded_knowledge_base": {"title": "Old title", "seed_id": "uniform_guidance"},
                },
                "KnowledgeBaseQuery", "user-1", None,
            )
        assert result["kb_uuid"] == "local-ug"
        assert "_import_note" not in result
        assert "_embedded_knowledge_base" not in result

    @pytest.mark.asyncio
    async def test_falls_back_to_the_exact_title(self):
        local = [_kb("local-osp", "University of Idaho Office of Sponsored Programs")]
        with patch("app.models.knowledge.KnowledgeBase") as MockKB:
            MockKB.find_one = AsyncMock(side_effect=_find_one_for(local))
            result = await _reconstruct_task_references(
                {
                    "kb_uuid": "x",
                    "_embedded_knowledge_base": {"title": "University of Idaho Office of Sponsored Programs"},
                },
                "KnowledgeBaseQuery", "user-1", "team-1",
            )
        assert result["kb_uuid"] == "local-osp"

    @pytest.mark.asyncio
    async def test_no_match_clears_the_uuid_and_leaves_the_note(self):
        with patch("app.models.knowledge.KnowledgeBase") as MockKB:
            MockKB.find_one = AsyncMock(side_effect=_find_one_for([]))
            result = await _reconstruct_task_references(
                {"kb_uuid": "x", "_embedded_knowledge_base": {"title": "NIH GPS"}},
                "KnowledgeBaseQuery", "user-1", None,
            )
        assert result["kb_uuid"] == ""
        assert "NIH GPS" in result["_import_note"]
        assert "select a local knowledge base" in result["_import_note"]

    @pytest.mark.asyncio
    async def test_lookup_failure_counts_as_no_match(self):
        with patch("app.models.knowledge.KnowledgeBase") as MockKB:
            MockKB.find_one = AsyncMock(side_effect=RuntimeError("beanie not initialised"))
            result = await _reconstruct_task_references(
                {"kb_uuid": "x", "_embedded_knowledge_base": {"title": "NIH GPS"}},
                "KnowledgeBaseQuery", "user-1", None,
            )
        assert result["kb_uuid"] == ""
        assert "NIH GPS" in result["_import_note"]

    @pytest.mark.asyncio
    async def test_grounded_task_keeps_each_bound_base_with_its_queries(self):
        local = [_kb("local-ug", "OMB Uniform Guidance", "uniform_guidance")]
        with patch("app.models.knowledge.KnowledgeBase") as MockKB:
            MockKB.find_one = AsyncMock(side_effect=_find_one_for(local))
            result = await _reconstruct_task_references(
                {
                    "prompt": "p",
                    "kb_grounding": {
                        "knowledge_bases": [
                            {"kb_uuid": "exp-1", "queries": ["cost sharing 200.306"]},
                            {"kb_uuid": "exp-2", "queries": ["approval routing"]},
                        ],
                        "queries": ["stale shared list"],
                        "_embedded_knowledge_bases": [
                            {"title": "OMB Uniform Guidance", "seed_id": "uniform_guidance", "queries": ["cost sharing 200.306"]},
                            {"title": "UI OSP", "queries": ["approval routing"]},
                        ],
                    },
                },
                "Prompt", "user-1", None,
            )
        grounding = result["kb_grounding"]
        assert grounding["knowledge_bases"] == [{"kb_uuid": "local-ug", "queries": ["cost sharing 200.306"]}]
        assert "queries" not in grounding
        assert "_embedded_knowledge_bases" not in grounding
        assert "UI OSP" in result["_import_note"]
        assert "for grounding" in result["_import_note"]

    @pytest.mark.asyncio
    async def test_bare_uuids_from_an_old_export_are_cleared(self):
        result = await _reconstruct_task_references(
            {"kb_grounding": {"knowledge_bases": ["exp-1"], "queries": ["q"]}},
            "Prompt", "user-1", None,
        )
        assert result["kb_grounding"]["knowledge_bases"] == []
        assert "do not exist here" in result["_import_note"]
