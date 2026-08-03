"""Tests for per-field extraction source tracking.

Covers the pure resolution logic in ``extraction_sources`` and the engine's
sidecar plumbing (capture, merge, draft, consensus, filtering).
"""

from unittest.mock import MagicMock, patch

from app.services.extraction_engine import ExtractionEngine
from app.services.extraction_sources import (
    SOURCE_KEY,
    find_quote_offset,
    normalize_with_map,
    page_for_offset,
    resolve_entity_sources,
)
from app.tasks.extraction_tasks import normalize_results


# ---------------------------------------------------------------------------
# normalize_with_map / find_quote_offset
# ---------------------------------------------------------------------------

class TestNormalization:
    def test_lowercase_and_whitespace_collapse(self):
        norm, idx_map = normalize_with_map("  Hello\n\n  World  ")
        assert norm == "hello world"
        assert len(idx_map) == len(norm)
        # 'h' maps back to the original 'H'
        assert idx_map[0] == 2

    def test_smart_quotes_and_dashes_fold(self):
        norm, _ = normalize_with_map("“terms” — and ‘conditions’")
        assert norm == '"terms" - and \'conditions\''

    def test_ligature_expansion_keeps_map_aligned(self):
        norm, idx_map = normalize_with_map("eﬀective" if False else "ﬁnal")
        assert norm == "final"
        # both expanded chars map to the ligature's original index
        assert idx_map[0] == idx_map[1] == 0

    def test_exact_match_wins(self):
        doc = "Effective December 31, 2025"
        assert find_quote_offset(doc, "December 31") == 10

    def test_normalized_match(self):
        doc = "the award’s terms—fully"
        assert find_quote_offset(doc, "the award's terms-fully") == 0

    def test_no_match_returns_none(self):
        assert find_quote_offset("some document text", "absent passage") is None
        assert find_quote_offset("", "quote") is None
        assert find_quote_offset("doc", "") is None


# ---------------------------------------------------------------------------
# page_for_offset / resolve_entity_sources
# ---------------------------------------------------------------------------

MARKERS = [
    {"char_offset": 0, "kind": "page", "value": 1},
    {"char_offset": 100, "kind": "page", "value": 2},
    {"char_offset": 200, "kind": "page", "value": 3},
]


class TestPageResolution:
    def test_page_for_offset(self):
        assert page_for_offset(0, MARKERS) == 1
        assert page_for_offset(150, MARKERS) == 2
        assert page_for_offset(500, MARKERS) == 3
        assert page_for_offset(5, []) is None

    def test_non_page_markers_ignored(self):
        markers = [{"char_offset": 0, "kind": "sheet", "value": "Sheet1"}]
        assert page_for_offset(10, markers) is None

    def test_resolve_verified_and_unverified(self):
        doc = "a" * 120 + "Cost sharing is required for this award." + "b" * 60
        entities = [{
            "Cost Sharing": "Yes",
            SOURCE_KEY: {
                "Cost Sharing": {"quote": "Cost sharing is required for this award."},
                "Award Number": {"quote": "not actually in the document"},
            },
        }]
        resolve_entity_sources(entities, doc, {"uuid": "U1", "title": "T&C", "text_markers": MARKERS})
        src = entities[0][SOURCE_KEY]["Cost Sharing"]
        assert src == {
            "quote": "Cost sharing is required for this award.",
            "page": 2,
            "document_uuid": "U1",
            "document_title": "T&C",
            "verified": True,
        }
        missing = entities[0][SOURCE_KEY]["Award Number"]
        assert missing["verified"] is False
        assert missing["page"] is None

    def test_resolve_combined_doc_spans(self):
        doc = "first document text" + "\n\n---\n\n" + "second document text"
        spans = [
            {"start": 0, "end": 19, "uuid": "D1", "title": "One"},
            {"start": 26, "end": 46, "uuid": "D2", "title": "Two"},
        ]
        entities = [{
            "F": "v",
            SOURCE_KEY: {"F": {"quote": "second document"}},
        }]
        resolve_entity_sources(entities, doc, {"uuid": None, "title": None,
                                               "text_markers": [], "doc_spans": spans})
        src = entities[0][SOURCE_KEY]["F"]
        assert src["verified"] is True
        assert src["document_uuid"] == "D2"
        assert src["document_title"] == "Two"


# ---------------------------------------------------------------------------
# Engine sidecar plumbing
# ---------------------------------------------------------------------------

def _engine():
    return ExtractionEngine(system_config_doc={})


