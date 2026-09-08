"""Workflow and automation extractions carry provenance.

`workflow_engine.data_extraction_model` used to call `engine.extract` with
neither `capture_sources` nor `doc_metadata`, so every value produced by a
workflow step — and therefore by the overnight folder-watch automation, the
highest-volume and least-supervised path in the product — arrived with no
quote, no page and no verification. "Source-linked answers" was an
interactive-UI feature the batch layer did not have.

The engine pairs `doc_metadata` with `doc_texts` *by position*, so these tests
lean hardest on alignment: a metadata list that drifts by one entry attributes
every quote to the wrong document.
"""

from unittest.mock import MagicMock, patch

from app.services.extraction_sources import SOURCE_KEY
from app.services.form_fill import DOC_META_TASKS
from app.services.workflow_engine import (
    ExtractionNode,
    data_extraction_model,
    format_extraction_results,
)


def _node(data: dict) -> ExtractionNode:
    return ExtractionNode({"model": "gpt-4o", **data})


class TestExtractionNodeRequestsSources:
    @patch("app.services.workflow_engine.data_extraction_model")
    def test_capture_sources_is_always_on(self, mock_extract):
        mock_extract.return_value = {"raw": [], "formatted": ""}
        _node({"keys": ["X"]}).process({"output": "prev text", "step_name": "Prompt"})
        assert mock_extract.call_args.kwargs["capture_sources"] is True

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_workflow_documents_metadata_is_index_aligned(self, mock_extract):
        mock_extract.return_value = {"raw": [], "formatted": ""}
        _node({
            "keys": ["X"],
            "input_source": "workflow_documents",
            "doc_texts": ["first doc", "second doc"],
            "doc_metas": [
                {"uuid": "u1", "title": "First", "text_markers": [{"page": 1}]},
                {"uuid": "u2", "title": "Second", "text_markers": [{"page": 1}]},
            ],
        }).process({"output": "prev", "step_name": "SomeStep"})

        kwargs = mock_extract.call_args.kwargs
        assert kwargs["doc_texts"] == ["first doc", "second doc"]
        assert [m["uuid"] for m in kwargs["doc_metadata"]] == ["u1", "u2"]
        assert kwargs["doc_metadata"][1]["title"] == "Second"

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_blank_document_text_does_not_shift_metadata(self, mock_extract):
        """A doc that yielded no text is skipped in the texts list, so its
        metadata must be skipped with it — otherwise every later quote is
        attributed one document too early."""
        mock_extract.return_value = {"raw": [], "formatted": ""}
        _node({
            "keys": ["X"],
            "input_source": "workflow_documents",
            "doc_texts": ["", "second doc"],
            "doc_metas": [{"uuid": "u1"}, {"uuid": "u2"}],
        }).process({"output": "prev", "step_name": "SomeStep"})

        kwargs = mock_extract.call_args.kwargs
        assert kwargs["doc_texts"] == ["second doc"]
        assert [m["uuid"] for m in kwargs["doc_metadata"]] == ["u2"]

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_selected_document_carries_its_metadata(self, mock_extract):
        mock_extract.return_value = {"raw": [], "formatted": ""}
        _node({
            "keys": ["Name"],
            "input_source": "select_document",
            "selected_doc_text": "Bob is a scientist.",
            "selected_doc_meta": {"uuid": "sel", "title": "Bio", "text_markers": [{"page": 3}]},
        }).process({"output": "prev", "step_name": "Prompt"})

        kwargs = mock_extract.call_args.kwargs
        assert kwargs["full_text"] == "Bob is a scientist."
        assert kwargs["doc_metadata"] == [
            {"uuid": "sel", "title": "Bio", "text_markers": [{"page": 3}]}
        ]

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_mixed_sources_stay_aligned(self, mock_extract):
        """A previous step's output has no document behind it, but it still
        occupies a slot so the documents after it keep their own."""
        mock_extract.return_value = {"raw": [], "formatted": ""}
        _node({
            "keys": ["X"],
            "input_sources": ["step_input", "workflow_documents"],
            "doc_texts": ["doc one"],
            "doc_metas": [{"uuid": "u1", "title": "One", "text_markers": []}],
        }).process({"output": "previous step output", "step_name": "Prompt"})

        kwargs = mock_extract.call_args.kwargs
        assert kwargs["doc_texts"] == ["previous step output", "doc one"]
        metas = kwargs["doc_metadata"]
        assert len(metas) == 2
        assert metas[0]["uuid"] is None
        assert metas[0]["text_markers"] == []
        # Tagged, so a quote located inside a previous LLM step's own output
        # cannot be mistaken for evidence from a source document — the check
        # that sets `verified` only asks whether the quote was found in the
        # text it searched, and here that text is the model's own words.
        assert metas[0]["kind"] == "step_input"
        assert metas[1]["uuid"] == "u1"
        assert "kind" not in metas[1]

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_missing_metadata_still_produces_aligned_placeholders(self, mock_extract):
        """An older run (or a hydration path that never attached doc_metas)
        must still extract — the quotes simply resolve to no page."""
        mock_extract.return_value = {"raw": [], "formatted": ""}
        _node({
            "keys": ["X"],
            "input_source": "workflow_documents",
            "doc_texts": ["a", "b"],
        }).process({"output": "prev", "step_name": "SomeStep"})

        metas = mock_extract.call_args.kwargs["doc_metadata"]
        assert len(metas) == 2
        # Documents with no hydrated metadata, not step inputs — the placeholder
        # is bare, with no origin tag.
        assert all(m == {"uuid": None, "title": None, "text_markers": []} for m in metas)


