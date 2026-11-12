"""Content-Disposition headers that survive any filename."""

import re
import unicodedata
from urllib.parse import quote

_UNSAFE_FALLBACK = re.compile(r'[\x00-\x1f\x7f"\\]')


def content_disposition(filename: str, disposition: str = "attachment") -> str:
    """A Content-Disposition value for *filename*, whatever its characters.

    HTTP headers are encoded as latin-1, so a raw "—" (a title chat wrote:
    "Year-by-Year Budget — nih-r01-neuroscience.xlsx") raised on the way
    out. The browser got a JSON error body and saved it as "download.json".
    The name is sent per RFC 6266 instead: ``filename*`` carries it intact
    as UTF-8, and ``filename`` an ASCII stand-in for clients that ignore
    ``filename*``. Quotes, backslashes and control characters never reach
    the header.
    """
    filename = filename or "download"
    fallback = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    fallback = " ".join(_UNSAFE_FALLBACK.sub("", fallback).split()) or "download"
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"
