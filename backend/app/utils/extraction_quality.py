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
