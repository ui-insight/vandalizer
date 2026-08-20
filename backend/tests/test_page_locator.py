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
