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
   developer API (the sanctioned programmatic access path). Chapter-level
   URLs (e.g. 48 CFR chapter 99), which the API can't serve in one call and
   which would overflow the cached-content cap as a single source, are split
   into one source per non-reserved part.
3. Remaining broken URLs are re-fetched through the normal web fetcher, whose
   bot-challenge gate now refuses to ingest lockout pages. Sources that are
   still blocked stay in ``error`` status and are listed in the report,
   grouped by failure kind (infrastructure / bot-blocked / dead link) so it's
   clear which need an environment fix versus a replacement URL.

Before repairing anything, the script probes the vector store with a test
write and aborts if it's read-only — a broken ChromaDB volume would otherwise
fail every repair one by one.

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
    fetch_parts_for_chapter_url,
    fetch_text_for_url,
    parse_ecfr_chapter_url,
    parse_ecfr_url,
)

logger = logging.getLogger(__name__)

_ECFR_API_DELAY_SECONDS = 2

# Mirror of the truncation in knowledge_service: source.content is capped at
# 500k chars while the ChromaDB chunks carry the full text. kb_reingest
# rebuilds chunks FROM the cached content, so text over the cap silently loses
# its tail on the next reingest — worth a loud warning at repair time.
_CONTENT_CAP = 500_000

# Ordered: first matching bucket wins, so infra errors (which can mention an
# HTTP step) aren't misfiled as dead links.
_FAILURE_BUCKETS: list[tuple[str, tuple[str, ...]]] = [
    ("infrastructure errors (fix the environment, then rerun)",
     ("readonly database", "read-only", "chroma", "no space left")),
    ("bot-blocked (the site refuses automated access)",
     ("bot protection", "bot-challenge", "403")),
    ("dead links (the page is gone — the source needs a replacement URL)",
     ("404", "cannot resolve hostname", "did not respond", "timed out")),
]


def _classify_failure(msg: str | None) -> str:
    lowered = (msg or "").lower()
    for bucket, needles in _FAILURE_BUCKETS:
        if any(n in lowered for n in needles):
            return bucket
    return "other"


def _warn_if_near_cap(text: str, url: str | None) -> None:
    if len(text) > _CONTENT_CAP:
        print(f"  WARNING {url}: {len(text):,} chars exceeds the {_CONTENT_CAP:,}-char "
              "cached-content cap — chunks are complete, but a reingest from the "
              "cached copy would lose the tail")
    elif len(text) > _CONTENT_CAP * 0.9:
        print(f"  WARNING {url}: {len(text):,} chars is within 10% of the "
              f"{_CONTENT_CAP:,}-char cached-content cap")


def _vector_store_write_error() -> str | None:
    """Probe ChromaDB with a create+delete; return the error text if writes fail."""
    from app.services.document_manager import get_document_manager

    client = get_document_manager().client
    probe = "vandalizer-repair-writecheck"
    try:
        client.get_or_create_collection(probe)
        client.delete_collection(probe)
        return None
    except Exception as e:  # noqa: BLE001 — any failure means "don't start"
        return f"{type(e).__name__}: {e}"


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


async def _split_chapter_source(
    src: KnowledgeBaseSource, kb: "KnowledgeBase", api_client: httpx.Client,
) -> bool:
    """Replace a chapter-level eCFR source with one source per part.

    A whole chapter (e.g. 48 CFR ch. 99 at ~634k chars) exceeds the
    cached-content cap as a single source, so mirror the seed pattern of one
    source per division. The original source is only deleted once every part
    has ingested; on partial failure it keeps its error status and a rerun
    finds the already-created part sources by URL and retries the rest.
    Returns True when the chapter was fully split.
    """
    from app.services.document_manager import get_document_manager
    from app.services.knowledge_service import ingest_text_into_source

    try:
        fetched = fetch_parts_for_chapter_url(
            src.url, client=api_client, delay_seconds=_ECFR_API_DELAY_SECONDS,
        )
    except Exception as e:
        logger.warning("eCFR chapter fetch failed for %s: %s", src.url, e)
        src.error_message = f"eCFR chapter fetch failed: {e}"[:2000]
        await src.save()
        return False
    if not fetched or not fetched[1]:
        src.error_message = "eCFR chapter has no fetchable parts"
        await src.save()
        return False
    chapter_label, parts = fetched

    ingested = 0
    for entry in parts:
        part_src = await KnowledgeBaseSource.find_one(
            KnowledgeBaseSource.knowledge_base_uuid == kb.uuid,
            KnowledgeBaseSource.url == entry["url"],
        )
        if part_src is None:
            part_src = KnowledgeBaseSource(
                knowledge_base_uuid=kb.uuid,
                source_type="url",
                url=entry["url"],
                source_reference=entry["url"],
            )
            await part_src.insert()
        _warn_if_near_cap(entry["text"], entry["url"])
        chunks = await ingest_text_into_source(part_src, kb, entry["text"], label=entry["label"])
        if chunks:
            ingested += 1
            print(f"    + [{kb.title}] {entry['url']} ({chunks} chunks)")

    if ingested < len(parts):
        src.error_message = f"chapter split incomplete: {ingested}/{len(parts)} parts ingested"
        await src.save()
        return False

    await asyncio.to_thread(get_document_manager().delete_kb_source, kb.uuid, src.uuid)
    await src.delete()
    print(f"  split [{kb.title}] {src.url} — {chapter_label} → {ingested} part sources")
    return True


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

    write_error = await asyncio.to_thread(_vector_store_write_error)
    if write_error:
        print("\nABORTING: the vector store rejected a test write, so every repair would fail.")
        print(f"  {write_error}")
        print("  Fix the ChromaDB volume (permissions / disk space), then rerun.")
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

            if text is None and src.url and parse_ecfr_chapter_url(src.url):
                if await _split_chapter_source(src, kb, api_client):
                    fixed += 1
                    touched_kbs.add(kb.uuid)
                else:
                    failed.append((src, src.error_message or "chapter split failed"))
                continue

            if text is not None:
                _warn_if_near_cap(text, src.url)
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
    grouped: dict[str, list[tuple[KnowledgeBaseSource, str]]] = {}
    for src, msg in failed:
        grouped.setdefault(_classify_failure(msg), []).append((src, msg))
    for bucket in [b for b, _ in _FAILURE_BUCKETS] + ["other"]:
        entries = grouped.get(bucket)
        if not entries:
            continue
        print(f"\nStill broken — {bucket}:")
        for src, msg in entries:
            kb = kbs.get(src.knowledge_base_uuid)
            print(f"  [{kb.title if kb else '?'}] {src.url} — {msg[:120]}")
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
