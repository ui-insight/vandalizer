"""Preview URLs before they enter a knowledge base.

Adding URLs used to be blind: each page was fetched, chunked and embedded in
one step, and the user found out afterwards that a page had come back as a
cookie banner or two lines of navigation. A preview runs the same fetch, the
same rejection gates and the same crawl as an add, but writes nothing to the
knowledge base. It records what each page *would* contribute — its text, how
many chunks it would become, and a verdict — so the user can drop pages before
committing. Committing indexes the stored text of the kept pages, so what was
reviewed is exactly what is indexed.
"""

from __future__ import annotations
from motor.motor_asyncio import AsyncIOMotorCollection


import datetime
import logging

from app.models.knowledge import (
    PREVIEW_ADDABLE_VERDICTS,
    KBUrlPreview,
    KBUrlPreviewPage,
    KnowledgeBase,
    KnowledgeBaseSource,
)
from app.services import knowledge_service as ks
from app.services.document_manager import count_chunks
from app.services.web_fetcher import WebFetchResult
from app.utils.fetch_errors import describe_fetch_error
from app.utils.url_validation import normalize_crawl_url

logger = logging.getLogger(__name__)

#: How much of a page's text the preview list carries; the rest is fetched on
#: demand for the one page the user expands.
EXCERPT_CHARS = 1500

GARBLED_REASON = "Most of the text is unreadable characters — the page may not have extracted properly"

#: How long a preview may wait for a worker before the user is told it is
#: taking longer than expected. An idle worker starts one in a second or two.
NOT_STARTED_AFTER = datetime.timedelta(seconds=60)
#: How long a started preview may go without recording a page. One page is at
#: most a fetch plus a browser render, each bounded by the fetch timeout.
NO_PROGRESS_AFTER = datetime.timedelta(seconds=90)
#: Past the task's hard time limit (1860s) with no progress, no worker is
#: running it any more: the preview is settled as failed.
DEAD_AFTER = datetime.timedelta(seconds=1860)

NOT_STARTED_MESSAGE = (
    "This is taking longer than expected. The server hasn't started fetching "
    "yet — it may be busy with other work."
)
NO_PROGRESS_MESSAGE = (
    "This is taking longer than expected. The server hasn't fetched another "
    "page for a while — a site may be slow to respond."
)
NO_WORKERS_MESSAGE = (
    "The server's background workers aren't running, so the preview can't "
    "start. Retrying won't help — ask your administrator to restart them."
)
DEAD_MESSAGE = "The preview stopped before it finished. Try again."

#: The task run_preview runs in; its queue is the one that must have a worker.
PREVIEW_TASK = "tasks.kb.preview_urls"


class PreviewCanceled(Exception):
    """The user canceled the preview while it was fetching."""


def _utc(value: datetime.datetime) -> datetime.datetime:
    # Mongo hands datetimes back naive; they are UTC.
    return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)


def _now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


def _collection() -> AsyncIOMotorCollection:
    return KBUrlPreview.get_motor_collection()


async def start_preview(
    kb: KnowledgeBase,
    user_id: str,
    urls: list[str],
    *,
    crawl_enabled: bool,
    max_crawl_pages: int,
    allowed_domains: str,
) -> KBUrlPreview:
    """Create a preview for ``urls``; the caller dispatches ``run_preview``.

    Raises ValueError when no usable URL was given.
    """
    new, present = await ks.partition_new_urls(kb, urls)
    if not new and not present:
        raise ValueError("No URLs provided")
    preview = KBUrlPreview(
        knowledge_base_uuid=kb.uuid,
        user_id=user_id,
        # Present ones stay in the list so the preview can say they were
        # skipped, rather than silently dropping what the user typed.
        urls=new + present,
        crawl_enabled=crawl_enabled,
        max_crawl_pages=max(1, min(max_crawl_pages, 50)),
        allowed_domains=allowed_domains or "",
    )
    await preview.insert()
    return preview