class TestEngineSidecarHelpers:
    def test_merge_chunk_results_merges_sidecars(self):
        merged = _engine()._merge_chunk_results([
            {"A": "1", SOURCE_KEY: {"A": {"quote": "qa"}}},
            {"B": "2", SOURCE_KEY: {"B": {"quote": "qb"}}},
        ])
        assert merged == [{"A": "1", "B": "2",
                           SOURCE_KEY: {"A": {"quote": "qa"}, "B": {"quote": "qb"}}}]

    def test_draft_hint_strips_sidecar(self):
        hint = _engine()._build_draft_hint([{"A": "1", SOURCE_KEY: {"A": {"quote": "qa"}}}])
        assert hint == {"A": "1"}

    def test_filter_drops_sidecar_only_entities(self):
        assert _engine()._filter_empty_entities([{SOURCE_KEY: {"A": {"quote": "q"}}}]) == []
        kept = _engine()._filter_empty_entities([{"A": "1", SOURCE_KEY: {"A": {"quote": "q"}}}])
        assert len(kept) == 1

    def test_attach_source_quotes(self):
        entities = [{"A": "1", "B": None}]
        ExtractionEngine._attach_source_quotes(entities, [{"A": " qa ", "B": None, "C": "orphan"}])
        assert entities[0][SOURCE_KEY] == {"A": {"quote": "qa"}}

    def test_backfill_sources_from_draft(self):
        final = [{"A": "1", "B": "2", SOURCE_KEY: {"A": {"quote": "final-a"}}}]
        draft = [{"A": "1", "B": "2", SOURCE_KEY: {"A": {"quote": "draft-a"}, "B": {"quote": "draft-b"}}}]
        ExtractionEngine._backfill_sources(final, draft)
        assert final[0][SOURCE_KEY]["A"] == {"quote": "final-a"}  # final wins
        assert final[0][SOURCE_KEY]["B"] == {"quote": "draft-b"}  # backfilled

    def test_sidecar_for_consensus_takes_agreeing_replicate(self):
        consensus = {"A": "1"}
        norms = [{"A": "2"}, {"A": "1"}, {"A": "1"}]
        fulls = [
            {"A": "2", SOURCE_KEY: {"A": {"quote": "wrong"}}},
            {"A": "1", SOURCE_KEY: {"A": {"quote": "right"}}},
            {"A": "1"},
        ]
        sidecar = ExtractionEngine._sidecar_for_consensus(consensus, norms, fulls)
        assert sidecar == {"A": {"quote": "right"}}


class TestNormalizeResultsSkipsSidecar:
    def test_sidecar_ignored(self):
        results = [{"A": "1", SOURCE_KEY: {"A": {"quote": "q"}}}]
        normalized = normalize_results(results)
        assert normalized == {"A": "1"}


# ---------------------------------------------------------------------------
# End-to-end (mocked LLM): capture_sources through extract()
# ---------------------------------------------------------------------------

def _make_structured_result_with_sources(entities_data, sources_data):
    mock = MagicMock()

    class FakeDump:
        def __init__(self, data):
            self._data = data

        def model_dump(self, by_alias=False):
            return self._data

    class FakeOutput:
        def __init__(self, entities, sources):
            self.entities = [FakeDump(e) for e in entities]
            self.sources = [FakeDump(s) for s in sources]

    mock.output = FakeOutput(entities_data, sources_data)
    usage = MagicMock()
    usage.request_tokens = 10
    usage.response_tokens = 5
    mock.usage.return_value = usage
    return mock


class TestExtractWithCaptureSources:
    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_capture_resolves_page_and_verification(self, mock_get_model, mock_agent_cls):
        doc_text = "x" * 110 + "Effective December 31, 2025." + "y" * 40
        mock_agent = mock_agent_cls.return_value
        mock_agent.run_sync.return_value = _make_structured_result_with_sources(
            [{"Effective Date": "December 31, 2025", "Award Number": "AB-123"}],
            [{"Effective Date": "Effective December 31, 2025.",
              "Award Number": "hallucinated passage"}],
        )

        engine = ExtractionEngine(system_config_doc={})
        results = engine.extract(
            ["Effective Date", "Award Number"],
            doc_texts=[doc_text],
            model="test-model",
            extraction_config_override={"mode": "one_pass",
                                        "one_pass": {"structured": True}},
            capture_sources=True,
            doc_metadata=[{"uuid": "DOC1", "title": "USDA T&C", "text_markers": MARKERS}],
        )

        assert len(results) == 1
        sidecar = results[0][SOURCE_KEY]
        assert sidecar["Effective Date"]["verified"] is True
        assert sidecar["Effective Date"]["page"] == 2
        assert sidecar["Effective Date"]["document_uuid"] == "DOC1"
        assert sidecar["Award Number"]["verified"] is False

        # The system prompt asked for sources
        system_prompt = mock_agent_cls.call_args.kwargs.get("system_prompt", "")
        assert "'sources'" in system_prompt

    @patch("app.services.extraction_engine.Agent")
    @patch("app.services.extraction_engine.get_agent_model")
    def test_no_capture_keeps_prompt_and_results_clean(self, mock_get_model, mock_agent_cls):
        mock_agent = mock_agent_cls.return_value
        mock_agent.run_sync.return_value = _make_structured_result_with_sources(
            [{"A": "1"}], [],
        )
        engine = ExtractionEngine(system_config_doc={})
        results = engine.extract(
            ["A"], doc_texts=["some text"], model="test-model",
            extraction_config_override={"mode": "one_pass",
                                        "one_pass": {"structured": True}},
        )
        assert results == [{"A": "1"}]
        system_prompt = mock_agent_cls.call_args.kwargs.get("system_prompt", "")
        assert "'sources'" not in system_prompt
