"""Tests for per-field extraction source tracking.

Covers the pure resolution logic in ``extraction_sources`` and the engine's
sidecar plumbing (capture, merge, draft, consensus, filtering).
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.extraction_engine import ExtractionEngine
from app.services.extraction_sources import (
    SOURCE_KEY,
    _numbers_in,
    find_quote_offset,
    normalize_with_map,
    page_for_offset,
    resolve_entity_sources,
    same_value,
    value_supported_by_quote,
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

# Irregular spacing on purpose: these represent measured boundaries, and
# perfectly uniform offsets are the interpolator's signature — the legacy
# detector in with_marker_provenance would (correctly) hedge a uniform list.
MARKERS = [
    {"char_offset": 0, "kind": "page", "value": 1},
    {"char_offset": 100, "kind": "page", "value": 2},
    {"char_offset": 230, "kind": "page", "value": 3},
]


class TestPageProvenance:
    """An extracted fact's page comes from the same markers KB chat uses, and
    OCR'd documents only have interpolated boundaries — so a source pin that
    reads "p. 4" on a scanned proposal is an estimate presented as a location.
    See #603."""

    def test_marker_is_returned_so_callers_can_read_its_provenance(self):
        from app.services.extraction_sources import page_marker_for_offset

        assert page_marker_for_offset(150, MARKERS) == MARKERS[1]
        assert page_marker_for_offset(5, []) is None

    def test_approximate_flag_survives_resolution(self):
        from app.services.extraction_sources import page_marker_for_offset

        markers = [dict(m, approximate=True) for m in MARKERS]
        marker = page_marker_for_offset(150, markers)
        assert marker is not None and marker["approximate"] is True

    QUOTE = "Cost sharing is required for this award."
    DOC = "a" * 120 + QUOTE + "b" * 60  # quote lands at offset 120 → page 2

    def _resolve(self, markers: list[dict]) -> dict:
        entities = [{
            "Cost Sharing": "Yes",
            SOURCE_KEY: {"Cost Sharing": {"quote": self.QUOTE}},
        }]
        resolve_entity_sources(
            entities, self.DOC,
            {"uuid": "U1", "title": "T&C", "text_markers": markers},
        )
        return entities[0][SOURCE_KEY]["Cost Sharing"]

    def test_sidecar_flags_an_estimated_page(self):
        src = self._resolve([dict(m, approximate=True) for m in MARKERS])
        assert src["page"] == 2
        assert src["page_approximate"] is True

    def test_sidecar_omits_the_flag_for_a_measured_page(self):
        """Measured sources keep the shape they have always had, so stored
        results stay comparable across the change."""
        src = self._resolve(MARKERS)
        assert src["page"] == 2
        assert "page_approximate" not in src


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
            # "Yes" is a judgment about the passage, not a span of it, so the
            # literal check reads it as unsupported. Declaring the field's
            # enum_values (see TestValueSupport) is what marks such fields
            # unassessable instead — without that declaration this field earns
            # the "quote doesn't match" badge, which is the conservative
            # direction but is why enum_values matters on judgment fields.
            "value_supported": False,
            "value_support_method": "no_match",
            "support": "quote_unsupported",
        }
        missing = entities[0][SOURCE_KEY]["Award Number"]
        assert missing["verified"] is False
        assert missing["page"] is None
        assert missing["value_supported"] is None
        assert missing["support"] == "unverified"

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


# ---------------------------------------------------------------------------
# Value support: does the quote actually contain the value it is attached to?
# ---------------------------------------------------------------------------

