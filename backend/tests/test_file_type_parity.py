"""The frontend's file-type list must match the server's.

Every surface that offers a file type — the upload inputs, the document
picker, the folder-watch automation filter — reads one frontend constant, and
the server's ``ALLOWED_EXTS`` is what actually accepts or rejects an upload.
They drifted once: the automation filter offered ``html`` (which no upload can
produce, so the automation could never fire) and omitted ``md`` (which uploads
fine). Asserted from this side because only the backend suite can read both
files — the frontend has no ``@types/node``, so a ``node:fs`` import there
fails the typecheck and the build.
"""

import re
from pathlib import Path

from app.utils.file_validation import ALLOWED_EXTS

_FILE_TYPES_TS = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "fileTypes.ts"
)


def _frontend_supported_extensions() -> set[str]:
    source = _FILE_TYPES_TS.read_text(encoding="utf-8")
    match = re.search(
        r"SUPPORTED_EXTENSIONS\s*=\s*\[([^\]]*)\]", source,
    )
    assert match, f"SUPPORTED_EXTENSIONS not found in {_FILE_TYPES_TS}"
    return {
        part.strip().strip("'\"")
        for part in match.group(1).split(",")
        if part.strip()
    }


def test_frontend_offers_exactly_what_the_server_accepts():
    assert _frontend_supported_extensions() == ALLOWED_EXTS


def test_html_is_offered_by_neither_and_md_by_both():
    frontend = _frontend_supported_extensions()
    assert "html" not in frontend and "html" not in ALLOWED_EXTS
    assert "md" in frontend and "md" in ALLOWED_EXTS