class _Recorder:
    """Writes preview pages in the order they were reached."""

    def __init__(self, preview: KBUrlPreview) -> None:
        self.preview = preview
        self.order = 0
        self.seen: set[str] = set()

    def has(self, url: str) -> bool:
        return normalize_crawl_url(url) in self.seen

    async def check_canceled(self) -> None:
        """Stop between pages once the user has canceled."""
        doc = await _collection().find_one({"uuid": self.preview.uuid}, {"status": 1})
        if not doc or doc.get("status") != "running":
            raise PreviewCanceled()

    async def record(self, url: str, verdict: str, **fields: object) -> KBUrlPreviewPage:
        self.seen.add(normalize_crawl_url(url))
        page = KBUrlPreviewPage(
            preview_uuid=self.preview.uuid,
            order=self.order,
            url=url[:2000],
            verdict=verdict,
            expires_at=self.preview.expires_at,
            **fields,
        )
        self.order += 1
        await page.insert()
        await _collection().update_one(
            {"uuid": self.preview.uuid}, {"$set": {"progress_at": _now()}},
        )
        return page


def _low_quality_reasons(result: WebFetchResult, *, is_seed: bool) -> list[str]:
    from app.config import Settings
    from app.utils.extraction_quality import nonletter_ratio
    from app.utils.page_quality import describe_low_value_page

    reasons: list[str] = []
    if is_seed:
        # A crawled page this thin never reaches here (the crawl drops it as
        # navigation, as ingestion does). A URL the user typed is added anyway
        # — so say it is thin and let them decide.
        thin = describe_low_value_page(
            result.text,
            len(ks._crawlable_links(result, result.url)),
            min_chars=Settings().kb_crawl_min_content_chars,
        )
        if thin:
            reasons.append(thin)
    if nonletter_ratio(result.text) > Settings().extraction_max_nonletter_ratio:
        reasons.append(GARBLED_REASON)
    return reasons


async def _preview_page(
    rec: _Recorder,
    url: str,
    *,
    parent_url: str | None,
) -> tuple[WebFetchResult | None, str]:
    """Fetch one page and record what adding it would do.

    Returns the fetch result (for following its links) and the verdict. The
    result is None when ingestion would have failed the page, which — as in
    ingestion — also means its links are not followed.
    """
    from app.config import Settings
    from app.utils.page_quality import describe_low_value_page

    await rec.check_canceled()
    try:
        result = await ks.fetch_source_page(url)
    except Exception as e:  # noqa: BLE001 — every failure is shown, as ingestion records it
        logger.info("URL preview fetch failed for %s: %s", url, e)
        await rec.record(url, "error", parent_url=parent_url, reason=describe_fetch_error(e)[:2000])
        return None, "error"

    common = {
        "parent_url": parent_url,
        "final_url": result.final_url,
        "title": result.title,
        "char_count": len(result.text),
    }
    reject = ks._reject_fetched_page(result)
    if reject:
        await rec.record(url, "empty", reason=reject, text=result.text[:EXCERPT_CHARS], **common)
        return None, "empty"

    if parent_url is not None:
        # The crawl's own gate: navigation is fetched for its links, not kept.
        nav = describe_low_value_page(
            result.text,
            len(ks._crawlable_links(result, url)),
            min_chars=Settings().kb_crawl_min_content_chars,
        )
        if nav:
            await rec.record(url, "navigation", reason=nav, text=result.text[:EXCERPT_CHARS], **common)
            return result, "navigation"

    reasons = _low_quality_reasons(result, is_seed=parent_url is None)
    # The preview keeps only the text, so the page is screened now, while its
    # HTML is at hand; committing it holds it for review like a direct add.
    from app.services.fetched_page_screen import screen_fetched_page

    findings = [f.to_dict() for f in screen_fetched_page(result.raw_html, result.text)]
    if findings:
        reasons.append(
            ks.describe_held_page(findings).replace(
                ". It was not added — review what was found, then add it anyway or remove it",
                ". If added, it is held for review before anything is indexed",
            )
        )
    verdict = "low" if reasons else "good"
    await rec.record(
        url, verdict,
        reason="; ".join(reasons) or None,
        text=result.text,
        chunk_count=count_chunks(result.text),
        truncated=bool(result.truncated),
        warnings=list(result.advisories),
        review_findings=findings,
        **common,
    )
    return result, verdict


async def _url_in_kb(kb_uuid: str, url: str) -> bool:
    return bool(await KnowledgeBaseSource.find_one(
        KnowledgeBaseSource.knowledge_base_uuid == kb_uuid,
        KnowledgeBaseSource.url == url,
    ))


