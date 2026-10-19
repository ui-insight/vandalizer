"""Regulation text the catalog ships with, by the URL it stands in for.

ecfr.gov serves an automated fetch a page shell, either a "Request Access"
lockout or 434 characters of search-box help, never the regulation. The
catalog therefore bundles the text (fetched once through the official eCFR
API) in ``seeds/knowledge_bases/content`` with a URL-keyed ``manifest.json``.
The seeder ingests it without touching the site, and every in-app fetch of a
bundled URL uses it as well. Before this, Refresh, Refresh all and the
schedule went to the live page and replaced the regulation with the shell
(support ticket: the FCOI KB answered from eCFR's search help for a week).
"""

from __future__ import annotations

import functools
import json
import logging
import pathlib
from typing import Optional

logger = logging.getLogger(__name__)

CONTENT_DIR = (
    pathlib.Path(__file__).resolve().parents[2] / "seeds" / "knowledge_bases" / "content"
)
MANIFEST_NAME = "manifest.json"

# A source whose text is less than this share of its bundle does not hold
# the regulation (a shell, a lockout page, a truncated fetch).
_MIN_SHARE_OF_BUNDLE = 0.5


def _key(url: str) -> str:
    return url.strip().rstrip("/")


@functools.lru_cache(maxsize=1)
def _manifest() -> dict[str, dict]:
    path = CONTENT_DIR / MANIFEST_NAME
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        logger.warning("Bundled source manifest missing: %s", path)
        return {}
    except Exception:
        logger.exception("Bundled source manifest unreadable: %s", path)
        return {}
    return {_key(url): entry for url, entry in raw.items() if isinstance(entry, dict)}


def bundled_source(url: Optional[str]) -> Optional[tuple[str, Optional[str]]]:
    """``(text, title)`` bundled for *url*, or None when nothing is bundled."""
    if not url:
        return None
    entry = _manifest().get(_key(url))
    if not entry or not entry.get("file"):
        return None
    try:
        text = (CONTENT_DIR / entry["file"]).read_text()
    except Exception:
        logger.exception("Bundled text for %s unreadable", url)
        return None
    return (text, entry.get("title")) if text.strip() else None


def falls_short_of_bundle(content: Optional[str], url: Optional[str]) -> bool:
    """True when a source with bundled text holds much less than the bundle:
    it is serving something other than the regulation."""
    bundled = bundled_source(url)
    if not bundled:
        return False
    return len((content or "").strip()) < len(bundled[0].strip()) * _MIN_SHARE_OF_BUNDLE
