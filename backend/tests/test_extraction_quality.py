"""Tests for the extraction-quality metric and its gating threshold.

A PDF with a broken font encoding (CID-mangled text layer) extracts into
mojibake that models will happily "answer" questions about. The non-letter
ratio is the ingest-time signal that separates such text from clean
extractions by orders of magnitude.
"""

from unittest.mock import MagicMock, patch

from app.utils.extraction_quality import nonletter_ratio


def _mojibake(n: int = 2000) -> str:
    # Deterministic symbol soup (math operators, arrows, box drawing) — the
    # kind of glyphs a mangled CID map produces. No real document content.
    return " ".join(
        "".join(chr(0x2190 + (i * 7 + j) % 600) for j in range(6))
        for i in range(n // 7)
    )


class TestNonletterRatio:
    def test_clean_english_prose_is_near_zero(self):
        text = (
            "The project requests $124,530 in Year 1, including 2.5 person-"
            "months of PI effort (12% of total salary). Indirect costs are "
            "computed at 48.5% MTDC per the negotiated rate agreement.\n"
        ) * 50
        assert nonletter_ratio(text) < 0.05

    def test_markdown_table_extraction_is_near_zero(self):
        text = "| Budget line | Year 1 | Year 2 |\n|---|---|---|\n| Salary | $50,000 | $51,500 |\n" * 100
        assert nonletter_ratio(text) < 0.05

    def test_accented_and_non_ascii_letters_are_not_penalized(self):
        text = "Résumé of José Muñoz — naïve façade, Zürich coöperation. " * 50
        assert nonletter_ratio(text) < 0.05

    def test_mojibake_is_far_above_any_clean_document(self):
        assert nonletter_ratio(_mojibake()) > 0.5

    def test_mostly_garbled_with_some_real_text_still_flags(self):
        # The real-world case: headers/footers survive extraction, the body
        # does not. ~70% garbage should land well above a 0.25 threshold.
        text = ("Page 1 of 60 Research Strategy " + _mojibake(300) + "\n") * 40
        assert nonletter_ratio(text) > 0.25

    def test_empty_and_whitespace_only_are_zero(self):
        assert nonletter_ratio("") == 0.0
        assert nonletter_ratio("   \n\t  ") == 0.0


class TestIsExtractionLowQuality:
    def _doc(self, ratio):
        doc = MagicMock()
        doc.extraction_nonletter_ratio = ratio
        return doc

    def test_unmeasured_documents_are_not_flagged(self):
        from app.services.document_service import is_extraction_low_quality
        assert is_extraction_low_quality(self._doc(None)) is False

    def test_clean_ratio_is_not_flagged(self):
        from app.services.document_service import is_extraction_low_quality
        assert is_extraction_low_quality(self._doc(0.01)) is False

    def test_garbled_ratio_is_flagged(self):
        from app.services.document_service import is_extraction_low_quality
        assert is_extraction_low_quality(self._doc(0.51)) is True

    def test_threshold_comes_from_settings(self):
        from app.services import document_service

        with patch.object(document_service, "Settings") as MockSettings:
            MockSettings.return_value.extraction_max_nonletter_ratio = 0.6
            assert document_service.is_extraction_low_quality(self._doc(0.51)) is False
