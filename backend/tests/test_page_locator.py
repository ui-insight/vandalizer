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


class TestWithMarkerProvenance:
    """Markers interpolated before the `approximate` flag existed carry no key
    and read as exact, so a legacy scanned 400-pager rendered confident
    "p. 234" off evenly-spread guesses. The interpolator has always placed
    page N at exactly N * (len(text) // num_pages), so uniform spacing across
    three or more page markers is its signature.
    """

    def _interpolated_legacy(self, n=5, step=100):
        return [
            {"char_offset": i * step, "kind": "page", "value": i + 1}
            for i in range(n)
        ]

    def test_legacy_uniform_markers_are_flagged_approximate(self):
        from app.services.page_locator import with_marker_provenance

        out = with_marker_provenance(self._interpolated_legacy())
        assert all(m["approximate"] is True for m in out)
        # Everything else about the markers is preserved.
        assert [m["value"] for m in out] == [1, 2, 3, 4, 5]
        assert [m["char_offset"] for m in out] == [0, 100, 200, 300, 400]

    def test_measured_markers_are_left_exact(self):
        from app.services.page_locator import with_marker_provenance

        measured = [
            {"char_offset": 0, "kind": "page", "value": 1},
            {"char_offset": 1893, "kind": "page", "value": 2},
            {"char_offset": 3121, "kind": "page", "value": 3},
        ]
        out = with_marker_provenance(measured)
        assert out is measured
        assert not any(m.get("approximate") for m in out)

    def test_already_flagged_markers_pass_through(self):
        from app.services.page_locator import with_marker_provenance

        flagged = [
            {"char_offset": i * 100, "kind": "page", "value": i + 1, "approximate": True}
            for i in range(5)
        ]
        assert with_marker_provenance(flagged) is flagged

    def test_two_pages_prove_nothing_and_stay_exact(self):
        from app.services.page_locator import with_marker_provenance

        two = self._interpolated_legacy(n=2)
        assert with_marker_provenance(two) is two

    def test_sheet_markers_and_none_are_untouched(self):
        from app.services.page_locator import with_marker_provenance

        sheets = [{"char_offset": 0, "kind": "sheet", "value": "Budget"}]
        assert with_marker_provenance(sheets) is sheets
        assert with_marker_provenance(None) is None

    def test_mixed_list_flags_only_the_page_markers(self):
        from app.services.page_locator import with_marker_provenance

        mixed = self._interpolated_legacy() + [
            {"char_offset": 50, "kind": "sheet", "value": "Notes"},
        ]
        out = with_marker_provenance(mixed)
        assert all(m.get("approximate") for m in out if m["kind"] == "page")
        assert not any(m.get("approximate") for m in out if m["kind"] == "sheet")


class TestProvenanceReachesTheMissedSurfaces:
    """The review found two production surfaces consuming stored markers
    without the legacy normalization: the combined-context merge (which
    destroys the uniform-spacing signature before the one wrapped consumer
    ever sees the list) and form-fill attribution reports.
    """

    def _legacy_markers(self, n=5, step=100):
        return [
            {"char_offset": i * step, "kind": "page", "value": i + 1}
            for i in range(n)
        ]

    def test_combined_context_merge_normalizes_per_document_before_shifting(self):
        """Merged offsets have irregular deltas (the inter-doc separator), so
        detection after the merge is impossible; it must happen per doc. And
        one modern doc's flagged markers must not exempt a legacy sibling's
        via the any(approximate) early-return."""
        from app.services.search_set_service import merge_combined_context

        legacy_doc = "x" * 500
        modern_doc = "y" * 400
        merged_text, meta = merge_combined_context(
            [legacy_doc, modern_doc],
            [
                {"uuid": "L", "title": "Legacy scan", "text_markers": self._legacy_markers()},
                {"uuid": "M", "title": "Modern", "text_markers": [
                    {"char_offset": 0, "kind": "page", "value": 1, "approximate": True},
                    {"char_offset": 137, "kind": "page", "value": 2, "approximate": True},
                    {"char_offset": 305, "kind": "page", "value": 3, "approximate": True},
                ]},
            ],
        )
        assert "x" in merged_text and "y" in merged_text
        legacy_merged = [m for m in meta["text_markers"] if m["char_offset"] < 500]
        assert len(legacy_merged) == 5
        assert all(m.get("approximate") is True for m in legacy_merged)
        # Spans still attribute offsets to the right document.
        assert meta["doc_spans"][0]["uuid"] == "L"
        assert meta["doc_spans"][1]["uuid"] == "M"

    def test_form_fill_report_hedges_legacy_interpolated_pages(self):
        from app.services.form_fill import resolve_fill

        report = resolve_fill(
            {"total": "485,000"},
            [{
                "uuid": "d1", "title": "Legacy scan",
                "text": "x" * 150 + " total 485,000 appears here " + "x" * 300,
                "text_markers": self._legacy_markers(),
            }],
        )
        entry = next(e for e in report if e["name"] == "total")
        assert entry["status"] == "supported"
        assert entry["page"] == 2
        assert entry.get("page_approximate") is True
