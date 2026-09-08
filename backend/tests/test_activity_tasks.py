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

    def _reap(self, pending_uuids=(), bell_rows=(), claim_modified=1):
        """Run the task and return (elapsed_time_query, decided_review_query)."""
        import app.tasks.activity_tasks as at

        db = MagicMock()
        db.activity_event.find.return_value = list(bell_rows)
        db.activity_event.update_many.return_value = MagicMock(modified_count=0)
        db.activity_event.update_one.return_value = MagicMock(modified_count=claim_modified)
        db.approval_request.find.return_value = [{"uuid": u} for u in pending_uuids]
        with patch.object(at, "_get_db", return_value=db), \
             patch.object(at, "_resolve_stale_threshold_minutes", return_value=30), \
             patch("app.services.failure_notifications.notify_extraction_failed") as notify:
            at.reap_stale_running_task()
        self.last_db = db
        self.last_notify = notify
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
        db.activity_event.find.return_value = []
        db.activity_event.update_many.return_value = MagicMock(modified_count=0)
        db.approval_request.find.return_value = []
        with patch.object(at, "_get_db", return_value=db), \
             patch.object(at, "_resolve_stale_threshold_minutes", return_value=30):
            at.reap_stale_running_task()

        update = db.activity_event.update_many.call_args_list[1][0][1]
        assert update["$unset"] == {"meta_summary.pending_review_uuid": ""}
        assert update["$set"]["status"] == "failed"

    def test_the_flip_stamps_the_bell_marker(self):
        """The bell fires later, off this marker — never off a pre-flip
        snapshot, which belled runs that completed in the race window."""
        self._reap()
        update = self.last_db.activity_event.update_many.call_args_list[0][0][1]
        assert "meta_summary.reaper_flipped_at" in update["$set"]

    def test_a_conclusively_dead_extraction_rings_the_owners_bell_once(self):
        """A reaped run previously failed in total silence. The bell keys off
        rows that are STILL failed long after the flip — extractions report
        no mid-run progress, so a fresh flip may just be a slow run — and an
        atomic claim keeps overlapping ticks from double-ringing."""
        self._reap(bell_rows=[{
            "_id": "a1", "user_id": "u1",
            "search_set_uuid": "ss-1", "title": "Award terms",
        }])
        self.last_notify.assert_called_once()
        kwargs = self.last_notify.call_args.kwargs
        assert kwargs["user_id"] == "u1"
        assert kwargs["search_set_uuid"] == "ss-1"
        assert kwargs["search_set_name"] == "Award terms"
        # The claim was taken before ringing.
        claim = self.last_db.activity_event.update_one.call_args[0]
        assert claim[0]["meta_summary.reap_notified"] == {"$ne": True}
        assert claim[1]["$set"]["meta_summary.reap_notified"] is True

    def test_a_lost_claim_race_means_no_bell(self):
        self._reap(
            bell_rows=[{"_id": "a1", "user_id": "u1",
                        "search_set_uuid": "ss-1", "title": "T"}],
            claim_modified=0,
        )
        self.last_notify.assert_not_called()

    def test_bell_query_selects_still_failed_extraction_rows_only(self):
        """Workflow runs are notified by reap_stale_workflow_runs_task with
        run-level truth; ringing here too would double the bell. And a row
        the completion write overwrote (status no longer failed) must never
        ring — its results are on the user's screen."""
        import app.tasks.activity_tasks as at

        self._reap()
        self.last_notify.assert_not_called()
        find_filter = self.last_db.activity_event.find.call_args[0][0]
        assert find_filter["type"] == "search_set_run"
        assert find_filter["status"] == "failed"
        assert find_filter["meta_summary.reap_notified"] == {"$ne": True}
        cutoff = find_filter["meta_summary.reaper_flipped_at"]["$lte"]
        import datetime as dt
        age = dt.datetime.now(dt.timezone.utc) - cutoff
        assert abs(age.total_seconds() - at._EXTRACTION_BELL_DELAY_SECONDS) < 5


