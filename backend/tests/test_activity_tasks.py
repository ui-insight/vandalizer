"""Tests for app.tasks.activity_tasks.generate_activity_description_task.

Activity title generation is best-effort cosmetic enrichment; an LLM outage
must degrade gracefully (activity goes untitled) and log at warning, not page
Sentry as a fault.
"""

from unittest.mock import MagicMock, patch

from bson import ObjectId
from pydantic_ai.exceptions import ModelAPIError


def _db_with_activity():
    db = MagicMock()
    activity_oid = ObjectId()
    db.activity_event.find_one.return_value = {
        "_id": activity_oid, "user_id": "u1", "team_id": None,
    }
    # A document with text so the prompt has context and we reach the model call.
    db.smart_document.find_one.return_value = {
        "uuid": "doc-1", "title": "NSF_Grant.pdf", "raw_text": "Grant proposal body.",
    }
    db.user_model_config.find_one.return_value = None
    db.system_config.find_one.return_value = {}
    return db, str(activity_oid)


class TestGenerateActivityDescription:
    def test_model_connection_error_warns_and_marks_done(self):
        import app.tasks.activity_tasks as at

        db, activity_id = _db_with_activity()
        err = ModelAPIError(model_name="VandalAI-Fast", message="Connection error.")

        with patch.object(at, "_get_db", return_value=db), \
             patch.object(at, "_pick_title_model", return_value="VandalAI-Fast"), \
             patch("app.services.llm_service.create_chat_agent", return_value=MagicMock()), \
             patch("app.services.metering.metered", return_value=MagicMock()), \
             patch.object(at, "run_task_async", side_effect=err), \
             patch.object(at, "logger") as mock_logger:
            result = at.generate_activity_description_task(
                activity_id=activity_id,
                activity_type="conversation",
                document_uuids=["doc-1"],
            )

        assert result is None
        # Handled degradation: warning, never error/exception (no Sentry event).
        mock_logger.error.assert_not_called()
        mock_logger.exception.assert_not_called()
        assert mock_logger.warning.called
        # The activity is still marked done so the UI stops shimmering.
        set_ops = [c[0][1]["$set"] for c in db.activity_event.update_one.call_args_list]
        assert any(s.get("meta_summary.description_generated") for s in set_ops)
