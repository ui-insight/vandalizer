"""Celery task for generating short LLM descriptions for activity events.

Ported from Flask app/utilities/activity_description.py.
Uses pymongo (sync) for DB access.
"""

import logging

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)


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

    try:
        db = _get_db()
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

        # Resolve model
        sys_cfg = db.system_config.find_one() or {}
        user_id = activity.get("user_id")
        model_name = ""
        if user_id:
            user_cfg = db.user_model_config.find_one({"user_id": user_id})
            if user_cfg:
                model_name = user_cfg.get("name", "")
        if not model_name:
            models = sys_cfg.get("available_models", [])
            model_name = models[0]["name"] if models else ""

        if not model_name:
            logger.warning("No model available for description generation")
            return

        # Build prompt
        if activity_type == "search_set_run":
            prompt = (
                f"You are generating a short title for an extraction activity. "
                f"Based on the extraction set name, the fields being extracted, "
                f"and the document content, create a 4-to-6-word title.\n\n"
                f"Extraction Set: {extraction_set_title or 'Data Extraction'}\n"
                f"{extraction_context}\n\n"
                f"Document content (first page):\n{document_text}\n\n"
                f"Generate a memorable 4-to-6-word title describing what data is being extracted "
                f"from what type of document. No punctuation. Return only the words, nothing else."
            )
        else:
            prompt = (
                f"Based on the following content and the task being performed, "
                f"generate a very short 4-to-6-word title.\n\n"
                f"Task: {task_description}{extraction_context}\n\n"
                f"Content:\n{document_text}\n\n"
                f"Generate a memorable 4-to-6-word title. No punctuation. "
                f"Return only the words, nothing else."
            )

        chat_agent = create_chat_agent(model_name, system_config_doc=sys_cfg)
        result = chat_agent.run_sync(prompt)
        description = result.output.strip()

        # Truncate to 6 words max; accept shorter descriptions as-is
        words = description.split()
        if len(words) > 6:
            description = " ".join(words[:6])

        # Update activity
        meta_summary = activity.get("meta_summary", {}) or {}
        meta_summary["ai_description"] = description
        meta_summary["description_generated"] = True

        db.activity_event.update_one(
            {"_id": ObjectId(activity_id)},
            {"$set": {"title": description, "meta_summary": meta_summary}},
        )

        logger.info("Updated activity %s with description: %s", activity_id, description)

    except Exception as e:
        logger.error("Error generating description for activity %s: %s", activity_id, e, exc_info=True)
