"""Per-task knowledge-base grounding wired into the workflow nodes.

Grounding is a property of the task (``data.kb_grounding``), independent of
the step's data sources: the node retrieves its own passages
(kb_grounding.py) and appends them to whatever input the step handed it.
These tests cover the wiring — the retrieval pipeline itself is covered in
test_kb_grounding.py.
"""

from unittest.mock import MagicMock, patch

from app.services.workflow_engine import (
    ExtractionNode,
    FormatNode,
    KnowledgeBaseQueryNode,
    MultiTaskNode,
    PromptNode,
    apply_step_input_config,
)


def _grounding_chunk(content="Cost sharing means the portion of project costs not paid by Federal funds."):
    return {
        "content": content,
        "metadata": {"source_name": "Subpart C", "source_id": "s1", "page": 12},
        "chunk_id": "c1", "score": 0.1, "similarity": 0.9,
    }


def _grounding_dm(chunks):
    dm = MagicMock()
    dm.query_kb.return_value = chunks
    dm.get_kb_chunks_containing.return_value = []
    return dm


GROUNDED_PROMPT = {
    "prompt": "List the budget rules this announcement imposes.",
    "model": "test-model",
    "input_sources": ["workflow_documents"],
    "doc_texts": ["RFA body: cost share of 20% required."],
    "kb_grounding": {
        "knowledge_bases": [{"kb_uuid": "ug", "queries": ["cost sharing requirements"]}],
    },
    "_kb_meta": {"ug": {"title": "OMB Uniform Guidance", "exists": True}},
}


