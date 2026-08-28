"""document_usage: what references a document (KBs, extractions, workflows)
and its folder path. The query helpers are patched; the assembly and the
workflow task → step → workflow merge are exercised for real."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.access_control import TeamAccessContext
from app.services.document_usage import build_workflow_entries, document_usage, in_caller_tenants


def _wf(id_, name, *, steps=None, input_config=None):
    return SimpleNamespace(id=id_, name=name, steps=steps or [], input_config=input_config or {})


class TestBuildWorkflowEntries:
    def test_fixed_and_step_references_merge_per_workflow(self):
        doc = "DOC1"
        task_sel = SimpleNamespace(id="t1", name="Prompt", data={"selected_document_uuid": doc})
        task_tpl = SimpleNamespace(id="t2", name="FormFiller", data={"template_document_uuid": doc})
        task_other = SimpleNamespace(id="t3", name="Prompt", data={"selected_document_uuid": "OTHER"})
        step_a = SimpleNamespace(id="s1", name="Summarize", tasks=["t1", "t3"])
        step_b = SimpleNamespace(id="s2", name="Fill form", tasks=["t2"])
        wf_both = _wf("w1", "Award review", steps=["s1", "s2"],
                      input_config={"fixed_documents": [{"uuid": doc, "title": "x"}]})
        wf_fixed_only = _wf("w2", "Bare ids", input_config={"fixed_documents": [doc, "z"]})
        wf_no_match = _wf("w3", "Unrelated", input_config={"fixed_documents": [{"uuid": "OTHER"}]})

        entries = build_workflow_entries(
            doc,
            fixed_workflows=[wf_both, wf_fixed_only, wf_no_match],
            step_workflows=[wf_both],
            steps=[step_a, step_b],
            tasks=[task_sel, task_tpl, task_other],
        )

        assert [e["id"] for e in entries] == ["w1", "w2"]
        assert entries[0]["name"] == "Award review"
        assert entries[0]["uses"] == [
            {"kind": "fixed_document"},
            {"kind": "step_document", "step": "Summarize", "task": "Prompt", "role": "selected document"},
            {"kind": "step_document", "step": "Fill form", "task": "FormFiller", "role": "form template"},
        ]
        assert entries[1]["uses"] == [{"kind": "fixed_document"}]

    def test_no_references(self):
        assert build_workflow_entries("DOC", [], [], [], []) == []


class TestDocumentUsage:
    @pytest.mark.asyncio
    async def test_assembles_all_sections_and_total(self):
        doc = SimpleNamespace(uuid="DOC1", title="Award.pdf", folder="f2", team_id=None)
        with patch("app.services.document_usage.access_control.get_team_access_context",
                   new=AsyncMock(return_value=TeamAccessContext(team_uuids={"team-a"}))), \
             patch("app.services.document_usage.access_control.get_authorized_document",
                   new=AsyncMock(return_value=doc)), \
             patch("app.services.document_usage._folder_path",
                   new=AsyncMock(return_value=[{"uuid": "f1", "title": "Grants"}, {"uuid": "f2", "title": "FY26"}])), \
             patch("app.services.document_usage._knowledge_bases_using",
                   new=AsyncMock(return_value=[{"uuid": "kb1", "title": "Policies", "exists": True}])), \
             patch("app.services.document_usage._extractions_using",
                   new=AsyncMock(return_value=[{"uuid": "ss1", "title": "Budget fields", "exists": True,
                                                "test_cases": [{"uuid": "tc1", "label": "Case A"}]}])), \
             patch("app.services.document_usage._workflows_using",
                   new=AsyncMock(return_value=[{"id": "w1", "name": "Award review", "uses": [{"kind": "fixed_document"}]}])):
            out = await document_usage("DOC1", user=MagicMock())

        assert out["document"] == {"uuid": "DOC1", "title": "Award.pdf"}
        assert [f["title"] for f in out["folder"]["path"]] == ["Grants", "FY26"]
        assert out["knowledge_bases"][0]["title"] == "Policies"
        assert out["extractions"][0]["test_cases"] == [{"uuid": "tc1", "label": "Case A"}]
        assert out["workflows"][0]["name"] == "Award review"
        assert out["total"] == 3

    @pytest.mark.asyncio
    async def test_unauthorized_or_missing_document_is_none(self):
        with patch("app.services.document_usage.access_control.get_team_access_context",
                   new=AsyncMock(return_value=TeamAccessContext())), \
             patch("app.services.document_usage.access_control.get_authorized_document",
                   new=AsyncMock(return_value=None)), \
             patch("app.services.document_usage._knowledge_bases_using", new=AsyncMock()) as kb:
            assert await document_usage("nope", user=MagicMock()) is None
        kb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_folder_path_walks_to_root_and_stops_on_cycles(self):
        from app.services import document_usage as mod

        folders = {
            "a": SimpleNamespace(uuid="a", title="Top", parent_id="0"),
            "b": SimpleNamespace(uuid="b", title="Mid", parent_id="a"),
            "c": SimpleNamespace(uuid="c", title="Leaf", parent_id="b"),
            "x": SimpleNamespace(uuid="x", title="Loop1", parent_id="y"),
            "y": SimpleNamespace(uuid="y", title="Loop2", parent_id="x"),
        }
        with patch.object(mod.SmartFolder, "find_one", new=AsyncMock(side_effect=lambda q: folders.get(_uuid_of(q)))):
            assert [f["title"] for f in await mod._folder_path("c")] == ["Top", "Mid", "Leaf"]
            assert [f["title"] for f in await mod._folder_path("x")] == ["Loop2", "Loop1"]
            assert await mod._folder_path("0") == []
            assert await mod._folder_path(None) == []


class TestTenantScope:
    """Referencing objects from a team the caller is not in are another
    tenant's: their titles must not surface through a shared document."""

    def test_in_caller_tenants(self):
        visible = {"team-a"}
        assert in_caller_tenants(SimpleNamespace(team_id=None), visible)      # personal
        assert in_caller_tenants(SimpleNamespace(team_id="team-a"), visible)  # own team
        assert not in_caller_tenants(SimpleNamespace(team_id="team-b"), visible)
        assert in_caller_tenants(SimpleNamespace(), set())                    # no team_id field

    @pytest.mark.asyncio
    async def test_other_tenants_objects_are_dropped(self):
        from app.services import document_usage as mod

        def _find(rows):
            return lambda *a, **k: SimpleNamespace(to_list=AsyncMock(return_value=rows))

        kb_sources = [SimpleNamespace(knowledge_base_uuid="kb-mine"), SimpleNamespace(knowledge_base_uuid="kb-theirs")]
        kbs = [SimpleNamespace(uuid="kb-mine", title="Policies", team_id="team-a"),
               SimpleNamespace(uuid="kb-theirs", title="Secret KB", team_id="team-b")]
        cases = [SimpleNamespace(uuid="tc1", label="A", search_set_uuid="ss-personal"),
                 SimpleNamespace(uuid="tc2", label="B", search_set_uuid="ss-theirs")]
        sets = [SimpleNamespace(uuid="ss-personal", title="Budget", team_id=None),
                SimpleNamespace(uuid="ss-theirs", title="Secret set", team_id="team-b")]
        wfs = [_wf("w1", "Mine", input_config={"fixed_documents": ["DOC"]}),
               _wf("w2", "Their workflow", input_config={"fixed_documents": ["DOC"]})]
        wfs[0].team_id = "team-a"
        wfs[1].team_id = "team-b"

        with patch.object(mod.KnowledgeBaseSource, "find", new=_find(kb_sources)), \
             patch.object(mod.KnowledgeBase, "find", new=_find(kbs)), \
             patch.object(mod.ExtractionTestCase, "find", new=_find(cases)), \
             patch.object(mod.SearchSet, "find", new=_find(sets)), \
             patch.object(mod.Workflow, "find", new=_find(wfs)), \
             patch.object(mod.WorkflowStepTask, "find", new=_find([])):
            visible = {"team-a"}
            assert [k["title"] for k in await mod._knowledge_bases_using("DOC", visible)] == ["Policies"]
            assert [e["title"] for e in await mod._extractions_using("DOC", visible)] == ["Budget"]
            assert [w["name"] for w in await mod._workflows_using("DOC", visible)] == ["Mine"]


