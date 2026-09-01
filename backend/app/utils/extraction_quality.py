"""Extraction-quality scoring for ingested document text.

A PDF whose embedded fonts defeat text extraction can still yield a large
raw_text — but it is mojibake, and chat over it produces fluent, confidently
wrong answers with no signal to the user that the underlying text is garbage.
The fraction of non-letter characters separates such garbled text layers from
clean extractions by orders of magnitude (clean English-language documents
measure ≤0.01; a CID-mangled text layer measures ~0.5), so it is computed once
at extraction time and stored on the document.
"""

# Punctuation that legitimately appears in clean extracted documents beyond
# letters and digits — including markdown syntax (xlsx/docx extractions are
# markdown-rendered) and common typographic characters.
_EXPECTED_PUNCTUATION = set(".,;:!?'\"()[]{}%$#&*+-–—/\\=<>@_|~^`•·§©®™°…‘’“”")


def nonletter_ratio(text: str) -> float:
    """Fraction of non-whitespace characters that are neither alphanumeric
    (any script) nor common punctuation.

    Returns 0.0 for empty or whitespace-only text — emptiness is a separate,
    already-handled failure and carries no garbling signal.
    """
    considered = 0
    suspicious = 0
    for ch in text:
        if ch.isspace():
            continue
        considered += 1
        if not (ch.isalnum() or ch in _EXPECTED_PUNCTUATION):
            suspicious += 1
    if considered == 0:
        return 0.0
    return suspicious / considered


#: A page of a real sponsored-programs document — even a sparse cover page or a
#: budget table — carries far more than this. The floor is deliberately well
#: below any plausible real page so that crossing it means the OCR gave up, not
#: that the document is terse. ``MIN_PDF_TEXT_LENGTH = 100`` is a whole-document
#: floor, which a 400-page scan yielding 150 characters clears comfortably;
#: this is the per-page equivalent that catches it.
MIN_CHARS_PER_PAGE = 40


def chars_per_page(text: str, num_pages: int | None) -> float | None:
    """Average non-whitespace characters per page, or None when unmeasurable."""
    if not num_pages or num_pages <= 0:
        return None
    return len("".join(text.split())) / num_pages


def is_sparse_extraction(text: str, num_pages: int | None) -> bool:
    """True when a PDF yielded far too little text for its page count.

    The whole-document minimum cannot see this: 150 characters is a complete
    failure spread over 400 pages and a perfectly ordinary result over one.
    """
    density = chars_per_page(text, num_pages)
    return density is not None and density < MIN_CHARS_PER_PAGE