class TestGroundedPromptNode:
    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_passages_land_after_the_document_in_their_own_section(self, mock_dm_cls, mock_llm):
        dm = _grounding_dm([_grounding_chunk()])
        mock_dm_cls.return_value = dm
        mock_llm.return_value = "answer"

        result = PromptNode(dict(GROUNDED_PROMPT)).process({"output": ["uuid"], "step_name": "Document"})

        data = mock_llm.call_args.kwargs["data"]
        assert data.index("=== Workflow Documents ===") < data.index("=== Knowledge Base Passages ===")
        assert "RFA body" in data
        assert "OMB Uniform Guidance — Subpart C · p. 12" in data
        assert "Cost sharing means" in data
        # The store was asked this task's own question, not a shared one.
        assert dm.query_kb.call_args.args[:2] == ("ug", "cost sharing requirements")
        assert result["output"] == "answer"
        assert "error" not in result
        assert result["retrieved_sources"][0]["kb_title"] == "OMB Uniform Guidance"
        assert result["retrieved_sources"][0]["document_title"] == "Subpart C"

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_grounding_survives_the_step_level_input_config(self, mock_dm_cls, mock_llm):
        """Input sources are set on the step and pushed onto every task; the
        task's own grounding is not part of that and must ride alongside."""
        mock_dm_cls.return_value = _grounding_dm([_grounding_chunk()])
        mock_llm.return_value = "answer"
        task_data = {**GROUNDED_PROMPT}
        task_data.pop("input_sources")
        apply_step_input_config({"input_sources": ["workflow_documents"]}, task_data)
        assert task_data["input_sources"] == ["workflow_documents"]

        PromptNode(task_data).process({"output": ["u"], "step_name": "Document"})
        data = mock_llm.call_args.kwargs["data"]
        assert "=== Knowledge Base Passages ===" in data

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_each_base_is_searched_with_its_own_queries(self, mock_dm_cls, mock_llm):
        dm = _grounding_dm([_grounding_chunk()])
        mock_dm_cls.return_value = dm
        mock_llm.return_value = "answer"
        data = {
            **GROUNDED_PROMPT,
            "kb_grounding": {"knowledge_bases": [
                {"kb_uuid": "ug", "queries": ["cost sharing 200.306"]},
                {"kb_uuid": "osp", "queries": ["cost share approval routing"]},
            ]},
            "_kb_meta": {
                "ug": {"title": "OMB Uniform Guidance", "exists": True},
                "osp": {"title": "UI OSP", "exists": True},
            },
        }
        PromptNode(data).process({"output": ["u"], "step_name": "Document"})
        calls = [(c.args[0], c.args[1]) for c in dm.query_kb.call_args_list]
        assert calls == [("ug", "cost sharing 200.306"), ("osp", "cost share approval routing")]

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_a_base_without_queries_fails_the_step_by_name(self, mock_llm):
        data = {
            **GROUNDED_PROMPT,
            "kb_grounding": {"knowledge_bases": [{"kb_uuid": "ug", "queries": []}]},
        }
        result = PromptNode(data).process({"output": ["u"], "step_name": "Document"})
        assert "error" in result
        assert "query is empty" in result["error"] or "no retrieval query" in result["error"]
        assert result["output"] == ""
        mock_llm.assert_not_called()

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_one_of_two_bases_without_queries_names_it(self, mock_llm):
        data = {
            **GROUNDED_PROMPT,
            "kb_grounding": {"knowledge_bases": [
                {"kb_uuid": "ug", "queries": ["cost sharing"]}, {"kb_uuid": "osp"},
            ]},
            "_kb_meta": {
                "ug": {"title": "OMB Uniform Guidance", "exists": True},
                "osp": {"title": "UI OSP", "exists": True},
            },
        }
        result = PromptNode(data).process({"output": ["u"], "step_name": "Document"})
        assert "no retrieval query for UI OSP" in result["error"]
        mock_llm.assert_not_called()

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_deleted_knowledge_base_fails_the_step_by_name(self, mock_llm):
        data = {**GROUNDED_PROMPT, "_kb_meta": {"ug": {"title": None, "exists": False}}}
        result = PromptNode(data).process({"output": ["u"], "step_name": "Document"})
        assert "Knowledge base not found" in result["error"]
        mock_llm.assert_not_called()

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_no_matches_warns_and_runs_on_the_document_alone(self, mock_dm_cls, mock_llm):
        mock_dm_cls.return_value = _grounding_dm([])
        mock_llm.return_value = "answer"
        result = PromptNode(dict(GROUNDED_PROMPT)).process({"output": ["u"], "step_name": "Document"})
        # One non-empty source -> the raw document, no section headers.
        assert mock_llm.call_args.kwargs["data"] == GROUNDED_PROMPT["doc_texts"][0]
        assert "no matching passages" in result["warning"]
        assert "error" not in result
        assert "retrieved_sources" not in result

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_store_failure_fails_the_step_instead_of_flowing_downstream(self, mock_dm_cls, mock_llm):
        dm = _grounding_dm([])
        dm.query_kb.side_effect = RuntimeError("chroma down")
        mock_dm_cls.return_value = dm
        result = PromptNode(dict(GROUNDED_PROMPT)).process({"output": ["u"], "step_name": "Document"})
        assert "Knowledge base lookup failed: chroma down" in result["error"]
        mock_llm.assert_not_called()

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_tasks_without_grounding_never_touch_the_store(self, mock_dm_cls, mock_llm):
        mock_llm.return_value = "answer"
        data = {**GROUNDED_PROMPT}
        data.pop("kb_grounding")
        PromptNode(data).process({"output": ["u"], "step_name": "Document"})
        mock_dm_cls.assert_not_called()
        assert mock_llm.call_args.kwargs["data"] == GROUNDED_PROMPT["doc_texts"][0]

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_an_empty_grounding_block_is_not_grounding(self, mock_dm_cls, mock_llm):
        """The editor writes ``kb_grounding: undefined`` when grounding is
        turned off; an empty list left behind must read the same way."""
        mock_llm.return_value = "answer"
        data = {**GROUNDED_PROMPT, "kb_grounding": {"knowledge_bases": []}}
        result = PromptNode(data).process({"output": ["u"], "step_name": "Document"})
        mock_dm_cls.assert_not_called()
        assert "error" not in result

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_grounding_query_can_read_the_previous_step(self, mock_dm_cls, mock_llm):
        dm = _grounding_dm([_grounding_chunk()])
        mock_dm_cls.return_value = dm
        mock_llm.return_value = "answer"
        data = {
            **GROUNDED_PROMPT,
            "input_sources": ["step_input"],
            "kb_grounding": {"knowledge_bases": [
                {"kb_uuid": "ug", "queries": ["{{ inputs.output.sponsor }} proposal policy"]},
            ]},
        }
        PromptNode(data).process({"output": {"sponsor": "NSF"}, "step_name": "Extraction"})
        assert dm.query_kb.call_args.args[1] == "NSF proposal policy"

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_citations_survive_the_step_wrapper(self, mock_dm_cls, mock_llm):
        """MultiTaskNode is what a real run wraps every task in; it must carry
        a grounded task's citations and warnings up to the step."""
        mock_dm_cls.return_value = _grounding_dm([_grounding_chunk()])
        mock_llm.return_value = "answer"
        step = MultiTaskNode("Budget rules")
        step.add_tasks([PromptNode(dict(GROUNDED_PROMPT))])
        out = step.process({"output": ["u"], "step_name": "Document"})
        assert out["output"] == "answer"
        assert out["retrieved_sources"][0]["kb_title"] == "OMB Uniform Guidance"