class TestValueSupport:
    def test_real_quote_does_not_vouch_for_a_hallucinated_value(self):
        """The defect this check exists for.

        A model invents an award amount and returns a genuine sentence from
        the budget section as its supporting passage. The quote verifies —
        it is real document text — and today that alone lights the source
        badge. ``value_supported`` must say False.
        """
        doc_text = "The budget narrative describes personnel and travel costs in detail."
        entities = [{
            "Award Amount": "$500,000",
            SOURCE_KEY: {"Award Amount": {"quote": doc_text}},
        }]
        resolve_entity_sources(entities, doc_text, {})
        src = entities[0][SOURCE_KEY]["Award Amount"]
        assert src["verified"] is True
        assert src["value_supported"] is False
        assert src["value_support_method"] == "no_match"

    def test_literal_value_in_quote_is_supported(self):
        doc_text = "Proposals are due March 1, 2026 at 5:00 PM local time."
        entities = [{
            "Deadline": "March 1, 2026",
            SOURCE_KEY: {"Deadline": {"quote": doc_text}},
        }]
        resolve_entity_sources(entities, doc_text, {})
        src = entities[0][SOURCE_KEY]["Deadline"]
        assert (src["value_supported"], src["value_support_method"]) == (True, "literal")

    def test_currency_formatting_still_counts_as_supported(self):
        doc_text = "Equipment costs total 61,100 in year one."
        entities = [{
            "Equipment": "$61,100",
            SOURCE_KEY: {"Equipment": {"quote": doc_text}},
        }]
        resolve_entity_sources(entities, doc_text, {})
        src = entities[0][SOURCE_KEY]["Equipment"]
        assert (src["value_supported"], src["value_support_method"]) == (True, "numeric")

    def test_reformatted_date_still_counts_as_supported(self):
        doc_text = "Applications close 3/1/2026 without exception."
        entities = [{
            "Deadline": "March 1, 2026",
            SOURCE_KEY: {"Deadline": {"quote": doc_text}},
        }]
        resolve_entity_sources(entities, doc_text, {})
        src = entities[0][SOURCE_KEY]["Deadline"]
        assert (src["value_supported"], src["value_support_method"]) == (True, "date")

    def test_wrong_number_is_not_supported(self):
        doc_text = "Equipment costs total $61,100 in year one."
        entities = [{
            "Equipment": "$16,100",
            SOURCE_KEY: {"Equipment": {"quote": doc_text}},
        }]
        resolve_entity_sources(entities, doc_text, {})
        assert entities[0][SOURCE_KEY]["Equipment"]["value_supported"] is False

    def test_enum_field_is_not_assessed(self):
        """An enum value is a mapping of the prose, not a span of it —
        flagging it would train users to ignore the signal."""
        doc_text = "Cost sharing is required for this competition."
        entities = [{
            "Cost Share": "yes",
            SOURCE_KEY: {"Cost Share": {"quote": doc_text}},
        }]
        resolve_entity_sources(
            entities, doc_text, {}, {"Cost Share": {"enum_values": ["yes", "no"]}},
        )
        src = entities[0][SOURCE_KEY]["Cost Share"]
        assert src["value_supported"] is None
        assert src["value_support_method"] == "enum_field"

    def test_not_found_sentinel_is_not_assessed(self):
        doc_text = "Nothing relevant here at all."
        entities = [{
            "Missing": "N/A",
            SOURCE_KEY: {"Missing": {"quote": doc_text}},
        }]
        resolve_entity_sources(entities, doc_text, {})
        src = entities[0][SOURCE_KEY]["Missing"]
        assert src["value_supported"] is None
        assert src["value_support_method"] == "empty_value"

    def test_unlocated_quote_is_not_assessed(self):
        """A fabricated passage containing the value proves nothing, so the
        value question is not even asked until the quote itself verifies."""
        entities = [{
            "Amount": "$500,000",
            SOURCE_KEY: {"Amount": {"quote": "The award totals $500,000."}},
        }]
        resolve_entity_sources(entities, "Unrelated document text.", {})
        src = entities[0][SOURCE_KEY]["Amount"]
        assert src["verified"] is False
        assert src["value_supported"] is None
        assert src["value_support_method"] == "quote_not_located"

    def test_verified_semantics_are_unchanged(self):
        """Phase 1 records the new signal without redefining the old one."""
        doc_text = "The budget narrative describes personnel costs."
        entities = [{
            "Amount": "$500,000",
            SOURCE_KEY: {"Amount": {"quote": doc_text}},
        }]
        resolve_entity_sources(entities, doc_text, {})
        assert entities[0][SOURCE_KEY]["Amount"]["verified"] is True


class TestBackfillGuard:
    def test_changed_value_does_not_inherit_the_drafts_quote(self):
        """Pass 2 moved the deadline; pass 1's quote supports the old one.

        Copying it would attach a real, verifiable passage that contradicts
        the displayed value — a source badge pointing at evidence against
        itself. The quote is withheld, but an entry is left behind: dropping
        the field entirely renders it unmarked, which is the state that looks
        cleanest, so the least trustworthy value would lose its warning too.
        """
        final = [{"Deadline": "April 1"}]
        draft = [{
            "Deadline": "March 1",
            SOURCE_KEY: {"Deadline": {"quote": "Proposals are due March 1."}},
        }]
        ExtractionEngine._backfill_sources(final, draft)
        entry = final[0][SOURCE_KEY]["Deadline"]
        assert entry["quote"] is None
        assert entry["dropped_reason"] == "value_changed"

    def test_withheld_quote_resolves_to_an_unverified_entry(self):
        """End to end: the withheld entry must survive resolution as a
        present-but-unverified source, which is what makes the UI render
        "no source found" rather than nothing at all."""
        final = [{"Deadline": "April 1"}]
        draft = [{
            "Deadline": "March 1",
            SOURCE_KEY: {"Deadline": {"quote": "Proposals are due March 1."}},
        }]
        ExtractionEngine._backfill_sources(final, draft)
        resolve_entity_sources(final, "Proposals are due March 1.", {})
        entry = final[0][SOURCE_KEY]["Deadline"]
        assert entry["verified"] is False
        assert entry["quote"] is None
        assert entry["value_supported"] is None
        assert entry["value_support_method"] == "value_changed_in_refinement"

    def test_unchanged_value_still_inherits_the_quote(self):
        final = [{"Deadline": "March 1"}]
        draft = [{
            "Deadline": "March 1",
            SOURCE_KEY: {"Deadline": {"quote": "Proposals are due March 1."}},
        }]
        ExtractionEngine._backfill_sources(final, draft)
        assert final[0][SOURCE_KEY]["Deadline"]["quote"] == "Proposals are due March 1."

    def test_reformatted_value_still_inherits_the_quote(self):
        """Formatting-only differences are the same value, not a new one."""
        final = [{"Amount": "61100"}]
        draft = [{
            "Amount": "$61,100",
            SOURCE_KEY: {"Amount": {"quote": "Equipment totals $61,100."}},
        }]
        ExtractionEngine._backfill_sources(final, draft)
        assert final[0][SOURCE_KEY]["Amount"]["quote"] == "Equipment totals $61,100."


