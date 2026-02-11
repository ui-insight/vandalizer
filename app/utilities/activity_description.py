"""Generate short descriptions for activity events using LLM."""

import logging
from devtools import debug
from app.celery_worker import celery_app
from app.models import ActivityEvent, ActivityType, SmartDocument, SearchSet, SearchSetItem
from app.utilities.agents import create_chat_agent
from app.utilities.config import get_user_model_name

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.activity.generate_description", bind=True)
def generate_activity_description_task(self, activity_id: str, activity_type: str, document_uuids: list[str]):
    """Generate a short 8-word description for an activity event."""
    debug(f"Starting description generation for activity {activity_id}, type {activity_type}, docs: {document_uuids}")
    try:
        activity = ActivityEvent.objects(id=activity_id).first()
        if not activity:
            debug(f"Activity {activity_id} not found")
            return

        # Get first page of documents (more context for better titles)
        document_text = ""
        document_titles = []
        for doc_uuid in document_uuids[:2]:  # Limit to first 2 documents
            doc = SmartDocument.objects(uuid=doc_uuid).first()
            if doc:
                if doc.title:
                    document_titles.append(doc.title)
                if doc.raw_text:
                    text = doc.raw_text.strip()
                    # Take first 1200 characters (roughly first page)
                    if len(text) > 1200:
                        text = text[:1200] + "..."
                    document_text += f"Document: {doc.title if doc.title else 'Untitled'}\n{text}\n\n"
                    if len(document_text) > 1500:
                        break

        if not document_text.strip():
            debug(f"No document text found for activity {activity_id}")
            return

        # Get task description and additional context based on type
        task_description = {
            ActivityType.SEARCH_SET_RUN.value: "extracting data from documents",
            ActivityType.WORKFLOW_RUN.value: "running workflow on documents",
            ActivityType.CONVERSATION.value: "chatting about documents",
        }.get(activity_type, "processing documents")
        
        # For extractions, get search set title, keys, and result count
        extraction_set_title = ""
        extraction_context = ""
        if activity_type == ActivityType.SEARCH_SET_RUN.value and activity.search_set_uuid:
            search_set = SearchSet.objects(uuid=activity.search_set_uuid).first()
            if search_set:
                # Get extraction set title
                if search_set.title:
                    extraction_set_title = search_set.title
                
                keys = []
                items = search_set.items()
                for item in items:
                    if item.searchtype == "extraction":
                        keys.append(item.searchphrase)
                
                if keys:
                    # Show first 5-7 keys as examples
                    keys_preview = ", ".join(keys[:7])
                    if len(keys) > 7:
                        keys_preview += f" and {len(keys) - 7} more"
                    extraction_context = f"\n\nExtraction Set: {extraction_set_title if extraction_set_title else 'Untitled'}\nExtracting {len(keys)} fields including: {keys_preview}"
                
                # Check if we have results in the activity snapshot
                if activity.result_snapshot:
                    snapshot = dict(activity.result_snapshot) if not isinstance(activity.result_snapshot, dict) else activity.result_snapshot
                    normalized = snapshot.get("normalized", {})
                    if normalized and isinstance(normalized, dict):
                        # Count non-null results
                        non_null_count = sum(1 for v in normalized.values() if v is not None and str(v).strip() != "")
                        if non_null_count > 0:
                            extraction_context += f"\nFound {non_null_count} values"

        # Get user's model preference with stale-model fallback.
        model_name = get_user_model_name(activity.user_id)

        # Create prompt for LLM
        if activity_type == ActivityType.SEARCH_SET_RUN.value:
            prompt = f"""You are generating a title for an extraction activity. Based on the extraction set name, the fields being extracted, and the document content, create an 8-word description.

Extraction Set: {extraction_set_title if extraction_set_title else 'Data Extraction'}
{extraction_context}

Document content (first page):
{document_text}

Generate exactly 8 words that describe what data is being extracted from what type of document. Be specific about the document type (e.g., "NSF award letter", "contract", "invoice") and what's being extracted. Examples: "Extract 88 fields from NSF award letter document" or "Extract grant information from research proposal document". Return only the 8 words, nothing else."""
        else:
            prompt = f"""Based on the following document excerpt and the task being performed, generate a very short 8-word description that captures what this activity is about.

Task: {task_description}{extraction_context}

Document excerpt:
{document_text}

Generate exactly 8 words (no more, no less) that describe this activity. Be concise and specific. Focus on what makes this activity unique - the document type, content, or specific data being extracted. Return only the 8 words, nothing else."""

        # Generate description using LLM
        chat_agent = create_chat_agent(model_name)
        result = chat_agent.run_sync(prompt)
        description = result.output.strip()

        # Ensure it's exactly 8 words (take first 8 if more)
        words = description.split()
        if len(words) > 8:
            description = " ".join(words[:8])
        elif len(words) < 8:
            # If less than 8, pad with generic words
            description = " ".join(words) + " " + " ".join(["task"] * (8 - len(words)))
            description = description.strip()

        debug(f"Generated description for activity {activity_id}: {description}")

        # Update activity title and meta_summary
        activity.title = description
        if not activity.meta_summary:
            activity.meta_summary = {}
        activity.meta_summary["ai_description"] = description
        activity.meta_summary["description_generated"] = True
        activity.save()

        # Trigger frontend update via WebSocket or polling (handled by existing polling)
        debug(f"Updated activity {activity_id} with description: {description}")

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        debug(f"Error generating description for activity {activity_id}: {e}")
        debug(f"Traceback: {error_trace}")
        logger.error(f"Failed to generate activity description for {activity_id}: {e}", exc_info=True)
