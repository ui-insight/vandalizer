"""Contract test for the corpus tools' dependency on backend extraction internals.

`validate_keys.py` deliberately locates answers with the same helpers the
product uses to resolve a citation, so the keys are checked against what
Vandalizer would actually see. That makes five backend symbols — two of them
private — part of this corpus's interface, and a backend rename would otherwise
break the corpus validator in a pull request that never runs corpus CI.

This test imports the corpus's whole backend surface the way `validate_keys.py`
does and smoke-calls the two cheap pure ones. The workflow's paths filter lists
the two backend modules below, so a change to either runs this test.

If this fails, a backend rename broke `validate_keys.py` — update both together.

Run: cd backend && uv run --with pytest pytest \\
       ../benchmarks/corpus/CSU-NSF-001/tools/test_backend_contract.py -q
"""
import sys
from pathlib import Path

# Same insertion as validate_keys.py: tools/ -> repo root is four up.
REPO = Path(__file__).resolve().parents[4]
assert (REPO / "backend").is_dir(), f"backend/ not found under {REPO}"
sys.path.insert(0, str(REPO / "backend"))

import app.services.document_readers as dr  # noqa: E402
from app.services.extraction_sources import (  # noqa: E402
    find_quote_offset,
    normalize_with_map,
    page_for_offset,
)


class TestSymbolsExist:
    """The five names validate_keys.py imports, and nothing else."""

    def test_pymupdf_extract_with_pages_is_importable(self):
        assert callable(dr._pymupdf_extract_with_pages)

    def test_extract_text_with_markers_is_importable(self):
        assert callable(dr.extract_text_with_markers)

    def test_extraction_sources_helpers_are_importable(self):
        assert callable(normalize_with_map)
        assert callable(find_quote_offset)
        assert callable(page_for_offset)


class TestNormalizeWithMap:
    """Shape of the (normalized, index_map) pair validate_keys.py caches per doc."""

    def test_returns_normalized_text_and_an_offset_map(self):
        text = "The  Total   Amount\nRequested"
        normalized, index_map = normalize_with_map(text)

        assert normalized == "the total amount requested"
        assert len(index_map) == len(normalized)
        # The map must project back into the original string, in order.
        assert index_map == sorted(index_map)
        assert text[index_map[0]] == "T"
        assert text[index_map[-1]] == "d"

    def test_a_normalized_hit_projects_back_onto_the_original_text(self):
        text = "Header\n\nTOTAL   requested:  $1,184,398.51"
        normalized, index_map = normalize_with_map(text)

        position = normalized.find("total requested")
        assert position != -1
        assert text[index_map[position]:].startswith("TOTAL")


class TestPageForOffset:
    """Page attribution over a marker list, as _pymupdf_extract_with_pages emits it."""

    MARKERS = [
        {"char_offset": 0, "kind": "page", "value": 1},
        {"char_offset": 10, "kind": "page", "value": 2},
        {"char_offset": 20, "kind": "page", "value": 3},
    ]

    def test_offset_inside_a_page_reports_that_page(self):
        assert page_for_offset(0, self.MARKERS) == 1
        assert page_for_offset(5, self.MARKERS) == 1
        assert page_for_offset(10, self.MARKERS) == 2
        assert page_for_offset(25, self.MARKERS) == 3

    def test_offset_past_the_last_marker_stays_on_the_last_page(self):
        assert page_for_offset(9999, self.MARKERS) == 3

    def test_no_markers_means_no_page(self):
        assert page_for_offset(0, []) is None


class TestFindQuoteOffset:
    """The fallback validate_keys.py uses for answers carrying no figure."""

    def test_locates_a_quote_that_differs_only_in_whitespace_and_case(self):
        text = "Page one.\nThe award is  administered   by the institution."
        offset = find_quote_offset(text, "administered by the institution",
                                   normalize_with_map(text))
        assert offset is not None
        assert text[offset:].startswith("administered")

    def test_returns_none_when_the_quote_is_absent(self):
        text = "Page one. Nothing relevant here."
        assert find_quote_offset(text, "administered by the institution",
                                 normalize_with_map(text)) is None
