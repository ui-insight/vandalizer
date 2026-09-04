"""Turn a resolved text marker into citation metadata and a display locator.

Page markers reach consumers from two paths that look identical:
``_pymupdf_extract_with_pages`` measures each boundary from the PDF, while
``_interpolate_page_markers`` estimates them by spreading the known page count
evenly across OCR text (the OCR endpoint returns no page structure). A citation
built on an interpolated offset is a guess, and rendering it as "p. 12" states a
position the data cannot support — the same confident-but-unsupported answer
tracked in #609, on exactly the scanned uploads research admin deals in.

Both helpers live here rather than in each consumer so KB chat, workflow
citations, extraction sources and chunk metadata hedge identically. Markers
persisted before the ``approximate`` flag existed carry no key; consumers run
them through :func:`with_marker_provenance`, which recognizes the
interpolator's uniform-spacing signature and restores the flag, so those
documents hedge instead of rendering a confident ``p. 234`` off a guess.
"""

import json
import re
from typing import Optional


def with_marker_provenance(markers: Optional[list[dict]]) -> Optional[list[dict]]:
    """Restore the ``approximate`` flag on legacy interpolated page markers.

    ``_interpolate_page_markers`` has always placed page N at exactly
    ``N * (len(text) // num_pages)`` — perfectly uniform spacing. Markers it
    persisted before the ``approximate`` flag existed carry that signature but
    no key, and read as exact, so a scanned 400-page package rendered
    confident ``p. 234`` citations off evenly-spread guesses.

    Measured boundaries (PyMuPDF, the local fast path) essentially never
    produce three or more pages of *identical* character length, so uniform
    spacing across >= 3 page markers identifies the interpolator's output.
    The cost of a false positive is only an unnecessary ``~`` hedge; the cost
    of a false negative is invented precision — the asymmetry the threshold
    leans on. Two-page documents are left as they are: one delta proves
    nothing either way.

    Returns a new list with the flag set when the signature matches;
    otherwise the input, untouched.
    """
    pages = [
        m for m in (markers or [])
        if isinstance(m, dict) and m.get("kind") == "page"
    ]
    if len(pages) < 3 or any(m.get("approximate") for m in pages):
        return markers
    offsets = [m.get("char_offset") for m in pages]
    if not all(isinstance(o, int) and not isinstance(o, bool) for o in offsets):
        return markers
    deltas = {b - a for a, b in zip(offsets, offsets[1:])}
    if len(deltas) != 1 or deltas == {0}:
        return markers
    return [
        {**m, "approximate": True}
        if isinstance(m, dict) and m.get("kind") == "page" else m
        for m in markers
    ]


def location_meta(location: dict) -> dict:
    """Chunk metadata for a resolved marker: page, sheet, or nothing.

    ``page_approximate`` is set only when true, so chunks written before this
    existed compare equal to newly-written exact ones.
    """
    kind = location.get("kind")
    value = location.get("value")

    # bool is a subclass of int, so an errant True would otherwise become p. 1.
    if kind == "page" and isinstance(value, int) and not isinstance(value, bool):
        meta: dict = {"page": value}
        if location.get("approximate"):
            meta["page_approximate"] = True
        return meta

    if kind == "sheet" and isinstance(value, str):
        return {"sheet": value}

    return {}


def format_page(page: object, approximate: object) -> Optional[str]:
    """``"p. 12"``, or ``"p. ~12"`` when the boundary was interpolated.

    Returns ``None`` when there is no page to cite, so callers can fall back to
    a sheet name or to the bare source title.
    """
    if not isinstance(page, int) or isinstance(page, bool):
        return None
    return f"p. ~{page}" if approximate else f"p. {page}"


def locator_for_meta(meta: dict) -> Optional[str]:
    """The citation locator for a retrieved chunk: page if it has one, else sheet.

    Both KB chat and workflow citations render ``name + locator``, differing
    only in how they join the two. Routing both through here keeps the metadata
    key that ingest writes and the key the renderers read from drifting apart —
    a drift that would silently turn every estimated page back into an exact
    one, with nothing failing.
    """
    page = format_page(meta.get("page"), meta.get("page_approximate"))
    if page:
        return page
    sheet = meta.get("sheet")
    return sheet if isinstance(sheet, str) and sheet else None


# ---------------------------------------------------------------------------
# Chunks that span pages
# ---------------------------------------------------------------------------
#
# A chunk was tagged with the page it *starts* on, so a passage sitting past a
# page break inside the chunk was cited one page early — worse the fewer chunks
# a document produces (support ticket: "p. 2" for text footed "Page 3 of 5").
# Ingest now also records the page the chunk ends on and where each break
# falls inside it; citation time picks the page of the passage that answers
# the question, or shows the range when that cannot be told.

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{2,}")