class TestGroundedFormatNode:
    @patch("app.services.workflow_engine.format_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_formatter_reads_passages_too(self, mock_dm_cls, mock_format):
        mock_dm_cls.return_value = _grounding_dm([_grounding_chunk()])
        mock_format.return_value = ("prompt", "formatted")
        node = FormatNode({
            "format_template": "Render as a checklist", "model": "test-model",
            "input_sources": ["step_input"],
            "kb_grounding": {"knowledge_bases": [{"kb_uuid": "ug", "queries": ["cost sharing"]}]},
        })
        result = node.process({"output": "fragments", "step_name": "Extraction"})
        text = mock_format.call_args.args[2]
        assert text.index("=== Previous Step Output ===") < text.index("=== Knowledge Base Passages ===")
        assert result["output"] == "formatted"
        assert result["retrieved_sources"]


class TestGroundedExtractionNode:
    @patch("app.services.workflow_engine.data_extraction_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_passages_ride_as_reference_context_not_as_a_document(self, mock_dm_cls, mock_extract):
        mock_dm_cls.return_value = _grounding_dm([_grounding_chunk()])
        mock_extract.return_value = {"raw": [{"Cost share": "20%"}], "formatted": "- Cost share: 20%"}
        node = ExtractionNode({
            "keys": ["Cost share"], "model": "test-model",
            "input_sources": ["workflow_documents"],
            "doc_texts": ["RFA body"],
            "kb_grounding": {"knowledge_bases": [{"kb_uuid": "ug", "queries": ["cost sharing"]}]},
        })
        result = node.process({"output": ["u"], "step_name": "Document"})

        kwargs = mock_extract.call_args.kwargs
        assert kwargs["doc_texts"] == ["RFA body"]           # still one entity per document
        assert "Cost sharing means" in kwargs["reference_context"]
        assert result["output"] == [{"Cost share": "20%"}]
        assert result["retrieved_sources"][0]["document_title"] == "Subpart C"

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_ungrounded_extraction_passes_no_reference_context(self, mock_extract):
        mock_extract.return_value = {"raw": [], "formatted": ""}
        ExtractionNode({"keys": ["A"], "model": "m", "doc_texts": ["doc"]}).process(
            {"output": ["u"], "step_name": "Document"},
        )
        assert "reference_context" not in mock_extract.call_args.kwargs


class TestKnowledgeBaseQueryNodeMultiple:
    def _dm(self):
        dm = MagicMock()
        dm.get_kb_chunks_containing.return_value = []

        def query_kb(kb_uuid, query, k=8, min_similarity=0.0, **kw):
            return [{
                "content": f"{kb_uuid} says: {query}",
                "metadata": {"source_name": f"{kb_uuid}.pdf", "source_id": kb_uuid},
                "chunk_id": f"{kb_uuid}-{query}", "similarity": 0.9,
            }]

        dm.query_kb.side_effect = query_kb
        return dm

    @patch("app.services.document_manager.get_document_manager")
    def test_several_bases_and_queries_in_one_step_give_one_text_block(self, mock_dm_cls):
        dm = self._dm()
        mock_dm_cls.return_value = dm
        node = KnowledgeBaseQueryNode({
            "knowledge_bases": ["ug", "osp"],
            "queries": ["cost share", "F&A rate"],
            "k": 2,
            "_kb_meta": {
                "ug": {"title": "OMB Uniform Guidance", "exists": True},
                "osp": {"title": "UI OSP", "exists": True},
            },
        })
        result = node.process({"output": "prev"})

        assert dm.query_kb.call_count == 4
        out = result["output"]
        assert isinstance(out, str)  # one block, never a JSON array of blocks
        assert "OMB Uniform Guidance — ug.pdf" in out
        assert "UI OSP — osp.pdf" in out
        assert "partial excerpts" in out
        assert len(result["retrieved_sources"]) == 4
        assert {s["kb_title"] for s in result["retrieved_sources"]} == {"OMB Uniform Guidance", "UI OSP"}

    @patch("app.services.document_manager.get_document_manager")
    def test_augment_mode_keeps_the_previous_step_output(self, mock_dm_cls):
        mock_dm_cls.return_value = self._dm()
        node = KnowledgeBaseQueryNode({"kb_uuid": "ug", "query": "cost share", "mode": "augment"})
        result = node.process({"output": "upstream findings", "step_name": "Extraction"})
        out = result["output"]
        assert out.index("=== Previous Step Output ===\nupstream findings") < out.index("=== Knowledge Base Passages ===")
        assert "ug says: cost share" in out

    @patch("app.services.document_manager.get_document_manager")
    def test_answer_mode_asks_every_query(self, mock_dm_cls):
        mock_dm_cls.return_value = self._dm()
        with patch("app.services.workflow_engine.llm_chat_model", return_value="ans") as mock_llm:
            node = KnowledgeBaseQueryNode({
                "kb_uuid": "ug", "queries": ["cost share", "F&A rate"], "mode": "answer",
            })
            result = node.process({"output": "prev"})
        assert result["output"] == "ans"
        assert "QUESTION:\ncost share\nF&A rate" in mock_llm.call_args.kwargs["prompt"]

    @patch("app.services.document_manager.get_document_manager")
    def test_deleted_base_fails_the_lookup_by_name(self, mock_dm_cls):
        mock_dm_cls.return_value = self._dm()
        node = KnowledgeBaseQueryNode({
            "kb_uuid": "gone", "query": "q",
            "_kb_meta": {"gone": {"title": None, "exists": False}},
        })
        result = node.process({"output": "prev"})
        assert "Knowledge base not found" in result["error"]
        assert result["output"] == ""


UPSTREAM_SOURCES = [{
    "document_title": "Subpart C", "page": 12, "kb_title": "OMB Uniform Guidance",
    "label": "OMB Uniform Guidance — Subpart C · p. 12", "chunk_id": "c1",
    "content": "Cost sharing means the portion of project costs not paid by Federal funds.",
}]


class TestInlineCitations:
    """The citation rule lives in the INSTRUCTION (the grounded prompt tells
    the model CONTEXT is data, so a rule inside the passages is ignored), and
    a later step that reads cited text keeps the citations and the passages."""

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_grounded_prompt_carries_the_citation_rule_in_its_instruction(self, mock_dm_cls, mock_llm):
        mock_dm_cls.return_value = _grounding_dm([_grounding_chunk()])
        mock_llm.return_value = "ok"
        PromptNode(dict(GROUNDED_PROMPT)).process({"output": ["u"], "step_name": "Document"})
        sent = mock_llm.call_args.kwargs["prompt"]
        assert sent.startswith(GROUNDED_PROMPT["prompt"])
        assert "CITATIONS (required)" in sent
        assert "If your output is JSON" in sent

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_an_ungrounded_prompt_is_left_alone(self, mock_llm):
        mock_llm.return_value = "ok"
        data = {**GROUNDED_PROMPT}
        data.pop("kb_grounding")
        PromptNode(data).process({"output": ["u"], "step_name": "Document"})
        assert "CITATIONS" not in mock_llm.call_args.kwargs["prompt"]

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_a_later_step_keeps_citations_and_carries_the_passages(self, mock_llm):
        """The RFA consolidation: reads cited fragments, must keep the
        citations with the statements, and its own result must resolve them."""
        mock_llm.return_value = "- Cost share: 20% [OMB Uniform Guidance — Subpart C · p. 12]"
        node = PromptNode({"prompt": "Render as markdown", "model": "m", "input_sources": ["step_input"]})
        result = node.process({
            "output": '{"cost_share": "20% [OMB Uniform Guidance — Subpart C · p. 12]"}',
            "step_name": "Budget", "retrieved_sources": UPSTREAM_SOURCES,
        })
        assert "CITATIONS (required)" in mock_llm.call_args.kwargs["prompt"]
        assert mock_llm.call_count == 1
        assert result["retrieved_sources"] == UPSTREAM_SOURCES
        assert "warning" not in result

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_a_later_step_reading_only_documents_does_not_inherit(self, mock_llm):
        mock_llm.return_value = "ok"
        node = PromptNode({
            "prompt": "Summarize", "model": "m",
            "input_sources": ["workflow_documents"], "doc_texts": ["doc"],
        })
        result = node.process({"output": "cited text", "step_name": "Budget", "retrieved_sources": UPSTREAM_SOURCES})
        assert "CITATIONS" not in mock_llm.call_args.kwargs["prompt"]
        assert "retrieved_sources" not in result

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_an_invented_citation_is_flagged_on_the_step(self, mock_dm_cls, mock_llm):
        mock_dm_cls.return_value = _grounding_dm([_grounding_chunk()])
        mock_llm.return_value = "The cap is 10% [NIH Grants Policy Statement — Section 7 · p. 3]."
        result = PromptNode(dict(GROUNDED_PROMPT)).process({"output": ["u"], "step_name": "Document"})
        assert "not among the retrieved passages" in result["warning"]
        assert "NIH Grants Policy Statement" in result["warning"]
        assert "error" not in result

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_matching_and_plain_brackets_do_not_warn(self, mock_dm_cls, mock_llm):
        mock_dm_cls.return_value = _grounding_dm([_grounding_chunk()])
        mock_llm.return_value = (
            "Cost share is required [OMB Uniform Guidance — Subpart C · p. 12]. "
            "Amount: [N/A]. See [Section II.B] of the announcement."
        )
        result = PromptNode(dict(GROUNDED_PROMPT)).process({"output": ["u"], "step_name": "Document"})
        assert "warning" not in result

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_an_uncited_reply_is_asked_once_more(self, mock_dm_cls, mock_llm):
        mock_dm_cls.return_value = _grounding_dm([_grounding_chunk()])
        mock_llm.side_effect = [
            "Cost share is 20%.",
            "Cost share is 20% [OMB Uniform Guidance — Subpart C · p. 12].",
        ]
        result = PromptNode(dict(GROUNDED_PROMPT)).process({"output": ["u"], "step_name": "Document"})
        assert mock_llm.call_count == 2
        assert "cited no passage" not in str(result.get("warning"))
        assert "did not cite them" in mock_llm.call_args_list[1].kwargs["prompt"]
        assert result["output"].endswith("· p. 12].")

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_the_model_cites_a_tag_and_the_output_carries_the_source_line(self, mock_dm_cls, mock_llm):
        """Passages are shown as [KB1] …; the reply's tag is swapped for the
        exact source line before anything downstream (or the UI) sees it."""
        mock_dm_cls.return_value = _grounding_dm([_grounding_chunk()])
        mock_llm.return_value = '{"rationale": "Cost share must be documented [KB1]."}'
        result = PromptNode(dict(GROUNDED_PROMPT)).process({"output": ["u"], "step_name": "Document"})
        assert "[KB1] OMB Uniform Guidance — Subpart C · p. 12" in str(mock_llm.call_args.kwargs["data"])
        assert "[KB2]" in mock_llm.call_args.kwargs["prompt"]  # the rule's example tag
        assert mock_llm.call_count == 1
        assert result["output"] == (
            '{"rationale": "Cost share must be documented [OMB Uniform Guidance — Subpart C · p. 12]."}'
        )
        assert result["retrieved_sources"][0]["label"] == "OMB Uniform Guidance — Subpart C · p. 12"
        assert "warning" not in result

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_a_later_step_is_told_to_keep_citations_not_to_cite_tags(self, mock_llm):
        mock_llm.return_value = "- Cost share: 20% [OMB Uniform Guidance — Subpart C · p. 12]"
        node = PromptNode({"prompt": "Render as markdown", "model": "m", "input_sources": ["step_input"]})
        node.process({
            "output": "20% [OMB Uniform Guidance — Subpart C · p. 12]",
            "step_name": "Budget", "retrieved_sources": UPSTREAM_SOURCES,
        })
        sent = mock_llm.call_args.kwargs["prompt"]
        assert "keep its citation with it" in sent
        assert "[KB2]" not in sent

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_a_cited_reply_is_not_retried(self, mock_dm_cls, mock_llm):
        mock_dm_cls.return_value = _grounding_dm([_grounding_chunk()])
        mock_llm.return_value = "Cost share is 20% [OMB Uniform Guidance — Subpart C · p. 12]."
        PromptNode(dict(GROUNDED_PROMPT)).process({"output": ["u"], "step_name": "Document"})
        assert mock_llm.call_count == 1

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_a_section_number_alone_still_earns_the_retry(self, mock_dm_cls, mock_llm):
        """An output template can fix a section anchor whether or not a
        passage was used, so only a cited passage tag skips the retry."""
        chunk = _grounding_chunk("§ 200.306 Cost sharing or matching. (a) Under Federal research proposals…")
        mock_dm_cls.return_value = _grounding_dm([chunk])
        mock_llm.side_effect = [
            '{"regulation_anchor": "2 CFR 200.306", "rationale": "Not expected."}',
            '{"regulation_anchor": "2 CFR 200.306", "rationale": "Not expected [KB1]."}',
        ]
        result = PromptNode(dict(GROUNDED_PROMPT)).process({"output": ["u"], "step_name": "Document"})
        assert mock_llm.call_count == 2
        assert "[OMB Uniform Guidance — Subpart C · p. 12]" in result["output"]

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.get_document_manager")
    def test_native_citation_marks_are_resolved_or_dropped(self, mock_dm_cls, mock_llm):
        mock_dm_cls.return_value = _grounding_dm([_grounding_chunk()])
        mock_llm.return_value = "Cost share applies【KB1】. Period is fine【】."
        result = PromptNode(dict(GROUNDED_PROMPT)).process({"output": ["u"], "step_name": "Document"})
        assert result["output"] == "Cost share applies[OMB Uniform Guidance — Subpart C · p. 12]. Period is fine."

    @patch("app.services.workflow_engine.format_model")
    def test_formatter_keeps_citations_from_its_input(self, mock_format):
        mock_format.return_value = ("prompt", "| x | [OMB Uniform Guidance — Subpart C · p. 12] |")
        node = FormatNode({"format_template": "As a table", "model": "m", "input_sources": ["step_input"]})
        result = node.process({"output": "x [OMB Uniform Guidance — Subpart C · p. 12]", "step_name": "B", "retrieved_sources": UPSTREAM_SOURCES})
        assert "CITATIONS (required)" in mock_format.call_args.args[1]
        assert mock_format.call_count == 1
        assert result["retrieved_sources"] == UPSTREAM_SOURCES

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_a_later_step_that_drops_the_citations_is_not_retried(self, mock_llm):
        """Only a task's own passages earn the retry: a step that merely reads
        cited text (e.g. a JSON formatter after a lookup) is asked once, and
        passages its output no longer cites are not carried forward."""
        mock_llm.return_value = '{"total": 20}'
        node = PromptNode({"prompt": "Emit JSON", "model": "m", "input_sources": ["step_input"]})
        result = node.process({
            "output": "Cost share is 20% [OMB Uniform Guidance — Subpart C · p. 12]",
            "step_name": "Budget", "retrieved_sources": UPSTREAM_SOURCES,
        })
        assert mock_llm.call_count == 1
        assert "CITATIONS (required)" in mock_llm.call_args.kwargs["prompt"]
        assert "retrieved_sources" not in result

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_an_invented_citation_in_a_later_step_is_still_flagged(self, mock_llm):
        mock_llm.return_value = "Cost share is 20% [NIH Grants Policy Statement · p. 4]"
        node = PromptNode({"prompt": "Summarize", "model": "m", "input_sources": ["step_input"]})
        result = node.process({
            "output": "x [OMB Uniform Guidance — Subpart C · p. 12]",
            "step_name": "Budget", "retrieved_sources": UPSTREAM_SOURCES,
        })
        assert "not among the retrieved passages" in result["warning"]