class TestSameValue:
    def test_equivalences(self):
        assert same_value("March 1, 2026", "3/1/2026")
        assert same_value("$61,100", "61100")
        assert same_value(" Alice ", "alice")
        assert same_value(None, "N/A")  # both sentinels

    def test_differences(self):
        assert not same_value("March 1", "April 1")
        assert not same_value("$61,100", "$16,100")
        assert not same_value("Alice", "Bob")
        assert not same_value(None, "Alice")  # sentinel vs real value

    def test_non_scalar_value_is_not_assessed(self):
        doc_text = "Personnel include Alice and Bob."
        entities = [{
            "People": ["Alice", "Bob"],
            SOURCE_KEY: {"People": {"quote": doc_text}},
        }]
        resolve_entity_sources(entities, doc_text, {})
        src = entities[0][SOURCE_KEY]["People"]
        assert src["value_supported"] is None
        assert src["value_support_method"] == "non_scalar_value"


class TestLiteralMatchBoundaries:
    """A substring is not a value.

    Every case here returned True before boundaries were required — the
    over-claiming direction, on the field the whole feature exists for.
    """

    @pytest.mark.parametrize("value,quote", [
        ("500000", "The total award is 5000000 dollars over five years."),
        ("1,500,000", "The ceiling is $11,500,000 across all awards."),
        ("$500,000", "The obligated total is $500,000.99 as of today."),
        ("61100", "Account code 561100 covers equipment purchases."),
        ("2026", "See https://grants.gov/opportunity/12026 for details."),
        ("John Smith", "The contact is John Smithson, Director of Research."),
        ("Cole", "Nicole Smith serves as principal investigator."),
        ("Ann", "The award was announced on the agency web site."),
    ])
    def test_fragment_of_a_larger_token_is_not_support(self, value, quote):
        assert value_supported_by_quote(value, quote) == (False, "no_match")

    @pytest.mark.parametrize("value,quote,method", [
        ("$500,000", "The award is $500,000.", "literal"),
        ("500,000", "Totals: $1,500,000 overall and 500,000 in year two.", "literal"),
        ("March 1, 2026", "Proposals are due March 1, 2026 at 5:00 PM.", "literal"),
        ("$61,100", "Equipment costs total 61,100 in year one.", "numeric"),
        ("March 1, 2026", "Applications close 3/1/2026 without exception.", "date"),
        ("Jane Smith", "Contact Jane Smith, Director.", "literal"),
    ])
    def test_real_support_still_counts(self, value, quote, method):
        """Sentence punctuation, a genuine second occurrence, and formatting
        differences must all still resolve as supported."""
        assert value_supported_by_quote(value, quote) == (True, method)


class TestNumberParsing:
    def test_percent_is_a_different_quantity_than_the_bare_number(self):
        assert value_supported_by_quote("$50", "The negotiated F&A rate is 50% of MTDC.") == (
            False, "no_match",
        )

    def test_a_percentage_is_supported_by_its_own_percentage(self):
        assert value_supported_by_quote("26%", "The negotiated rate is 26% of MTDC.") == (
            True, "literal",
        )

    def test_comma_separated_list_is_not_one_number(self):
        """`[\\d,]*` read "1,2,3" as a single 123."""
        assert _numbers_in("Sections 1,2,3 of the policy apply.") == {
            (1.0, False), (2.0, False), (3.0, False),
        }
        assert value_supported_by_quote("123", "Sections 1,2,3 of the policy apply.") == (
            False, "no_match",
        )

    def test_thousands_groups_still_parse(self):
        assert _numbers_in("Equipment totals $61,100 this year.") == {(61100.0, False)}


class TestQuoteLengthCap:
    def test_oversized_quote_is_not_assessed(self):
        """The quote is model-controlled and the date scan backtracks
        quadratically on space-free text; a passage this long is pathological,
        so it is excluded rather than measured."""
        supported, method = value_supported_by_quote("3/1/2026", "May" * 4000)
        assert (supported, method) == (None, "quote_too_long")

    def test_a_normal_passage_is_still_assessed(self):
        quote = "Proposals are due March 1, 2026. " + ("Boilerplate text. " * 50)
        assert value_supported_by_quote("March 1, 2026", quote)[0] is True
