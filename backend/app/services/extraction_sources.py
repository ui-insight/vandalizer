"""Per-field source tracking for extractions.

The extraction engine asks the LLM for a verbatim supporting passage per
field (stored under ``SOURCE_KEY`` on each entity dict). This module then
verifies each passage against the document text it was extracted from and
resolves the page it appears on via the document's ``text_markers``
(see ``SmartDocument.text_markers`` / ``document_readers.extract_text_with_markers``).

A passage that cannot be located in the document — even after unicode
normalization — is marked ``verified: False``, which the frontend surfaces
as "no source found": both a traceability gap and a hallucination signal.

Pure string/offset logic only; no DB or LLM access, safe to import anywhere.
"""

from typing import Optional

# Reserved sidecar key on entity dicts: {field_name: source dict}. Every
# consumer that iterates entity items must skip it (normalize_results,
# draft hints, consensus votes, chunk merges).
SOURCE_KEY = "_field_sources"

# 1:1-or-expanding character folds applied to both document text and quotes
# before matching. LLM output routinely differs from PDF text layers by
# smart quotes, dash variants, NBSP, and ligatures.
_CHAR_MAP = {
    # curly quotes -> straight
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"',
    # hyphen/dash variants -> "-"
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-", "\u2212": "-",
    # NBSP / figure / thin / narrow no-break space -> " "
    "\u00a0": " ", "\u2007": " ", "\u2009": " ", "\u202f": " ",
    # ligatures
    "\ufb01": "fi", "\ufb02": "fl",
}

# Zero-width / joining characters dropped entirely: soft hyphen, BOM,
# zero-width space / non-joiner / joiner.
_DROP_CHARS = {"\u00ad", "\ufeff", "\u200b", "\u200c", "\u200d"}


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercase + fold + whitespace-collapse *text*.

    Returns ``(normalized, index_map)`` where ``index_map[i]`` is the offset
    in the original text of the character that produced ``normalized[i]``,
    so matches in normalized space can be projected back to real offsets.
    """
    out: list[str] = []
    index_map: list[int] = []
    last_was_space = True  # trims leading whitespace
    for i, ch in enumerate(text):
        if ch in _DROP_CHARS:
            continue
        folded = _CHAR_MAP.get(ch, ch)
        for c in folded:
            if c.isspace():
                if last_was_space:
                    continue
                out.append(" ")
                index_map.append(i)
                last_was_space = True
            else:
                out.append(c.lower())
                index_map.append(i)
                last_was_space = False
    if out and out[-1] == " ":
        out.pop()
        index_map.pop()
    return "".join(out), index_map


def find_quote_offset(doc_text: str, quote: str,
                      normalized: tuple[str, list[int]] | None = None) -> Optional[int]:
    """Locate *quote* in *doc_text*, returning the original char offset.

    Tries an exact match first, then a normalized match. Pass a pre-built
    ``normalize_with_map(doc_text)`` result via *normalized* to amortize the
    normalization cost across many quotes in the same document.
    """
    if not doc_text or not quote:
        return None
    idx = doc_text.find(quote)
    if idx != -1:
        return idx

    norm_doc, index_map = normalized if normalized is not None else normalize_with_map(doc_text)
    norm_quote, _ = normalize_with_map(quote)
    if not norm_quote:
        return None
    nidx = norm_doc.find(norm_quote)
    if nidx == -1:
        return None
    return index_map[nidx]


def page_for_offset(offset: int, markers: list[dict]) -> Optional[int]:
    """Page number of the most recent ``kind: "page"`` marker at or before *offset*."""
    page: Optional[int] = None
    for m in markers or []:
        if m.get("char_offset", 0) > offset:
            break
        if m.get("kind") == "page":
            value = m.get("value")
            if isinstance(value, int):
                page = value
    return page


def _doc_for_offset(offset: int, doc_spans: list[dict]) -> Optional[dict]:
    for span in doc_spans or []:
        if span.get("start", 0) <= offset < span.get("end", 0):
            return span
    return None


def resolve_entity_sources(entities: list, doc_text: str, doc_meta: dict) -> None:
    """Verify and locate each entity's raw source quotes, in place.

    The engine attaches ``entity[SOURCE_KEY] = {field: {"quote": str}}``.
    This fills each entry out to::

        {"quote", "page", "document_uuid", "document_title", "verified"}

    *doc_meta* carries ``uuid``, ``title``, ``text_markers``, and (for
    combined-context runs over a merged text) optional ``doc_spans`` —
    ``[{"start", "end", "uuid", "title"}]`` — used to attribute an offset to
    the document that contributed it.
    """
    markers = doc_meta.get("text_markers") or []
    doc_spans = doc_meta.get("doc_spans") or []
    normalized = normalize_with_map(doc_text) if doc_text else ("", [])

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        sidecar = entity.get(SOURCE_KEY)
        if not isinstance(sidecar, dict):
            continue
        for field, src in list(sidecar.items()):
            quote = src.get("quote") if isinstance(src, dict) else None
            if isinstance(quote, str):
                quote = quote.strip() or None
            offset = find_quote_offset(doc_text, quote, normalized) if quote else None
            doc_uuid = doc_meta.get("uuid")
            doc_title = doc_meta.get("title")
            if offset is not None and doc_spans:
                span = _doc_for_offset(offset, doc_spans)
                if span:
                    doc_uuid = span.get("uuid")
                    doc_title = span.get("title")
            sidecar[field] = {
                "quote": quote,
                "page": page_for_offset(offset, markers) if offset is not None else None,
                "document_uuid": doc_uuid,
                "document_title": doc_title,
                "verified": offset is not None,
            }
