"""Exact page markers from an OCR service's ``<!-- page N -->`` boundaries."""

from app.services.document_readers import split_ocr_page_markers


def test_markers_parsed_and_stripped():
    text = "<!-- page 1 -->\n\nFirst page.\n\n<!-- page 2 -->\n\nSecond page."
    clean, markers = split_ocr_page_markers(text)
    assert "<!--" not in clean
    assert [m["value"] for m in markers] == [1, 2]
    assert all(m["kind"] == "page" and "approximate" not in m for m in markers)
    assert clean[markers[0]["char_offset"]:].startswith("First page.")
    assert clean[markers[1]["char_offset"]:].startswith("Second page.")


def test_no_markers_returns_none():
    text = "Plain OCR text with no boundaries."
    assert split_ocr_page_markers(text) == (text, None)


def test_blank_pages_keep_numbering():
    text = "<!-- page 1 -->\n\nA\n\n<!-- page 2 -->\n\n<!-- page 3 -->\n\nC"
    clean, markers = split_ocr_page_markers(text)
    assert [m["value"] for m in markers] == [1, 2, 3]
    assert clean[markers[2]["char_offset"]:].startswith("C")


def test_trailing_blank_page_clamped_into_text():
    clean, markers = split_ocr_page_markers("<!-- page 1 -->\n\nA\n\n<!-- page 2 -->\n\n")
    assert all(0 <= m["char_offset"] < len(clean) for m in markers)


def test_inline_comment_text_is_not_a_marker():
    text = "Body mentions &lt;!-- page 9 --&gt; literally."
    assert split_ocr_page_markers(text) == (text, None)