class TestReapStaleWorkflowRuns:
    """A worker that dies mid-run (OOM, hard time limit, deploy) leaves the
    WorkflowResult at "running" with no failure handler ever firing. The SSE
    poller returns only on terminal status, so it streamed forever and Run
    History spun indefinitely. This reaper is the backstop.
    """

    def _reap(self, stuck=(), parked=(), approved_old=(), flip_modified=1):
        import app.tasks.activity_tasks as at

        db = MagicMock()
        # First find: the heartbeat/never-started sweep. Second: pending_approval.
        db.workflow_result.find.side_effect = [list(stuck), list(parked)]
        db.workflow_result.update_one.return_value = MagicMock(
            modified_count=flip_modified,
        )
        db.activity_event.find_one_and_update.return_value = {"user_id": "runner"}
        # The batched approval lookup: uuids of approvals that are approved
        # AND older than the stale cutoff (the query pushes both predicates
        # to the server).
        db.approval_request.find.return_value = [{"uuid": u} for u in approved_old]
        db.workflow.find_one.return_value = {"name": "WF", "user_id": "owner"}
        with patch.object(at, "_get_db", return_value=db), \
             patch("app.services.failure_notifications.notify_workflow_failed") as notify:
            at.reap_stale_workflow_runs_task()
        return db, notify

    def _run(self, **over):
        base = {
            "_id": ObjectId(), "workflow": ObjectId(),
            "session_id": "s1", "status": "running",
            "last_progress_at": "old",
        }
        base.update(over)
        return base

    def test_sweep_query_matches_dead_heartbeats_and_never_started_rows(self):
        db, _ = self._reap()
        query = db.workflow_result.find.call_args_list[0][0][0]
        stale, never_started = query["$or"]
        assert stale["status"] == "running"
        assert "$lt" in stale["last_progress_at"]
        # `None` matches null or missing, so rows predating the heartbeat
        # field fall into the gentler day-old sweep, not the strict one.
        assert never_started["last_progress_at"] is None
        assert "$lt" in never_started["start_time"]

    def test_dead_run_is_failed_synced_to_rail_and_notifies_owner(self):
        run = self._run()
        db, notify = self._reap(stuck=[run])

        flip_filter, flip_update = db.workflow_result.update_one.call_args[0]
        assert flip_filter == {"_id": run["_id"], "status": "running"}
        assert flip_update["$set"]["status"] == "error"

        rail_filter = db.activity_event.find_one_and_update.call_args[0][0]
        assert {"workflow_result": run["_id"]} in rail_filter["$or"]
        assert {"workflow_session_id": "s1"} in rail_filter["$or"]

        notify.assert_called_once()
        assert notify.call_args.kwargs["user_id"] == "runner"

    def test_a_run_that_finished_between_find_and_flip_is_left_alone(self):
        """The flip filters on the status the sweep matched; zero modified
        means the run reached a real terminal state first — no bell."""
        db, notify = self._reap(stuck=[self._run()], flip_modified=0)
        db.activity_event.find_one_and_update.assert_not_called()
        notify.assert_not_called()

    def test_approved_but_never_resumed_run_is_reaped(self):
        """approve_review dispatches a resume message and returns. If that
        message is lost the run sits at pending_approval forever while the
        reviewer believes they released it."""
        run = self._run(status="pending_approval", approval_request_id="ap-1")
        run.pop("last_progress_at")
        db, notify = self._reap(parked=[run], approved_old=["ap-1"])
        flip_filter, flip_update = db.workflow_result.update_one.call_args[0]
        assert flip_filter["status"] == "pending_approval"
        assert "approved but never resumed" in flip_update["$set"]["error"]
        notify.assert_called_once()

    def test_approval_lookup_is_one_batched_server_side_query(self):
        """Expired-undecided reviews leave their run parked forever by design,
        so the pending_approval set grows with tenant age — a find_one per
        run was an unbounded N+1 every tick. One $in query, with the
        approved/decision-age predicates pushed to the server."""
        runs = [
            dict(self._run(status="pending_approval", approval_request_id=f"ap-{i}"))
            for i in range(3)
        ]
        for r in runs:
            r.pop("last_progress_at")
        db, _ = self._reap(parked=runs, approved_old=[])
        db.approval_request.find_one.assert_not_called()
        query = db.approval_request.find.call_args[0][0]
        assert set(query["uuid"]["$in"]) == {"ap-0", "ap-1", "ap-2"}
        assert query["status"] == "approved"
        assert "$lt" in query["decision_at"]

    def test_a_run_whose_review_is_not_approved_and_old_is_left_alone(self):
        """Pending, rejected, and expired reviews (and recent approvals) all
        fall out of the batched query, so their runs stay parked."""
        run = self._run(status="pending_approval", approval_request_id="ap-1")
        run.pop("last_progress_at")
        db, notify = self._reap(parked=[run], approved_old=[])
        db.workflow_result.update_one.assert_not_called()
        notify.assert_not_called()

    def test_historical_backlog_is_flipped_silently(self):
        """The first sweep on a mature install finds every run stranded
        before this reaper existed. Flip them — housekeeping — but thirty
        unread bells about runs from last spring is noise, not disclosure."""
        import datetime as dt

        ancient = self._run(
            last_progress_at=None,
            start_time=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90),
        )
        db, notify = self._reap(stuck=[ancient])
        # Flipped...
        assert db.workflow_result.update_one.call_args[0][1]["$set"]["status"] == "error"
        # ...but no bell.
        notify.assert_not_called()

    def test_workflow_doc_is_fetched_with_a_projection_and_cached(self):
        """notify reads only name and user_id; a workflow document drags
        validation plans that can run to hundreds of KB, and a worker-crash
        batch reaps many runs of the same workflow."""
        wf_id = ObjectId()
        runs = [self._run(workflow=wf_id), self._run(workflow=wf_id)]
        db, notify = self._reap(stuck=runs)
        assert notify.call_count == 2
        db.workflow.find_one.assert_called_once()
        projection = db.workflow.find_one.call_args[0][1]
        assert projection == {"name": 1, "user_id": 1}

    def test_legacy_string_workflow_id_still_resolves_an_owner(self):
        """Rows migrated from the Flask era stored workflow as a string; an
        unconverted lookup found nothing and the failure notified nobody."""
        wf_id = ObjectId()
        run = self._run(workflow=str(wf_id))
        db, notify = self._reap(stuck=[run])
        looked_up = db.workflow.find_one.call_args[0][0]["_id"]
        assert looked_up == wf_id
        notify.assert_called_once()