def span_meta(offset: int, length: int, markers: list[dict]) -> dict:
    """Chunk metadata for the text at ``[offset, offset + length)``.

    Everything :func:`location_meta` gives for the chunk's start, plus — for a
    chunk that crosses page boundaries — ``page_end`` (the page it ends on)
    and ``page_breaks``, a JSON string of ``[[offset_in_chunk, page], …]``.
    (Chroma metadata holds scalars only, hence the string.) Single-page
    chunks keep exactly the shape they had, so existing collections stay
    comparable. *markers* must be sorted by ``char_offset``.
    """
    start: dict = {}
    breaks: list[list[int]] = []
    end = offset + max(length, 1)
    for m in markers or []:
        if not isinstance(m, dict):
            continue
        at = m.get("char_offset", 0)
        if not isinstance(at, int) or isinstance(at, bool):
            continue
        if at <= offset:
            start = m
        elif at < end:
            if m.get("kind") == "page" and isinstance(m.get("value"), int) and not isinstance(m.get("value"), bool):
                breaks.append([at - offset, m["value"]])
        else:
            break
    meta = location_meta(start)
    if "page" in meta and breaks:
        meta["page_end"] = breaks[-1][1]
        meta["page_breaks"] = json.dumps(breaks)
    return meta


def page_breaks_of(meta: dict) -> list[tuple[int, int]]:
    """``[(offset_in_chunk, page), …]`` from chunk metadata, or ``[]``."""
    raw = meta.get("page_breaks")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    out: list[tuple[int, int]] = []
    for item in raw or []:
        if isinstance(item, (list, tuple)) and len(item) == 2 and all(isinstance(x, int) for x in item):
            out.append((item[0], item[1]))
    return out


def chunk_page_segments(content: str, meta: dict) -> list[tuple[int, str]]:
    """Split a chunk's text at its page breaks: ``[(page, text), …]``."""
    page = meta.get("page")
    if not isinstance(page, int) or isinstance(page, bool):
        return []
    breaks = page_breaks_of(meta)
    if not breaks:
        return [(page, content)]
    segments: list[tuple[int, str]] = []
    prev_off, prev_page = 0, page
    for off, next_page in breaks:
        segments.append((prev_page, content[prev_off:off]))
        prev_off, prev_page = off, next_page
    segments.append((prev_page, content[prev_off:]))
    return segments


def annotate_chunk_pages(content: str, meta: dict) -> str:
    """Insert ``[p. N]`` at each page break inside a chunk so the model can
    see where the page changes and cite the page a passage is actually on."""
    segments = chunk_page_segments(content, meta)
    if len(segments) <= 1:
        return content
    approx = bool(meta.get("page_approximate"))
    parts = [segments[0][1]]
    for page, text in segments[1:]:
        parts.append(f"\n[p. ~{page}]\n" if approx else f"\n[p. {page}]\n")
        parts.append(text)
    return "".join(parts)


def _query_terms(query: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(query or "")}


def cited_pages(meta: dict, content: str, query: str) -> dict:
    """The page(s) to cite for a retrieved chunk.

    Returns ``{"page", "page_end", "page_approximate"}``. A single-page chunk
    cites its page. A chunk spanning pages cites the page of the segment that
    shares the most query terms with the question, when exactly one segment
    does; otherwise ``page``/``page_end`` give the range and the caller shows
    "p. 2–3" rather than guessing.
    """
    page = meta.get("page")
    approximate = bool(meta.get("page_approximate"))
    if not isinstance(page, int) or isinstance(page, bool):
        return {"page": None, "page_end": None, "page_approximate": approximate}
    segments = chunk_page_segments(content, meta)
    if len(segments) <= 1:
        return {"page": page, "page_end": None, "page_approximate": approximate}

    terms = _query_terms(query)
    scored: list[tuple[int, int]] = []
    for seg_page, text in segments:
        seg_terms = _query_terms(text)
        scored.append((len(terms & seg_terms), seg_page))
    best = max(score for score, _ in scored)
    winners = [seg_page for score, seg_page in scored if score == best]
    if best > 0 and len(winners) == 1:
        return {"page": winners[0], "page_end": None, "page_approximate": approximate}
    return {"page": segments[0][0], "page_end": segments[-1][0], "page_approximate": approximate}


def format_page_range(page: object, page_end: object, approximate: object) -> Optional[str]:
    """``"p. 2–3"`` for a span, else :func:`format_page`."""
    single = format_page(page, approximate)
    if single is None:
        return None
    if isinstance(page_end, int) and not isinstance(page_end, bool) and page_end > page:  # type: ignore[operator]
        return f"{single}–{page_end}"
    return single
