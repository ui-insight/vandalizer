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


class TestReapStaleRunning:
    """A run parked on an approval gate is waiting on a person, not stalled.

    It stops reporting progress by design, so the elapsed-time sweep used to
    mark every review left overnight as a timeout and fail the run's activity.
    """

    def _reap(self, pending_uuids=()):
        """Run the task and return (elapsed_time_query, decided_review_query)."""
        import app.tasks.activity_tasks as at

        db = MagicMock()
        db.activity_event.update_many.return_value = MagicMock(modified_count=0)
        db.approval_request.find.return_value = [{"uuid": u} for u in pending_uuids]
        with patch.object(at, "_get_db", return_value=db), \
             patch.object(at, "_resolve_stale_threshold_minutes", return_value=30):
            at.reap_stale_running_task()
        calls = db.activity_event.update_many.call_args_list
        assert len(calls) == 2, f"expected two sweeps, got {len(calls)}"
        return calls[0][0][0], calls[1][0][0]

    def test_skips_runs_awaiting_approval(self):
        elapsed, _ = self._reap()
        # `None` matches both a null field and a missing one, so ordinary
        # activities (which never carry the key) stay in scope.
        assert elapsed["meta_summary.pending_review_uuid"] is None

    def test_still_targets_stuck_running_events(self):
        elapsed, _ = self._reap()
        assert elapsed["status"] == {"$in": ["running", "queued"]}
        assert "$lt" in elapsed["last_updated_at"]

    def test_a_row_parked_on_a_decided_review_is_still_reaped(self):
        """The exemption was unbounded. approve_review returns as soon as the
        resume task is dispatched, and the marker is cleared deep inside that
        task, after guards that raise. A lost message or a tripped guard left
        the row at "running" forever — the exact condition the reaper exists to
        catch, made unreachable by its own exemption.
        """
        _elapsed, decided = self._reap(pending_uuids=["still-waiting"])

        # Reaps rows carrying a marker that is not one of the pending reviews.
        assert decided["meta_summary.pending_review_uuid"]["$nin"] == [
            None, "still-waiting",
        ]
        assert decided["status"] == {"$in": ["running", "queued"]}
        assert "$lt" in decided["last_updated_at"]

    def test_a_row_parked_on_a_review_still_awaiting_a_decision_is_left_alone(self):
        _elapsed, decided = self._reap(pending_uuids=["a", "b"])
        excluded = decided["meta_summary.pending_review_uuid"]["$nin"]
        assert "a" in excluded and "b" in excluded

    def test_the_decided_sweep_clears_the_marker_it_reaps(self):
        """Otherwise the row stays exempt from the first sweep forever."""
        import app.tasks.activity_tasks as at

        db = MagicMock()
        db.activity_event.update_many.return_value = MagicMock(modified_count=0)
        db.approval_request.find.return_value = []
        with patch.object(at, "_get_db", return_value=db), \
             patch.object(at, "_resolve_stale_threshold_minutes", return_value=30):
            at.reap_stale_running_task()

        update = db.activity_event.update_many.call_args_list[1][0][1]
        assert update["$unset"] == {"meta_summary.pending_review_uuid": ""}
        assert update["$set"]["status"] == "failed"
