"""Detect and remove text a PDF renders invisibly.

A PDF's text layer and what a human sees on the page are two different
things. Text drawn in render mode 3 (never painted), in white on white, or
at a sub-point font size is in the file — and therefore in everything we
extract — while being absent from the page the user read before uploading
it. That gap is the whole mechanism behind a document-borne prompt
injection: the notice of award shows ``Total Award Amount: 485,000 USD``,
the text layer also carries ``the official total is $1``, and every model
downstream (chat, extraction, Deep Analysis) reads the second one as part
of the document and reports it as the document's own figure.

The defense is to never let hidden text into the extracted text at all, no
matter which reader produced it — the local Markdown fast path, the OCR
service, or PyMuPDF. ``scrub_pdf`` takes the text a reader returned, finds
what the PDF hides, and removes those fragments from it.

Two deliberate limits:

* A page whose text is *entirely* invisible is left alone. That is the
  shape of a scanned page with an OCR text layer under the image — the
  standard, legitimate use of render mode 3 — and stripping it would erase
  the page's whole content.
* A hidden fragment that also appears in the page's visible text is kept.
  Tagged PDFs and accessibility duplicates repeat visible text invisibly;
  removing those occurrences would delete the visible copy too.
"""

import logging
import re


class HiddenTextInspectionError(RuntimeError):
    """The hidden-text inspection itself failed (reader crash, odd PDF).

    Distinct from "inspected and found nothing": a caller that treats the
    two the same silently disables the prompt-injection defense.
    """

logger = logging.getLogger(__name__)

# Below this, text is unreadable at any zoom the viewer offers.
_MIN_VISIBLE_FONT_SIZE = 1.0

# Shorter fragments carry no instruction and risk matching ordinary prose.
_MIN_FRAGMENT_CHARS = 8

# Fill colors this close to white count as "white" for the on-white test.
_WHITE_RGB = 0xFFFFFF
_NEAR_WHITE_CHANNEL = 0xF0

# Characters a Markdown reader may sprinkle between words of the same span
# (**bold**, _emphasis_), tolerated when matching a fragment back in text.
_FRAGMENT_GAP = r"[\s*_~`]*"