class TestDataExtractionModelForwards:
    @patch("app.services.workflow_engine.ExtractionEngine")
    def test_sources_reach_the_engine(self, mock_engine_cls):
        engine = MagicMock()
        engine.extract.return_value = []
        engine.tokens_in = engine.tokens_out = 0
        mock_engine_cls.return_value = engine

        meta = [{"uuid": "u1", "title": "One", "text_markers": []}]
        data_extraction_model(
            "gpt-4o", ["X"], doc_texts=["text"],
            capture_sources=True, doc_metadata=meta,
        )

        kwargs = engine.extract.call_args.kwargs
        assert kwargs["capture_sources"] is True
        assert kwargs["doc_metadata"] == meta


class TestFormattedOutput:
    def test_source_sidecar_is_not_rendered_as_a_field(self):
        """The sidecar is provenance, not an extracted value — dumping it into
        the step's markdown would put a wall of JSON in the deliverable."""
        formatted = format_extraction_results([{
            "Award Amount": "$4,200,000",
            SOURCE_KEY: {"Award Amount": {"quote": "The award is $4,200,000.", "page": 12}},
        }])
        assert "**Award Amount**: $4,200,000" in formatted
        assert SOURCE_KEY not in formatted
        assert "quote" not in formatted


class TestHydration:
    def test_extraction_tasks_get_document_metadata(self):
        assert "Extraction" in DOC_META_TASKS
        assert "FormFiller" in DOC_META_TASKS

    def test_build_steps_data_attaches_doc_metas_to_extraction(self):
        from app.tasks.workflow_tasks import _build_steps_data

        db = MagicMock()
        db.workflow_step.find_one.return_value = {
            "_id": "s1", "name": "Extract", "tasks": ["t1"],
        }
        db.workflow_step_task.find_one.return_value = {
            "_id": "t1", "name": "Extraction", "data": {"keys": ["X"]},
        }
        db.smart_document.find_one.return_value = {
            "uuid": "d1", "title": "Proposal", "raw_text": "body",
            "text_markers": [{"page": 1, "char_offset": 0}],
        }

        steps_data, _ = _build_steps_data(
            db, {"steps": ["s1"], "input_config": {}}, "wf1", {"doc_uuids": ["d1"]},
        )

        task_data = steps_data[1]["tasks"][0]["data"]
        assert task_data["doc_texts"] == ["body"]
        assert task_data["doc_metas"] == [{
            "uuid": "d1", "title": "Proposal",
            "text_markers": [{"page": 1, "char_offset": 0}],
        }]


