"""Find and repair KB URL sources poisoned by site-lockout pages.

When ecfr.gov / federalregister.gov (and similar bot-protected sites) locked
out our scraper, the "Request Access" interstitial was cached into
``KnowledgeBaseSource.content`` and embedded into ChromaDB, so retrieval
returns lockout boilerplate instead of regulation text.

This script scans EVERY url-type source in the database (seeded catalog KBs,
clones, and user-created KBs alike) and repairs the broken ones:

1. URLs covered by the bundled seed content
   (``seeds/knowledge_bases/content/manifest.json``) are rebuilt from the
   bundled text — no network access needed.
2. Other ecfr.gov URLs are rebuilt from text fetched via the official eCFR
   developer API (the sanctioned programmatic access path).
3. Remaining broken URLs are re-fetched through the normal web fetcher, whose
   bot-challenge gate now refuses to ingest lockout pages. Sources that are
   still blocked stay in ``error`` status and are listed in the report.

Usage (run inside the backend container / venv on the target server)::

    cd backend
    python -m scripts.repair_gov_kb_sources --dry-run   # report only
    python -m scripts.repair_gov_kb_sources             # repair
    python -m scripts.repair_gov_kb_sources --no-refetch  # skip step 3

A source counts as broken when its cached content looks like a bot-challenge
page, its status is ``error``, or it has no cached content at all.
"""

import argparse
import asyncio
import json
import logging
import time

import httpx

from app.config import Settings
from app.database import init_db
from app.models.knowledge import KnowledgeBase, KnowledgeBaseSource
from app.utils.bot_challenge import looks_like_bot_challenge
from scripts.fetch_ecfr_text import (
    DEFAULT_OUT_DIR,
    MANIFEST_NAME,
    fetch_text_for_url,
    parse_ecfr_url,
)

logger = logging.getLogger(__name__)

_ECFR_API_DELAY_SECONDS = 2


def _is_broken(source: KnowledgeBaseSource) -> str | None:
    """Return a short reason when the source needs repair, else None."""
    if looks_like_bot_challenge(source.content):
        return "cached bot-challenge page"
    if source.status == "error":
        return f"error status ({(source.error_message or '')[:80]})"
    if not (source.content or "").strip():
        return "no cached content"
    return None


def _load_manifest() -> dict[str, dict]:
    path = DEFAULT_OUT_DIR / MANIFEST_NAME
    if not path.exists():
        logger.warning("Bundled content manifest missing: %s", path)
        return {}
    return json.loads(path.read_text())


async def repair(dry_run: bool, refetch_others: bool) -> None:
    from app.services.document_manager import get_document_manager
    from app.services.knowledge_service import (
        _ingest_url_source,
        ingest_text_into_source,
        recalculate_stats,
    )

    manifest = _load_manifest()
    kbs = {kb.uuid: kb for kb in await KnowledgeBase.find_all().to_list()}
    sources = await KnowledgeBaseSource.find(
        KnowledgeBaseSource.source_type == "url",
    ).to_list()

    broken: list[tuple[KnowledgeBaseSource, str]] = []
    for src in sources:
        reason = _is_broken(src)
        if reason:
            broken.append((src, reason))

    print(f"Scanned {len(sources)} URL sources across {len(kbs)} KBs; "
          f"{len(broken)} need repair.")
    for src, reason in broken:
        kb = kbs.get(src.knowledge_base_uuid)
        kb_title = kb.title if kb else f"<missing KB {src.knowledge_base_uuid}>"
        print(f"  [{kb_title}] {src.url} — {reason}")
    if dry_run or not broken:
        return

    ecfr_cache: dict[str, tuple[str, str] | None] = {}
    touched_kbs: set[str] = set()
    fixed, failed, skipped = 0, [], []

    with httpx.Client(timeout=60) as api_client:
        for src, reason in broken:
            kb = kbs.get(src.knowledge_base_uuid)
            if not kb:
                skipped.append((src, "knowledge base row missing"))
                continue

            text: str | None = None
            label: str | None = None
            entry = manifest.get(src.url or "")
            if entry:
                path = DEFAULT_OUT_DIR / entry["file"]
                if path.exists():
                    text = path.read_text()
                    label = entry.get("title")
            if text is None and src.url and parse_ecfr_url(src.url):
                cached = ecfr_cache.get(src.url)
                if src.url not in ecfr_cache:
                    try:
                        cached = fetch_text_for_url(src.url, client=api_client)
                        time.sleep(_ECFR_API_DELAY_SECONDS)
                    except Exception as e:
                        logger.warning("eCFR API fetch failed for %s: %s", src.url, e)
                        cached = None
                    ecfr_cache[src.url] = cached
                if cached:
                    label, text = cached

            if text is not None:
                ok = await ingest_text_into_source(src, kb, text, label=label)
                if ok:
                    fixed += 1
                    touched_kbs.add(kb.uuid)
                    print(f"  fixed [{kb.title}] {src.url} ({ok} chunks)")
                else:
                    failed.append((src, src.error_message or "ingest failed"))
            elif refetch_others and src.url:
                # _ingest_url_source is a fresh-source path — clear the old
                # (poisoned) chunks first so none survive a smaller refetch.
                await asyncio.to_thread(
                    get_document_manager().delete_kb_source, kb.uuid, src.uuid,
                )
                result = await _ingest_url_source(src, kb)
                if result is not None:
                    fixed += 1
                    touched_kbs.add(kb.uuid)
                    print(f"  refetched [{kb.title}] {src.url}")
                else:
                    failed.append((src, src.error_message or "refetch failed"))
            else:
                skipped.append((src, "no bundled/API text and refetch disabled"))

    for kb_uuid in touched_kbs:
        await recalculate_stats(kbs[kb_uuid])

    print(f"\nRepaired {fixed}/{len(broken)} sources "
          f"({len(touched_kbs)} KBs re-embedded).")
    for src, msg in failed:
        kb = kbs.get(src.knowledge_base_uuid)
        print(f"  STILL BROKEN [{kb.title if kb else '?'}] {src.url} — {msg[:120]}")
    for src, msg in skipped:
        kb = kbs.get(src.knowledge_base_uuid)
        print(f"  SKIPPED [{kb.title if kb else '?'}] {src.url} — {msg}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Report broken sources without changing anything")
    parser.add_argument("--no-refetch", action="store_true",
                        help="Don't re-fetch broken non-eCFR URLs from the live web")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings()
    await init_db(settings)
    await repair(dry_run=args.dry_run, refetch_others=not args.no_refetch)


if __name__ == "__main__":
    asyncio.run(main())