async def run_preview(preview_uuid: str) -> None:
    """Fetch (and crawl) a preview's URLs, recording every page. Never raises."""
    # Claim it: a preview canceled while queued, or already started by another
    # delivery of the task, is left alone.
    now = _now()
    claimed = await _collection().update_one(
        {"uuid": preview_uuid, "status": "running", "started_at": None},
        {"$set": {"started_at": now, "progress_at": now}},
    )
    if claimed.modified_count != 1:
        logger.info("URL preview %s not started: canceled, missing or already running", preview_uuid)
        return
    preview = await KBUrlPreview.find_one(KBUrlPreview.uuid == preview_uuid)
    if not preview:
        return
    rec = _Recorder(preview)
    status, error_message = "ready", None
    try:
        for seed in preview.urls:
            if rec.has(seed):
                continue
            if await _url_in_kb(preview.knowledge_base_uuid, seed):
                await rec.record(
                    seed, "duplicate",
                    reason="Already in this knowledge base. Use ↻ on that source to re-fetch it.",
                )
                continue
            fetched, verdict = await _preview_page(rec, seed, parent_url=None)
            if not (preview.crawl_enabled and fetched and verdict in PREVIEW_ADDABLE_VERDICTS):
                continue

            async def visit(url: str, seed: str = seed) -> ks._CrawlVisit:
                # Same skips as an add's crawl: a page already held (in the KB,
                # or reached earlier in this preview) is not fetched again.
                if rec.has(url) or await _url_in_kb(preview.knowledge_base_uuid, url):
                    return ks._CrawlVisit("known")
                child, child_verdict = await _preview_page(rec, url, parent_url=seed)
                if child_verdict == "navigation":
                    return ks._CrawlVisit("skipped", child)
                return ks._CrawlVisit("added", child)

            await ks._crawl_bfs(
                seed, fetched, preview.max_crawl_pages, preview.allowed_domains, visit,
            )
    except PreviewCanceled:
        logger.info("URL preview %s canceled", preview_uuid)
        return
    except Exception as e:
        logger.exception("URL preview %s failed", preview_uuid)
        status = "error"
        error_message = f"The preview could not be completed: {str(e)[:300]}"
    # Only a preview still running is finished here: save() would overwrite a
    # cancel that landed during the last page.
    await _collection().update_one(
        {"uuid": preview_uuid, "status": "running"},
        {"$set": {"status": status, "error_message": error_message}},
    )


async def cancel_preview(preview: KBUrlPreview) -> bool:
    """Stop a running preview; the worker stops before its next page.

    False if it had already finished.
    """
    result = await _collection().update_one(
        {"uuid": preview.uuid, "status": "running"},
        {"$set": {"status": "canceled"}},
    )
    return bool(result.modified_count == 1)


async def check_progress(preview: KBUrlPreview, now: datetime.datetime | None = None) -> str | None:
    """Why a running preview looks stuck, or None.

    A preview with no progress past the task's hard time limit has no worker
    left: it is settled as failed, so the user gets an error instead of a
    spinner until the TTL removes it.
    """
    if preview.status != "running":
        return None
    now = now or _now()
    last = _utc(preview.progress_at or preview.started_at or preview.created_at)
    if now - last > DEAD_AFTER:
        result = await _collection().update_one(
            {"uuid": preview.uuid, "status": "running"},
            {"$set": {"status": "error", "error_message": DEAD_MESSAGE}},
        )
        if result.modified_count == 1:
            preview.status = "error"
            preview.error_message = DEAD_MESSAGE
        return None
    if preview.started_at is None:
        if now - last <= NOT_STARTED_AFTER:
            return None
        # Busy and down look the same from here; only down makes Retry useless.
        from app.services.worker_status import queue_for, queue_has_worker

        if await queue_has_worker(queue_for(PREVIEW_TASK)) is False:
            return NO_WORKERS_MESSAGE
        return NOT_STARTED_MESSAGE
    return NO_PROGRESS_MESSAGE if now - last > NO_PROGRESS_AFTER else None


async def get_preview(kb_uuid: str, preview_uuid: str, user_id: str) -> KBUrlPreview | None:
    """The caller's own preview of this KB, or None."""
    return await KBUrlPreview.find_one(
        KBUrlPreview.uuid == preview_uuid,
        KBUrlPreview.knowledge_base_uuid == kb_uuid,
        KBUrlPreview.user_id == user_id,
    )


async def list_pages(preview: KBUrlPreview) -> list[KBUrlPreviewPage]:
    return await KBUrlPreviewPage.find(
        KBUrlPreviewPage.preview_uuid == preview.uuid,
    ).sort("order").to_list()