class TestWorkflowTasksAckLate:
    """Workers ack on delivery by default, so a worker death loses the message
    for good and no failure path ever runs. These two tasks are safe to
    redeliver — resume-at-step skips completed steps and the atomic
    finalized_at claim keeps side effects single-shot — so they opt in. Other
    task families have NOT been audited for idempotency; do not widen this to
    a global setting.
    """

    def test_execution_and_resume_ack_late_and_requeue_on_worker_loss(self):
        import app.tasks.workflow_tasks as wt

        for task in (wt.execute_workflow_task, wt.resume_workflow_after_approval):
            assert task.acks_late is True
            assert task.reject_on_worker_lost is True

    def test_visibility_timeout_outlives_the_hard_time_limit(self):
        """The Redis transport redelivers any message unacked past
        visibility_timeout, and kombu's DEFAULT (3600s) is shorter than the
        hard time limit — a 61-minute run would be handed to a second worker
        while the first was still executing it. acks_late without this
        override is not safe to ship."""
        from app.celery_app import celery

        vt = celery.conf.broker_transport_options["visibility_timeout"]
        assert vt > celery.conf.task_time_limit * 2

    def _execute_db(self, result_doc):
        db = MagicMock()
        db.workflow.find_one.return_value = {"_id": ObjectId(), "user_id": "u1"}
        db.workflow_result.find_one.return_value = result_doc
        return db

    def test_a_terminal_run_is_not_resurrected_by_a_late_delivery(self):
        """A visibility-timeout redelivery (or requeue) arriving after the
        user canceled — or the reaper failed — the run must no-op, not flip
        it back to running and finish a run the user explicitly stopped."""
        import app.tasks.workflow_tasks as wt

        db = self._execute_db({"status": "canceled"})
        with patch.object(wt, "_get_db", return_value=db):
            out = wt.execute_workflow_task("6" * 24, "7" * 24, {}, "m")
        assert out["status"] == "skipped_terminal"
        db.workflow_result.find_one_and_update.assert_not_called()
        db.workflow_result.update_one.assert_not_called()

    def test_the_poison_message_loop_is_bounded(self):
        """reject_on_worker_lost requeues with a fresh retry counter, so a
        run that OOM-kills its worker every time would loop forever — and
        every pass rewrites last_progress_at, blinding the heartbeat reaper.
        The per-run delivery counter is what stops it."""
        import app.tasks.workflow_tasks as wt

        db = self._execute_db({"status": "queued"})
        db.workflow_result.find_one_and_update.return_value = {
            "delivery_attempts": wt.MAX_DELIVERY_ATTEMPTS + 1,
        }
        with patch.object(wt, "_get_db", return_value=db), \
             patch.object(wt, "_mark_workflow_failed") as mark:
            out = wt.execute_workflow_task("6" * 24, "7" * 24, {}, "m")
        assert out["status"] == "error"
        mark.assert_called_once()
        assert "crashed the worker" in mark.call_args[0][3]

    def test_resume_refuses_a_run_the_reaper_already_finalized(self):
        """The resume guard is a positive status filter: a late resume
        delivery for a run already failed (approved-but-never-resumed reap)
        must not execute the post-gate steps after the owner was told to
        re-run it."""
        import app.tasks.workflow_tasks as wt

        db = MagicMock()
        db.approval_request.find_one.return_value = {
            "uuid": "ap-1", "status": "approved",
            "workflow_result_id": ObjectId(), "workflow_id": ObjectId(),
            "step_index": 1,
        }
        db.workflow.find_one.return_value = {"_id": ObjectId(), "user_id": "u1"}
        db.workflow_result.find_one.return_value = {"input_context": {}, "status": "error"}
        db.system_config.find_one.return_value = {}
        db.user.find_one.return_value = None
        db.workflow_result.update_one.return_value = MagicMock(matched_count=0)
        with patch.object(wt, "_get_db", return_value=db), \
             patch.object(wt, "_build_steps_data", return_value=([], [])):
            out = wt.resume_workflow_after_approval("ap-1")
        assert out["status"] == "canceled"
        resumed_filter = db.workflow_result.update_one.call_args[0][0]
        assert resumed_filter["status"] == {"$in": ["pending_approval", "running"]}