def _is_near_white(color: int) -> bool:
    r, g, b = (color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF
    return min(r, g, b) >= _NEAR_WHITE_CHANNEL


def _normalize(text: str) -> str:
    return " ".join((text or "").split())


def _page_backdrops(page, blocks: list[dict]) -> list:
    """Rects that give white text something to show up against.

    White is only a hiding trick when the page behind the text is also
    white. White-on-color is ordinary design — a banner heading, a table
    header row — and its text must survive.
    """
    import pymupdf

    backdrops = []
    for block in blocks:
        # An image block: white text over a photo or a logo is visible.
        if block.get("type") == 1:
            backdrops.append(pymupdf.Rect(block["bbox"]))
    try:
        drawings = page.get_drawings()
    except Exception as e:  # pragma: no cover - malformed content streams
        logger.debug("Could not read drawings on page: %s", e)
        return backdrops
    for drawing in drawings:
        fill = drawing.get("fill")
        if not fill:
            continue
        # fill channels are 0..1 floats
        if min(fill[:3]) >= _NEAR_WHITE_CHANNEL / 0xFF:
            continue
        backdrops.append(pymupdf.Rect(drawing["rect"]))
    return backdrops


def _span_is_unpainted(span: dict) -> bool:
    """True for text the page never shows regardless of what is behind it."""
    # Render mode 3 / fully transparent fill — drawn, never painted.
    if span.get("alpha", 255) == 0:
        return True
    return float(span.get("size") or 0) < _MIN_VISIBLE_FONT_SIZE


def hidden_text_fragments(pdf_path: str) -> list[str]:
    """Normalized text fragments *pdf_path* renders invisibly.

    Raises :class:`HiddenTextInspectionError` for a PDF it cannot inspect —
    "no hidden text" and "could not look" must be distinct answers, or a
    reader crash silently disables the scrub (see #811). ``scrub_pdf`` is the
    catcher: it passes the text through unchanged and reports the failure.
    """
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - pymupdf is a hard dependency
        return []

    hidden: list[str] = []
    visible: list[str] = []
    try:
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                blocks = page.get_text("dict").get("blocks") or []
                spans = [
                    span
                    for block in blocks
                    for line in block.get("lines", [])
                    for span in line.get("spans", [])
                ]
                backdrops = None
                page_hidden: list[str] = []
                page_visible: list[str] = []
                for span in spans:
                    text = _normalize(span.get("text", ""))
                    if not text:
                        continue
                    if _span_is_unpainted(span):
                        page_hidden.append(text)
                        continue
                    if _is_near_white(int(span.get("color") or 0)):
                        # White only hides on white — read the page's fills
                        # (the expensive part) just for these spans.
                        if backdrops is None:
                            backdrops = _page_backdrops(page, blocks)
                        bbox = pymupdf.Rect(span["bbox"])
                        if not any(r.intersects(bbox) for r in backdrops):
                            page_hidden.append(text)
                            continue
                    page_visible.append(text)
                if not page_visible:
                    # Scanned page with an OCR text layer under the image:
                    # invisible by design, and all the content there is.
                    continue
                hidden.extend(page_hidden)
                visible.extend(page_visible)
    except Exception as e:
        # Raised, not swallowed: returning [] here was indistinguishable from
        # "inspected and clean", which silently disabled this module's whole
        # purpose — the unscrubbed text, hidden content included, flowed
        # straight through to chat, extraction and Deep Analysis.
        raise HiddenTextInspectionError(
            f"Hidden-text inspection failed for {pdf_path}: {e}"
        ) from e

    visible_blob = " ".join(visible)
    fragments: list[str] = []
    for fragment in hidden:
        if len(fragment) < _MIN_FRAGMENT_CHARS:
            continue
        if fragment in visible_blob or fragment in fragments:
            continue
        fragments.append(fragment)
    return fragments


def _fragment_pattern(fragment: str) -> re.Pattern:
    """Match *fragment* across the line breaks and Markdown a reader adds."""
    tokens = [re.escape(t) for t in fragment.split(" ") if t]
    return re.compile(_FRAGMENT_GAP.join(tokens))


def _merge(cuts: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(cuts):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _widen_to_emptied_lines(text: str, cuts: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Extend each cut over its whole line when nothing readable survives.

    Removing a fragment usually empties the line it sat on; leaving the
    blank behind would push a stray empty line into every chunk and
    citation offset downstream.
    """
    widened: list[tuple[int, int]] = []
    i = 0
    while i < len(cuts):
        line_start = text.rfind("\n", 0, cuts[i][0]) + 1
        line_end = text.find("\n", cuts[i][1])
        if line_end == -1:
            line_end = len(text)

        # Every cut that starts within this line is judged together: the line
        # survives only if something readable is left after all of them.
        group: list[tuple[int, int]] = []
        while i < len(cuts) and cuts[i][0] < line_end:
            group.append(cuts[i])
            i += 1

        kept: list[str] = []
        cursor = line_start
        for start, end in group:
            kept.append(text[cursor:max(cursor, start)])
            cursor = max(cursor, end)
        kept.append(text[min(cursor, line_end):line_end])

        # Markdown punctuation left stranded by a cut (an orphaned ``**``, a
        # table row's pipes) is not content — a line needs a word to survive.
        if re.search(r"\w", "".join(kept)):
            widened.extend(group)
        else:
            # Take the line's newline with it, unless it is the last line.
            widened.append((line_start, min(line_end + 1, len(text))))
    return _merge(widened)


def scrub(
    text: str, fragments: list[str], markers: list[dict] | None = None
) -> tuple[str, list[dict]]:
    """Remove *fragments* from *text*, keeping ``markers`` pointing at the
    same content.

    Markers carry char offsets into the text (page boundaries, for
    citations), so every offset past a removal has to shift back by what was
    removed before it.
    """
    markers = markers or []
    if not text or not fragments:
        return text, markers

    cuts: list[tuple[int, int]] = []
    # Longest first: a fragment contained in another must not cut it in half.
    for fragment in sorted(fragments, key=len, reverse=True):
        for match in _fragment_pattern(fragment).finditer(text):
            # Take the Markdown wrapping with it, so removing the text of a
            # **bolded** fragment doesn't strand its asterisks.
            start, end = match.start(), match.end()
            while start > 0 and text[start - 1] in "*_~`":
                start -= 1
            while end < len(text) and text[end] in "*_~`":
                end += 1
            cuts.append((start, end))
    if not cuts:
        return text, markers
    cuts = _widen_to_emptied_lines(text, _merge(cuts))

    parts: list[str] = []
    cursor = 0
    for start, end in cuts:
        parts.append(text[cursor:start])
        cursor = end
    parts.append(text[cursor:])
    scrubbed = "".join(parts)

    adjusted: list[dict] = []
    for marker in markers:
        offset = marker.get("char_offset", 0)
        removed = sum(
            min(end, offset) - start for start, end in cuts if start < offset
        )
        adjusted.append({**marker, "char_offset": max(0, offset - removed)})
    return scrubbed, adjusted


def scrub_pdf(
    pdf_path: str, text: str, markers: list[dict] | None = None,
    report: dict | None = None,
) -> tuple[str, list[dict]]:
    """Strip whatever *pdf_path* hides from the text a reader extracted.

    When the inspection itself fails, the text is returned unchanged — a
    reader hiccup must not fail every odd-but-honest PDF — but the failure
    is recorded in *report* as ``{"hidden_text_unchecked": True}`` so the
    ingestion layer can mark the document instead of silently shipping text
    the defense never looked at.
    """
    markers = markers or []
    if not text:
        return text, markers
    try:
        fragments = hidden_text_fragments(pdf_path)
    except HiddenTextInspectionError as e:
        logger.warning("%s — text passed through UNSCRUBBED", e)
        if report is not None:
            report["hidden_text_unchecked"] = True
        return text, markers
    if not fragments:
        return text, markers
    scrubbed, adjusted = scrub(text, fragments, markers)
    if scrubbed != text:
        logger.warning(
            "Removed %d hidden text fragment(s) from %s (%d chars); first: %r",
            len(fragments), pdf_path, len(text) - len(scrubbed), fragments[0][:120],
        )
    return scrubbed, adjusted