def page_summary(page: KBUrlPreviewPage) -> dict:
    return {
        "page_id": page.page_id,
        "url": page.url,
        "final_url": page.final_url,
        "title": page.title,
        "parent_url": page.parent_url,
        "verdict": page.verdict,
        "addable": page.verdict in PREVIEW_ADDABLE_VERDICTS,
        "reason": page.reason,
        "excerpt": page.text[:EXCERPT_CHARS],
        "char_count": page.char_count,
        "chunk_count": page.chunk_count,
        "truncated": page.truncated,
        "warnings": page.warnings,
    }


async def claim_for_commit(preview: KBUrlPreview) -> bool:
    """Atomically move a ready preview to committing; False if it wasn't ready.

    Two clicks on Add must not index the same pages twice.
    """
    result = await KBUrlPreview.get_motor_collection().update_one(
        {"uuid": preview.uuid, "status": "ready"},
        {"$set": {"status": "committing"}},
    )
    return bool(result.modified_count == 1)


async def commit_preview(preview_uuid: str, page_ids: list[str]) -> int:
    """Index the kept pages of a preview. Returns how many sources were added.

    Pages are created in the order they were reached, so a crawled page's seed
    already exists when the page is linked to it. A page whose URL the KB
    gained since the preview (another add, another tab) is skipped.
    """
    preview = await KBUrlPreview.find_one(KBUrlPreview.uuid == preview_uuid)
    if not preview:
        return 0
    kb = await KnowledgeBase.find_one(KnowledgeBase.uuid == preview.knowledge_base_uuid)
    if not kb:
        return 0

    wanted = set(page_ids)
    pages = await list_pages(preview)
    seeds: dict[str, KnowledgeBaseSource] = {}
    children: dict[str, list[str]] = {}
    added = 0

    for page in pages:
        if page.page_id not in wanted or page.verdict not in PREVIEW_ADDABLE_VERDICTS:
            continue
        is_seed = page.parent_url is None
        parent = seeds.get(page.parent_url) if page.parent_url else None
        # The same fields an add sets: crawl settings live on the seed only.
        crawl_fields = (
            {"crawl_enabled": preview.crawl_enabled, "max_crawl_pages": preview.max_crawl_pages}
            if is_seed else {}
        )
        source = KnowledgeBaseSource(
            knowledge_base_uuid=kb.uuid,
            source_type="url",
            url=page.url[:2000],
            parent_source_uuid=parent.uuid if parent else None,
            status="processing",
            **crawl_fields,
        )
        if not await ks._insert_source_unless_duplicate(source):
            continue
        try:
            if page.review_findings:
                # Not indexed: held with what was found, as _ingest_url_source
                # holds a page it screens, until the user adds it anyway.
                source.content = ks._kb_snapshot(page.text)
                source.url_title = page.title
                source.truncated = page.truncated
                source.warnings = list(page.warnings)
                source.review_findings = list(page.review_findings)
                source.status = "held"
                source.error_message = ks.describe_held_page(page.review_findings)[:2000]
                stored = await ks._save_unless_deleted(source)
            else:
                stored = await ks._store_url_text(
                    source, kb, page.text,
                    title=page.title,
                    truncated=page.truncated,
                    warnings=list(page.warnings),
                )
        except Exception as e:
            logger.error("Error indexing previewed page %s: %s", page.url, e)
            source.status = "error"
            source.error_message = describe_fetch_error(e)[:2000]
            await ks._save_unless_deleted(source)
            stored = False
        if not stored and source.status == "deleted":
            continue
        added += 1
        if is_seed:
            seeds[page.url] = source
        elif parent and page.parent_url:
            children.setdefault(page.parent_url, []).append(page.url)

    # A seed's crawl record, as an add writes it: the pages kept, and the
    # navigation pages followed but not kept.
    navigation = [p for p in pages if p.verdict == "navigation"]
    for seed_url, seed in seeds.items():
        if not preview.crawl_enabled:
            continue
        seed.crawled_urls = children.get(seed_url, [])
        skipped = [p.url for p in navigation if p.parent_url == seed_url]
        seed.skipped_urls = skipped or None
        await ks._save_unless_deleted(seed)

    preview.status = "committed"
    await preview.save()
    await ks.recalculate_stats(kb)
    return added

