"""Page locators must not present an estimate as a measurement.

Page markers come from two paths. ``_pymupdf_extract_with_pages`` measures each
boundary from the PDF; ``_interpolate_page_markers`` estimates them by spreading
the known page count evenly across OCR text, because the OCR endpoint returns no
page structure. Everything that shows a page number — KB chat, workflow
citations, extraction sources, the document viewer — reads the same markers, so
the distinction has to survive the whole way out to the user.

See #603.
"""

from app.services.page_locator import format_page, location_meta, locator_for_meta


class TestLocationMeta:
    def test_measured_page_carries_no_approximation_flag(self):
        assert location_meta({"kind": "page", "value": 7}) == {"page": 7}

    def test_interpolated_page_is_flagged(self):
        meta = location_meta({"kind": "page", "value": 7, "approximate": True})
        assert meta == {"page": 7, "page_approximate": True}

    def test_sheet_is_never_a_page(self):
        """XLSX markers describe sheets. A sheet has no page number, and
        `approximate` is meaningless for one."""
        assert location_meta({"kind": "sheet", "value": "Budget"}) == {"sheet": "Budget"}

    def test_no_marker_yields_no_location(self):
        """Web sources and plaintext have no markers at all."""
        assert location_meta({}) == {}

    def test_non_integer_page_is_dropped(self):
        assert location_meta({"kind": "page", "value": None}) == {}

    def test_boolean_is_not_a_page_number(self):
        """bool is an int subclass, so `True` would otherwise render as p. 1."""
        assert location_meta({"kind": "page", "value": True}) == {}


class TestFormatPage:
    def test_measured_page_reads_as_exact(self):
        assert format_page(12, False) == "p. 12"

    def test_interpolated_page_is_visibly_hedged(self):
        assert format_page(12, True) == "p. ~12"

    def test_missing_page_has_no_locator(self):
        assert format_page(None, False) is None

    def test_boolean_is_not_a_page_number(self):
        assert format_page(True, False) is None


class TestLocatorForMeta:
    """The contract between what ingest writes and what the citation renderers
    read. Both sides go through this, so the metadata key cannot drift apart
    unnoticed — which is how an estimated page would quietly read as exact."""

    def test_measured_page(self):
        assert locator_for_meta({"page": 3}) == "p. 3"

    def test_estimated_page_is_hedged(self):
        assert locator_for_meta({"page": 3, "page_approximate": True}) == "p. ~3"

    def test_sheet_when_there_is_no_page(self):
        assert locator_for_meta({"sheet": "Budget"}) == "Budget"

    def test_page_wins_over_sheet(self):
        assert locator_for_meta({"page": 3, "sheet": "Budget"}) == "p. 3"

    def test_nothing_to_cite(self):
        assert locator_for_meta({}) is None
        assert locator_for_meta({"sheet": ""}) is None



# ---------------------------------------------------------------------------
# Chunks that span pages (support ticket: "p. 2" for text footed "Page 3 of 5")
# ---------------------------------------------------------------------------

import json  # noqa: E402

from app.services.page_locator import (  # noqa: E402
    annotate_chunk_pages,
    chunk_page_segments,
    cited_pages,
    format_page_range,
    page_breaks_of,
    span_meta,
)

_MARKERS = [
    {"char_offset": 0, "kind": "page", "value": 1},
    {"char_offset": 100, "kind": "page", "value": 2},
    {"char_offset": 200, "kind": "page", "value": 3},
]


class TestSpanMeta:
    def test_single_page_chunk_keeps_the_old_shape(self):
        assert span_meta(10, 50, _MARKERS) == {"page": 1}
        assert span_meta(100, 50, _MARKERS) == {"page": 2}

    def test_spanning_chunk_records_end_page_and_breaks(self):
        meta = span_meta(150, 120, _MARKERS)  # covers 150..270: pages 2 and 3
        assert meta == {"page": 2, "page_end": 3, "page_breaks": "[[50, 3]]"}
        assert page_breaks_of(meta) == [(50, 3)]

    def test_chunk_across_three_pages(self):
        meta = span_meta(50, 200, _MARKERS)  # 50..250: pages 1, 2, 3
        assert meta["page"] == 1 and meta["page_end"] == 3
        assert json.loads(meta["page_breaks"]) == [[50, 2], [150, 3]]

    def test_approximate_flag_travels(self):
        markers = [dict(m, approximate=True) for m in _MARKERS]
        meta = span_meta(150, 120, markers)
        assert meta["page_approximate"] is True and meta["page_end"] == 3

    def test_sheet_markers_get_no_span_fields(self):
        markers = [{"char_offset": 0, "kind": "sheet", "value": "A"}, {"char_offset": 100, "kind": "sheet", "value": "B"}]
        assert span_meta(50, 100, markers) == {"sheet": "A"}


class TestCitedPages:
    CHUNK = "end of page two about budgets. " * 2 + "PURPLE WOMBAT RECONCILIATION 4471 is described here on page three."
    META = {"page": 2, "page_end": 3, "page_breaks": json.dumps([[62, 3]])}

    def test_segments_split_at_the_break(self):
        segs = chunk_page_segments(self.CHUNK, self.META)
        assert [p for p, _ in segs] == [2, 3]
        assert segs[1][1].startswith("PURPLE WOMBAT")

    def test_query_pins_the_passage_to_its_real_page(self):
        assert cited_pages(self.META, self.CHUNK, "What is PURPLE WOMBAT RECONCILIATION 4471?") == {
            "page": 3, "page_end": None, "page_approximate": False,
        }

    def test_query_matching_the_first_segment(self):
        assert cited_pages(self.META, self.CHUNK, "tell me about budgets")["page"] == 2

    def test_ambiguous_query_gives_the_range(self):
        assert cited_pages(self.META, self.CHUNK, "summarise this") == {
            "page": 2, "page_end": 3, "page_approximate": False,
        }

    def test_single_page_chunk_and_legacy_metadata_unchanged(self):
        assert cited_pages({"page": 5}, "text", "text") == {"page": 5, "page_end": None, "page_approximate": False}
        assert cited_pages({"sheet": "A"}, "text", "text") == {"page": None, "page_end": None, "page_approximate": False}

    def test_annotate_marks_the_break_for_the_model(self):
        out = annotate_chunk_pages(self.CHUNK, self.META)
        assert "\n[p. 3]\nPURPLE WOMBAT" in out
        assert annotate_chunk_pages("plain", {"page": 1}) == "plain"
        approx = annotate_chunk_pages(self.CHUNK, {**self.META, "page_approximate": True})
        assert "[p. ~3]" in approx


class TestFormatPageRange:
    def test_range_single_and_none(self):
        assert format_page_range(2, 3, False) == "p. 2–3"
        assert format_page_range(2, 3, True) == "p. ~2–3"
        assert format_page_range(2, None, False) == "p. 2"
        assert format_page_range(2, 2, False) == "p. 2"
        assert format_page_range(None, 3, False) is None
