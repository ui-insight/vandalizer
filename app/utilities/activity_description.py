"""Generate short descriptions for activity events using LLM."""

import logging
from devtools import debug
from app.celery_worker import celery_app
from app.models import ActivityEvent, ActivityType, SmartDocument
from app.utilities.agents import create_chat_agent
from app.utilities.config import get_default_model_name
from app.models import UserModelConfig

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.activity.generate_description", bind=True)
def generate_activity_description_task(self, activity_id: str, activity_type: str, document_uuids: list[str]):
    """Generate a short 5-word description for an activity event."""
    debug(f"Starting description generation for activity {activity_id}, type {activity_type}, docs: {document_uuids}")
    try:
        activity = ActivityEvent.objects(id=activity_id).first()
        if not activity:
            debug(f"Activity {activity_id} not found")
            return

        # Get first 200-500 characters from documents
        document_text = ""
        for doc_uuid in document_uuids[:3]:  # Limit to first 3 documents
            doc = SmartDocument.objects(uuid=doc_uuid).first()
            if doc and doc.raw_text:
                text = doc.raw_text.strip()
                # Take first 350 characters (middle of 200-500 range)
                if len(text) > 350:
                    text = text[:350] + "..."
                document_text += text + "\n\n"
                if len(document_text) > 500:
                    break

        if not document_text.strip():
            debug(f"No document text found for activity {activity_id}")
            return

        # Get task description based on type
        task_description = {
            ActivityType.SEARCH_SET_RUN.value: "extracting data from documents",
            ActivityType.WORKFLOW_RUN.value: "running workflow on documents",
            ActivityType.CONVERSATION.value: "chatting about documents",
        }.get(activity_type, "processing documents")

        # Get user's model preference
        user_model_config = UserModelConfig.objects(user_id=activity.user_id).first()
        model_name = (
            user_model_config.name
            if user_model_config and user_model_config.name
            else get_default_model_name()
        )

        # Create prompt for LLM
        prompt = f"""Based on the following document excerpt and the task being performed, generate a very short 5-word description that captures what this activity is about.

Task: {task_description}

Document excerpt:
{document_text}

Generate exactly 5 words (no more, no less) that describe this activity. Be concise and specific. Return only the 5 words, nothing else."""

        # Generate description using LLM
        chat_agent = create_chat_agent(model_name)
        result = chat_agent.run_sync(prompt)
        description = result.output.strip()

        # Ensure it's exactly 5 words (take first 5 if more)
        words = description.split()
        if len(words) > 5:
            description = " ".join(words[:5])
        elif len(words) < 5:
            # If less than 5, pad with generic words
            description = " ".join(words) + " " + " ".join(["task"] * (5 - len(words)))
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

