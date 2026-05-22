"""Celery task for generating short LLM descriptions for activity events.

Ported from Flask app/utilities/activity_description.py.
Uses pymongo (sync) for DB access.
"""

import datetime
import logging
import re

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)

# Strips a leading <think>…</think> reasoning block that some Qwen/DeepSeek-R1
# style models emit even when thinking is disabled at the request level.
_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
# Catches a stray opening <think> with no closing tag (some models stream the
# block and then truncate at max_tokens without ever closing it).
_OPEN_THINK_RE = re.compile(r"<think\b[^>]*>.*", re.IGNORECASE | re.DOTALL)


def _clean_title(raw: str) -> str:
    """Strip thinking tags, surrounding quotes/punctuation, and clamp length."""
    text = _THINK_BLOCK_RE.sub("", raw or "")
    text = _OPEN_THINK_RE.sub("", text)
    text = text.strip().strip('"').strip("'").strip()
    # Drop leading prefixes like "Title:" the model sometimes adds.
    text = re.sub(r"^(title|description)\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    # Collapse whitespace and remove trailing period.
    text = " ".join(text.split())
    text = text.rstrip(".")
    return text


def _pick_title_model(sys_cfg: dict, user_model_name: str | None) -> str | None:
    """Choose the fastest non-thinking model available.

    Priority:
      1. Any model in available_models with thinking explicitly False
      2. The user's selected model
      3. The first available model
    """
    models = sys_cfg.get("available_models") or []
    for m in models:
        if m.get("thinking") is False and m.get("name"):
            return m["name"]
    if user_model_name:
        return user_model_name
    return models[0]["name"] if models and models[0].get("name") else None


TITLE_SYSTEM_PROMPT = (
    "You write very short, descriptive titles for activity log entries. "
    "Output the title only — no quotes, no punctuation, no preamble, no "
    "thinking. Five to seven words. Title Case."
)

# Fallback when SystemConfig.retention_config doesn't override it. Activity is
# considered stuck if its last_updated_at hasn't advanced in this long — workflow
# and extraction steps refresh last_updated_at as they make progress.
STALE_ACTIVITY_THRESHOLD_MINUTES_DEFAULT = 30


def _resolve_stale_threshold_minutes(db) -> int:
    """Read the stale-activity threshold from SystemConfig, falling back to default.

    Uses sync pymongo so it's safe to call from the Celery beat task.
    """
    try:
        sys_cfg = db.system_config.find_one() or {}
        retention = sys_cfg.get("retention_config") or {}
        value = retention.get("activity_stale_threshold_minutes")
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    except Exception:
        logger.exception("Failed to resolve stale threshold from SystemConfig")
    return STALE_ACTIVITY_THRESHOLD_MINUTES_DEFAULT


def _get_db():
    """Get sync pymongo database handle."""
    from pymongo import MongoClient

    from app.config import Settings
    settings = Settings()
    client = MongoClient(settings.mongo_host)
    return client[settings.mongo_db]


@celery_app.task(
    bind=True,
    name="tasks.activity.generate_description",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=5,
)
def generate_activity_description_task(
    self,
    activity_id: str,
    activity_type: str,
    document_uuids: list[str],
) -> None:
    """Generate a short 8-word description for an activity event."""
    from bson import ObjectId

    from app.services.llm_service import create_chat_agent

    logger.info(
        "Starting description generation for activity %s, type %s",
        activity_id, activity_type,
    )

    db = _get_db()

    # Mark the title-generation attempt as complete on every exit path so the
    # activity rail stops shimmering "Generating title…" and falls back to the
    # activity's original title (workflow name / extraction set name). Without
    # this, any early return below leaves the UI stuck on the shimmer until a
    # 2-minute client-side fallback fires.
    def _mark_done(description: str | None = None) -> None:
        try:
            update: dict = {"meta_summary.description_generated": True}
            if description:
                update["meta_summary.ai_description"] = description
                update["title"] = description
            db.activity_event.update_one(
                {"_id": ObjectId(activity_id)},
                {"$set": update},
            )
        except Exception:
            logger.exception(
                "Failed to mark description_generated for activity %s",
                activity_id,
            )

    try:
        activity = db.activity_event.find_one({"_id": ObjectId(activity_id)})
        if not activity:
            logger.warning("Activity %s not found", activity_id)
            return

        # Get first 2 documents for context
        document_text = ""
        for doc_uuid in document_uuids[:2]:
            doc = db.smart_document.find_one({"uuid": doc_uuid})
            if doc:
                title = doc.get("title", "Untitled")
                raw_text = (doc.get("raw_text") or "").strip()
                if raw_text:
                    text = raw_text[:1200] + "..." if len(raw_text) > 1200 else raw_text
                    document_text += f"Document: {title}\n{text}\n\n"
                    if len(document_text) > 1500:
                        break

        if not document_text.strip():
            # For conversations, fall back to the first exchange as context
            if activity_type == "conversation" and activity.get("conversation_id"):
                conv = db.chat_conversation.find_one({"uuid": activity["conversation_id"]})
                if conv and conv.get("messages"):
                    msg_ids = conv["messages"][:4]
                    msgs = list(db.chat_message.find({"_id": {"$in": msg_ids}}))
                    if msgs:
                        combined = " ".join(
                            (m.get("message") or "")[:400] for m in msgs[:2]
                        ).strip()
                        if combined:
                            document_text = combined
            if not document_text.strip():
                logger.info("No text context found for activity %s", activity_id)
                _mark_done()
                return

        # Build context based on activity type
        task_description = {
            "search_set_run": "extracting data from documents",
            "workflow_run": "running workflow on documents",
            "conversation": "chatting about documents",
        }.get(activity_type, "processing documents")

        extraction_set_title = ""
        extraction_context = ""

        if activity_type == "search_set_run" and activity.get("search_set_uuid"):
            ss = db.search_set.find_one({"uuid": activity["search_set_uuid"]})
            if ss:
                extraction_set_title = ss.get("title", "")
                items = list(db.search_set_item.find({
                    "searchset": activity["search_set_uuid"],
                    "searchtype": "extraction",
                }))
                keys = [item["searchphrase"] for item in items]
                if keys:
                    keys_preview = ", ".join(keys[:7])
                    if len(keys) > 7:
                        keys_preview += f" and {len(keys) - 7} more"
                    extraction_context = (
                        f"\n\nExtraction Set: {extraction_set_title or 'Untitled'}\n"
                        f"Extracting {len(keys)} fields including: {keys_preview}"
                    )

                snapshot = activity.get("result_snapshot", {})
                normalized = snapshot.get("normalized", {})
                if normalized and isinstance(normalized, dict):
                    non_null = sum(1 for v in normalized.values() if v is not None and str(v).strip())
                    if non_null > 0:
                        extraction_context += f"\nFound {non_null} values"

        # Resolve model — prefer the fastest non-thinking model so the rail
        # title arrives quickly; reasoning models add 5–30s of latency for
        # what should be a one-shot 5-word output.
        sys_cfg = db.system_config.find_one() or {}
        user_id = activity.get("user_id")
        user_model_name = ""
        if user_id:
            user_cfg = db.user_model_config.find_one({"user_id": user_id})
            if user_cfg:
                user_model_name = user_cfg.get("name", "") or ""
        model_name = _pick_title_model(sys_cfg, user_model_name)

        if not model_name:
            logger.warning("No model available for description generation")
            _mark_done()
            return

        # Build prompt
        if activity_type == "search_set_run":
            prompt = (
                f"Write a short title for an extraction activity.\n\n"
                f"Extraction Set: {extraction_set_title or 'Data Extraction'}"
                f"{extraction_context}\n\n"
                f"Document content (first page):\n{document_text}\n\n"
                f"Title (5–7 words, no punctuation, just the words):"
            )
        else:
            prompt = (
                f"Write a short title for this activity.\n\n"
                f"Task: {task_description}{extraction_context}\n\n"
                f"Content:\n{document_text}\n\n"
                f"Title (5–7 words, no punctuation, just the words):"
            )

        # Force thinking off — the per-model `thinking` flag from SystemConfig
        # would otherwise leak in and add latency. Use a tight system prompt
        # instead of the default chat preamble so the model stays on task.
        chat_agent = create_chat_agent(
            model_name,
            system_prompt=TITLE_SYSTEM_PROMPT,
            thinking_override=False,
            system_config_doc=sys_cfg,
        )
        result = chat_agent.run_sync(prompt)
        description = _clean_title(result.output)

        # Truncate to 8 words max; the UI clamps to 2 lines anyway.
        words = description.split()
        if len(words) > 8:
            description = " ".join(words[:8])

        if not description:
            logger.warning(
                "Empty title from model %s for activity %s (raw=%r)",
                model_name, activity_id, result.output[:200],
            )
            _mark_done()
            return

        _mark_done(description=description)

        logger.info(
            "Updated activity %s with title %r (model=%s)",
            activity_id, description, model_name,
        )

    except Exception as e:
        logger.error("Error generating description for activity %s: %s", activity_id, e, exc_info=True)
        _mark_done()


@celery_app.task(bind=True, name="tasks.activity.reap_stale_running")
def reap_stale_running_task(self) -> None:
    """Mark activity events stuck in running/queued as failed.

    Catches orphans from crashed workers, dropped chat streams, and Celery soft
    time limits that killed a task before its exception handler could update the
    activity record. Without this, the activity rail spins forever and the user
    has to delete the item manually.
    """
    db = _get_db()
    threshold_minutes = _resolve_stale_threshold_minutes(db)
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=threshold_minutes,
    )
    now = datetime.datetime.now(datetime.timezone.utc)

    result = db.activity_event.update_many(
        {
            "status": {"$in": ["running", "queued"]},
            "last_updated_at": {"$lt": cutoff},
        },
        {
            "$set": {
                "status": "failed",
                "finished_at": now,
                "last_updated_at": now,
                "error": (
                    f"Timed out — no progress reported for over "
                    f"{threshold_minutes} minutes."
                ),
            },
        },
    )

    if result.modified_count:
        logger.info(
            "Reaped %d stale activity events (threshold=%d min)",
            result.modified_count, threshold_minutes,
        )