class TestSidecarTravelsBesideTheOutput:
    """Every other capture_sources caller pops the sidecar off the entities.

    Left inline it stops the entity being a flat {field: value} map, and three
    things read that shape: approval artifact detection (a dict value drops an
    editable field table to a raw JSON blob), DataExportNode's csv.DictWriter
    (headers from row 0, extrasaction="raise" — so a run where only some
    documents carried quotes raises mid-export), and any downstream LLM step,
    which json-dumps its input into the prompt.
    """

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_entities_stay_flat(self, mock_extract):
        mock_extract.return_value = {
            "raw": [{
                "Award Amount": "$4,200,000",
                SOURCE_KEY: {"Award Amount": {"quote": "The award is $4,200,000."}},
            }],
            "formatted": "",
        }
        out = _node({"keys": ["Award Amount"]}).process(
            {"output": "text", "step_name": "Prompt"},
        )
        entity = out["output"][0]
        assert entity == {"Award Amount": "$4,200,000"}
        assert all(isinstance(v, (str, int, float, type(None))) for v in entity.values())

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_the_sidecar_is_still_carried(self, mock_extract):
        mock_extract.return_value = {
            "raw": [{
                "Award Amount": "$4,200,000",
                SOURCE_KEY: {"Award Amount": {"quote": "The award is $4,200,000."}},
            }],
            "formatted": "",
        }
        out = _node({"keys": ["Award Amount"]}).process(
            {"output": "text", "step_name": "Prompt"},
        )
        assert out["field_sources"][0]["Award Amount"]["quote"] == "The award is $4,200,000."

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_a_run_with_no_quotes_keeps_its_old_shape(self, mock_extract):
        mock_extract.return_value = {"raw": [{"Award Amount": "$1"}], "formatted": ""}
        out = _node({"keys": ["Award Amount"]}).process(
            {"output": "text", "step_name": "Prompt"},
        )
        assert "field_sources" not in out

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_mixed_documents_produce_uniform_rows(self, mock_extract):
        """The CSV case: document 1's reply carried no quotes, document 2's did.
        Both rows must still have identical keys."""
        mock_extract.return_value = {
            "raw": [
                {"Award Amount": "$1"},
                {"Award Amount": "$2", SOURCE_KEY: {"Award Amount": {"quote": "q"}}},
            ],
            "formatted": "",
        }
        out = _node({"keys": ["Award Amount"]}).process(
            {"output": "text", "step_name": "Prompt"},
        )
        rows = out["output"]
        assert set(rows[0]) == set(rows[1])
        assert out["field_sources"] == [{}, {"Award Amount": {"quote": "q"}}]


# ---------------------------------------------------------------------------
# field_sources must stay positional against output through the step wrapper
# ---------------------------------------------------------------------------


class _StubTask:
    """Minimal stand-in for a node: MultiTaskNode only needs `inputs`,
    `process` and `_apply_post_process`."""

    def __init__(self, result):
        self._result = result
        self.inputs = None

    def process(self, _inputs):
        return dict(self._result)

    def _apply_post_process(self, result):
        return result


class TestFieldSourcesStayAlignedWithOutput:
    """`field_sources[i]` holds the quotes for `output[i]` — the contract
    ExtractionNode builds. `collected` takes a slot from every task in the
    step while only an Extraction task contributes a sidecar, so extending by
    the sidecar alone drifted the two lists apart and attributed one task's
    quotes to another task's output."""

    def test_a_task_with_no_sidecar_still_takes_its_slots(self):
        from app.services.workflow_engine import MultiTaskNode

        wrapper = MultiTaskNode("Mixed")
        # A Prompt-style task: one output, no provenance.
        wrapper.add_task(_StubTask({"output": "a prose summary", "step_name": "Mixed"}))
        # An Extraction-style task: two entities, each with its own quotes.
        wrapper.add_task(_StubTask({
            "output": [{"Award": "$1"}, {"Award": "$2"}],
            "field_sources": [
                {"Award": {"quote": "one"}},
                {"Award": {"quote": "two"}},
            ],
            "step_name": "Mixed",
        }))

        out = wrapper.process({"output": "in", "step_name": "Prev"})

        output, sources = out["output"], out["field_sources"]
        assert len(sources) == len(output)
        # Whichever completion order the pool returns them in, every entity
        # still sits beside its own quotes.
        for value, sidecar in zip(output, sources):
            if isinstance(value, dict) and value.get("Award") == "$1":
                assert sidecar == {"Award": {"quote": "one"}}
            elif isinstance(value, dict) and value.get("Award") == "$2":
                assert sidecar == {"Award": {"quote": "two"}}
            else:
                assert sidecar == {}

    def test_no_sidecar_anywhere_omits_the_key(self):
        from app.services.workflow_engine import MultiTaskNode

        wrapper = MultiTaskNode("Prose")
        wrapper.add_task(_StubTask({"output": "just prose", "step_name": "Prose"}))
        out = wrapper.process({"output": "in", "step_name": "Prev"})
        assert "field_sources" not in out