class TestLookupGrouping:
    """Several references to one object are one entry, and a workflow step
    lookup is skipped when no task names the document."""

    @pytest.mark.asyncio
    async def test_kb_sources_group_per_knowledge_base_and_name_missing_ones(self):
        from app.services import document_usage as mod

        def _find(rows):
            return lambda *a, **k: SimpleNamespace(to_list=AsyncMock(return_value=rows))

        sources = [SimpleNamespace(knowledge_base_uuid="kb1"), SimpleNamespace(knowledge_base_uuid="kb1"),
                   SimpleNamespace(knowledge_base_uuid="kb-gone")]
        kbs = [SimpleNamespace(uuid="kb1", title="Policies", team_id=None)]
        cases = [SimpleNamespace(uuid="tc1", label="A", search_set_uuid="ss1"),
                 SimpleNamespace(uuid="tc2", label="B", search_set_uuid="ss1")]
        sets = [SimpleNamespace(uuid="ss1", title="Budget", team_id=None)]
        with patch.object(mod.KnowledgeBaseSource, "find", new=_find(sources)), \
             patch.object(mod.KnowledgeBase, "find", new=_find(kbs)), \
             patch.object(mod.ExtractionTestCase, "find", new=_find(cases)), \
             patch.object(mod.SearchSet, "find", new=_find(sets)):
            kb_out = await mod._knowledge_bases_using("DOC", set())
            ex_out = await mod._extractions_using("DOC", set())
        assert [(k["uuid"], k["exists"]) for k in kb_out] == [("kb1", True), ("kb-gone", False)]
        assert [tc["label"] for tc in ex_out[0]["test_cases"]] == ["A", "B"]
        assert len(ex_out) == 1

    @pytest.mark.asyncio
    async def test_step_lookups_skipped_when_no_task_names_the_document(self):
        from app.services import document_usage as mod

        wf_find = MagicMock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=[])))
        with patch.object(mod.Workflow, "find", new=wf_find), \
             patch.object(mod.WorkflowStepTask, "find",
                          new=MagicMock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=[])))), \
             patch.object(mod.WorkflowStep, "find", new=MagicMock()) as step_find:
            assert await mod._workflows_using("DOC", set()) == []
        step_find.assert_not_called()
        assert wf_find.call_count == 1


def _uuid_of(query) -> str:
    return str(query["uuid"])
