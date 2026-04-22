"""Version detection and upstream release check.

The running version is baked into the image at build time (see backend/Dockerfile
ARG VERSION) and written to /app/VERSION. At runtime we read that file, then
optionally call the public GitHub Releases API to see whether a newer tag has
been published upstream. The result is cached in Redis for 1 hour so admin UI
polling never hits GitHub directly.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import httpx
import redis.asyncio as aioredis

from app.config import Settings

logger = logging.getLogger(__name__)

GITHUB_RELEASES_LATEST_URL = (
    "https://api.github.com/repos/ui-insight/vandalizer/releases/latest"
)
CACHE_KEY = "vandalizer:update_check:latest_release"
CACHE_TTL_SECONDS = 60 * 60  # 1 hour

# CalVer (vYYYY.MM.N) or SemVer (vMAJOR.MINOR.PATCH).
_VERSION_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def get_current_version() -> str:
    """Return the version baked into this image, or 'dev' if unknown."""
    version_file = Path("/app/VERSION")
    if version_file.exists():
        value = version_file.read_text().strip()
        if value:
            return value
    # Fallback for local development where the file isn't written.
    return "dev"


def _parse_tag(tag: str) -> Optional[tuple[int, int, int]]:
    """Parse vX.Y.Z into a comparable tuple, or None if not a release tag."""
    match = _VERSION_TAG_RE.match(tag)
    if not match:
        return None
    return tuple(int(x) for x in match.groups())  # type: ignore[return-value]


def _is_newer(latest: str, current: str) -> bool:
    """True iff `latest` is a parseable tag strictly greater than `current`.

    Non-release builds (sha-*, dev, branch names) always return False — we can
    surface the latest release in the UI but we never claim an update is
    available against an unparseable current version.
    """
    current_parts = _parse_tag(current)
    latest_parts = _parse_tag(latest)
    if current_parts is None or latest_parts is None:
        return False
    return latest_parts > current_parts


async def _redis_client(settings: Settings) -> aioredis.Redis:
    return aioredis.Redis(host=settings.redis_host, decode_responses=True)


async def _fetch_latest_release() -> Optional[dict[str, Any]]:
    """Call GitHub; return {tag, name, html_url, published_at} or None on error."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                GITHUB_RELEASES_LATEST_URL,
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("Update check failed: %s", exc)
        return None

    tag = data.get("tag_name")
    if not tag:
        return None
    return {
        "tag": tag,
        "name": data.get("name") or tag,
        "html_url": data.get("html_url"),
        "published_at": data.get("published_at"),
    }


async def get_update_status(settings: Settings) -> dict[str, Any]:
    """Return the payload served to the admin UI.

    Shape:
        {
          "current": "v2026.04.1" | "sha-abc1234" | "dev",
          "latest": "v2026.05.2" | None,
          "update_available": bool,
          "released_at": "2026-05-15T..." | None,
          "release_url": "https://github.com/..." | None,
          "check_disabled": bool,
        }
    """
    current = get_current_version()

    if settings.disable_update_check:
        return {
            "current": current,
            "latest": None,
            "update_available": False,
            "released_at": None,
            "release_url": None,
            "check_disabled": True,
        }

    cached: Optional[dict[str, Any]] = None
    redis = await _redis_client(settings)
    try:
        raw = await redis.get(CACHE_KEY)
        if raw:
            cached = json.loads(raw)
    except (aioredis.RedisError, ValueError) as exc:
        logger.debug("Update-check cache read failed: %s", exc)
    finally:
        await redis.aclose()

    if cached is None:
        cached = await _fetch_latest_release()
        if cached is not None:
            try:
                redis = await _redis_client(settings)
                await redis.set(CACHE_KEY, json.dumps(cached), ex=CACHE_TTL_SECONDS)
                await redis.aclose()
            except aioredis.RedisError as exc:
                logger.debug("Update-check cache write failed: %s", exc)

    if cached is None:
        return {
            "current": current,
            "latest": None,
            "update_available": False,
            "released_at": None,
            "release_url": None,
            "check_disabled": False,
        }

    latest_tag = cached["tag"]
    return {
        "current": current,
        "latest": latest_tag,
        "update_available": _is_newer(latest_tag, current),
        "released_at": cached.get("published_at"),
        "release_url": cached.get("html_url"),
        "check_disabled": False,
    }
