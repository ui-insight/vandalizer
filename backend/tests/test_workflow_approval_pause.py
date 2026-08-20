"""A run paused on an approval gate has to stay findable.

The activity keeps status "running" while it waits (ActivityStatus has no
paused member), so ``meta_summary.pending_review_uuid`` is the only thing
telling the rail, the run history, and the stale reaper that this run is parked
on a person. Every path out of the wait has to clear it.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from types import SimpleNamespace

import pytest
from bson import ObjectId

import app.tasks.workflow_tasks as wt


def _pause(activity_id=None):
    db = MagicMock()
    db.workflow.find_one.return_value = {"name": "Subaward Review", "user_id": "owner-1", "team_id": "t1"}
    db.workflow_result.find_one.return_value = {"input_context": {"doc_uuids": ["doc-1"]}}

    final_output = {
        "_approval_pause": True,
        "_paused_step_index": 2,
        "_data_for_review": {"amount": "10000"},
        "_assignee_role": "specific_users",
        "_assigned_to_user_ids": ["rev-1"],
    }

    with patch("app.services.approval_service.resolve_assignees_sync", return_value=["rev-1"]), \
         patch("app.services.approval_service.detect_artifact_kind", return_value="json"), \
         patch.object(wt, "_accumulate_activity_usage"), \
         patch.object(wt, "_notify_approval_reviewers_sync"):
        result = wt._pause_for_approval(
            db, final_output, MagicMock(), str(ObjectId()), str(ObjectId()),
            activity_id=activity_id,
        )
    return db, result


def _activity_set_ops(db):
    """Merged $set payloads from every activity_event.update_one call."""
    merged: dict = {}
    for call in db.activity_event.update_one.call_args_list:
        merged.update(call[0][1].get("$set", {}))
    return merged


class TestPauseStampsReviewMarker:
    def test_marker_carries_the_approval_uuid(self):
        db, result = _pause(activity_id=str(ObjectId()))
        set_ops = _activity_set_ops(db)
        assert set_ops["meta_summary.pending_review_uuid"] == result["approval_uuid"]

    def test_marker_matches_the_created_review(self):
        db, result = _pause(activity_id=str(ObjectId()))
        created = db.approval_request.insert_one.call_args[0][0]
        assert created["uuid"] == result["approval_uuid"]
        assert created["status"] == "pending"

    def test_activity_link_still_written(self):
        """Regression guard: the marker must not displace the result link."""
        db, _ = _pause(activity_id=str(ObjectId()))
        assert "workflow_result" in _activity_set_ops(db)

    def test_no_activity_is_not_an_error(self):
        db, result = _pause(activity_id=None)
        db.activity_event.update_one.assert_not_called()
        assert result["status"] == "pending_approval"


class TestClearPauseMarker:
    def test_unsets_the_marker(self):
        db = MagicMock()
        oid = ObjectId()
        wt._clear_pause_marker(db, oid)
        update = db.activity_event.update_one.call_args[0][1]
        assert update["$unset"] == {"meta_summary.pending_review_uuid": ""}

    def test_bumps_last_updated_so_the_reaper_has_a_fresh_clock(self):
        """Without this the row rejoins the sweep already past the cutoff."""
        db = MagicMock()
        wt._clear_pause_marker(db, ObjectId())
        update = db.activity_event.update_one.call_args[0][1]
        assert "last_updated_at" in update["$set"]

    def test_does_not_touch_status(self):
        """Resume re-runs the workflow; the row stays running, not completed."""
        db = MagicMock()
        wt._clear_pause_marker(db, ObjectId())
        update = db.activity_event.update_one.call_args[0][1]
        assert "status" not in update["$set"]


class TestEndApprovalWait:
    """The async counterpart used by the reject and timeout paths."""

    @pytest.mark.asyncio
    async def test_clears_marker_without_closing_the_row(self):
        from app.services import approval_service

        coll = MagicMock()
        coll.update_one = _AsyncNoop()
        with patch("app.models.activity.ActivityEvent.get_motor_collection", return_value=coll):
            await approval_service.end_approval_wait(ObjectId())

        update = coll.update_one.calls[0][0][1]
        assert update["$unset"] == {"meta_summary.pending_review_uuid": ""}
        assert "status" not in update["$set"]

    @pytest.mark.asyncio
    async def test_error_closes_the_row_as_failed(self):
        from app.services import approval_service

        coll = MagicMock()
        coll.update_one = _AsyncNoop()
        with patch("app.models.activity.ActivityEvent.get_motor_collection", return_value=coll):
            await approval_service.end_approval_wait(ObjectId(), error="Rejected by reviewer.")

        update = coll.update_one.calls[0][0][1]
        assert update["$set"]["status"] == "failed"
        assert update["$set"]["error"] == "Rejected by reviewer."
        assert "finished_at" in update["$set"]

    @pytest.mark.asyncio
    async def test_it_targets_the_review_rather_than_the_run(self):
        """A batch shares one ActivityEvent across every document, and
        _pause_for_approval overwrites `workflow_result` on each pause. So
        matching on the run found the row only for whichever document paused
        last, and missed entirely for the others — leaving the marker behind,
        and with it a row the reaper will never touch.
        """
        from app.services import approval_service

        coll = MagicMock()
        coll.update_one = _AsyncNoop()
        with patch("app.models.activity.ActivityEvent.get_motor_collection", return_value=coll), \
             patch("app.models.workflow.WorkflowResult.get", new=AsyncMock(return_value=None)):
            await approval_service.end_approval_wait(ObjectId(), approval_uuid="rev-7")

        query = coll.update_one.calls[0][0][0]
        assert query == {"meta_summary.pending_review_uuid": "rev-7"}

    @pytest.mark.asyncio
    async def test_one_document_rejection_does_not_fail_the_whole_batch(self):
        """The shared row represents the batch. Closing it because one document
        was rejected would report every other document as failed while they are
        still running."""
        from app.services import approval_service

        coll = MagicMock()
        coll.update_one = _AsyncNoop()
        batch_run = SimpleNamespace(batch_id="b-1")
        with patch("app.models.activity.ActivityEvent.get_motor_collection", return_value=coll), \
             patch("app.models.workflow.WorkflowResult.get", new=AsyncMock(return_value=batch_run)):
            await approval_service.end_approval_wait(
                ObjectId(), approval_uuid="rev-7", error="Rejected by reviewer.",
            )

        update = coll.update_one.calls[0][0][1]
        # The wait ends...
        assert update["$unset"] == {"meta_summary.pending_review_uuid": ""}
        # ...but the row stays open for the documents still running.
        assert "status" not in update["$set"]

    @pytest.mark.asyncio
    async def test_a_single_run_rejection_still_closes_its_row(self):
        from app.services import approval_service

        coll = MagicMock()
        coll.update_one = _AsyncNoop()
        single_run = SimpleNamespace(batch_id=None)
        with patch("app.models.activity.ActivityEvent.get_motor_collection", return_value=coll), \
             patch("app.models.workflow.WorkflowResult.get", new=AsyncMock(return_value=single_run)):
            await approval_service.end_approval_wait(
                ObjectId(), approval_uuid="rev-7", error="Rejected by reviewer.",
            )

        update = coll.update_one.calls[0][0][1]
        assert update["$set"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_never_raises(self):
        """A review decision must not fail on a bookkeeping write."""
        from app.services import approval_service

        with patch(
            "app.models.activity.ActivityEvent.get_motor_collection",
            side_effect=RuntimeError("mongo down"),
        ):
            await approval_service.end_approval_wait(ObjectId(), error="x")


class _AsyncNoop:
    """Awaitable stand-in that records how it was called."""

    def __init__(self):
        self.calls: list = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return MagicMock()
