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
persisted before the ``approximate`` flag existed carry no key and read as
exact, which matches the behaviour those documents have today.
"""

from typing import Optional


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
