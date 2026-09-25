"""Celery task for generating short LLM descriptions for activity events.

Ported from Flask app/utilities/activity_description.py.
Uses pymongo (sync) for DB access.
"""

import datetime
import logging
import re

from pydantic_ai.exceptions import ModelAPIError

from app.celery_app import celery_app
from app.models.activity import ActivityType
from app.tasks import TRANSIENT_EXCEPTIONS, run_task_async

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

# How long a reaper-flipped extraction row must STAY failed before its owner
# is belled. Extractions report no mid-run progress, so the elapsed-time flip
# above catches slow runs too (their completion write then corrects the rail);
# a row still failed this long after the flip is past any legitimate runtime
# (the Celery hard time limit is 3660s) and genuinely dead.
_EXTRACTION_BELL_DELAY_SECONDS = 5400

_REAPED_EXTRACTION_ERROR = (
    "Timed out — the run stopped reporting progress and never finished. The "
    "worker likely crashed or was restarted mid-run."
)


def _bell_reaped_extraction(db, row: dict) -> None:
    """Tell an extraction's owner that the rail reaper failed its run."""
    from app.services.failure_notifications import notify_extraction_failed

    notify_extraction_failed(
        db,
        user_id=row.get("user_id"),
        search_set_uuid=row.get("search_set_uuid"),
        search_set_name=row.get("title"),
        error=_REAPED_EXTRACTION_ERROR,
    )


# Who tells the owner when a reaper fails a row of this type. A type missing
# here is a test failure, not a silent default: adding an activity type is a
# decision about disclosure, made here and nowhere else.
#
#   callable        — this reaper rings it, from the delayed bell sweep in
#                     reap_stale_running_task, once per row.
#   OWNED_ELSEWHERE — another reaper owns the row's truth and rings the bell;
#                     this reaper may flip the rail row but must stay silent.
#   None            — silent by design.
OWNED_ELSEWHERE = "owned_elsewhere"
REAP_BELL_OWNERS: dict = {
    # Extraction's only backstop: its task's final-attempt bell never fires
    # when the worker dies without running a handler.
    ActivityType.SEARCH_SET_RUN.value: _bell_reaped_extraction,
    # reap_stale_workflow_runs_task owns the WorkflowResult and notifies once,
    # with run-level truth (and the automation owner for scheduled runs).
    ActivityType.WORKFLOW_RUN.value: OWNED_ELSEWHERE,
    # The user was watching the stream drop.
    ActivityType.CONVERSATION.value: None,
    # Written already-terminal by quality_tasks; never running, never reaped.
    ActivityType.QUALITY_ALERT.value: None,
}


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
    """Get sync pymongo database handle (shared per-process client)."""
    from app.tasks import get_sync_db

    return get_sync_db()


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
        # No activity_id: this runs after the activity is finalized, and flush
        # $sets activity token totals — linking it would clobber the real
        # workflow/chat/extraction total with the tiny title-gen count. The
        # ledger still meters it (attributed to the user).
        from app.services.metering import metered
        # Run the agent in a dedicated event loop rather than run_sync's ambient
        # one: run_sync grabs asyncio.get_event_loop(), which can hand back a
        # closed loop left by a prior async task in this worker ("Event loop is
        # closed"). run_task_async also releases the loop's pooled httpx client,
        # which run_sync would otherwise leak (FD exhaustion).
        with metered("title_gen", user_id=user_id, team_id=activity.get("team_id")):
            result = run_task_async(chat_agent.run(prompt))
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

    except ModelAPIError as e:
        # Title generation is best-effort cosmetic enrichment; an LLM outage —
        # e.g. the configured endpoint is unreachable ("Connection error.") or a
        # misconfigured model returns 4xx (ModelHTTPError is a ModelAPIError
        # subclass) — is a handled degradation: the activity just goes untitled.
        # Log at warning so it doesn't page Sentry as a fault.
        logger.warning(
            "Skipping description for activity %s — model unavailable: %s",
            activity_id, e,
        )
        _mark_done()

    except Exception as e:
        logger.error("Error generating description for activity %s: %s", activity_id, e, exc_info=True)
        _mark_done()


def _as_utc(value):
    """Sync pymongo hands back naive datetimes; compare them as UTC."""
    if value is not None and getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


def _workflow_rail_rows_without_live_run(db, rail_rows: list[dict], cutoff) -> list[dict]:
    """Return the workflow_run rail rows whose WorkflowResult is not alive.

    The run's ``last_progress_at`` is the one clock (see
    reap_stale_running_task). A rail row is kept at "running" when its run has
    heartbeated since ``cutoff`` or sits at ``pending_approval`` — a state the
    run reaper's approved-but-never-resumed sweep owns. A rail row with no
    linked run at all (the run was never created, or the row predates the
    link fields) has nothing to follow and is flipped as before. Linked by the
    result id when the run got far enough to set it, by session otherwise —
    the same ``rail_or`` pairing reap_stale_workflow_runs_task uses in the
    other direction. One batched lookup, not a find_one per row.
    """
    result_ids = [r["workflow_result"] for r in rail_rows if r.get("workflow_result")]
    session_ids = [
        r["workflow_session_id"] for r in rail_rows if r.get("workflow_session_id")
    ]
    link_or = []
    if result_ids:
        link_or.append({"_id": {"$in": result_ids}})
    if session_ids:
        link_or.append({"session_id": {"$in": session_ids}})
    if not link_or:
        return list(rail_rows)

    runs = list(db.workflow_result.find(
        {"$or": link_or},
        {"session_id": 1, "status": 1, "last_progress_at": 1},
    ))
    by_id = {run["_id"]: run for run in runs}
    by_session = {run["session_id"]: run for run in runs if run.get("session_id")}

    def _is_live(run: dict) -> bool:
        if run.get("status") == "pending_approval":
            return True
        heartbeat = _as_utc(run.get("last_progress_at"))
        return heartbeat is not None and heartbeat >= cutoff

    dead = []
    for row in rail_rows:
        run = by_id.get(row.get("workflow_result")) or by_session.get(
            row.get("workflow_session_id"),
        )
        if run is None or not _is_live(run):
            dead.append(row)
    return dead


@celery_app.task(bind=True, name="tasks.activity.reap_stale_running")
def reap_stale_running_task(self) -> None:
    """Mark activity events stuck in running/queued as failed.

    Catches orphans from crashed workers, dropped chat streams, and Celery soft
    time limits that killed a task before its exception handler could update the
    activity record. Without this, the activity rail spins forever and the user
    has to delete the item manually.

    Runs parked on a human approval gate are exempt: they carry
    ``meta_summary.pending_review_uuid`` and stop reporting progress by design,
    so reaping on elapsed time marked every review left overnight as a timeout.
    The approval paths (resume, reject, expire) clear the marker, which puts the
    row back under this sweep.

    One clock for workflow runs. A workflow run has two rows — the rail row
    here and the WorkflowResult — written by different writers on different
    cadences. The rail row's ``last_updated_at`` is refreshed by the same
    progress writes that stamp the run's ``last_progress_at``, but the two
    reapers used different thresholds (this one ~30 min, the run reaper 2×
    the hard time limit), so a long step could see the rail flipped to
    "failed" while the run stayed "running" and the SSE poller kept streaming
    — the rail contradicting the run it describes (#835). The run's
    ``last_progress_at`` is the authoritative clock and the rail follows it:
    a workflow_run rail row is only flipped here when its run has no
    heartbeat newer than this sweep's cutoff (or no run at all), and never
    when the run reaper owns the row's fate (``pending_approval``).
    """
    db = _get_db()
    threshold_minutes = _resolve_stale_threshold_minutes(db)
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=threshold_minutes,
    )
    now = datetime.datetime.now(datetime.timezone.utc)

    stale_filter = {
        "status": {"$in": ["running", "queued"]},
        "last_updated_at": {"$lt": cutoff},
        # Matches rows where the field is null *or* absent.
        "meta_summary.pending_review_uuid": None,
    }

    # Fetch the candidates rather than flipping blind: workflow_run rows have
    # a second clock to consult before the verdict (see the docstring).
    candidates = list(db.activity_event.find(
        stale_filter,
        {"type": 1, "workflow_result": 1, "workflow_session_id": 1},
    ))
    workflow_rows = [
        r for r in candidates if r.get("type") == ActivityType.WORKFLOW_RUN.value
    ]
    to_flip = [
        r["_id"] for r in candidates
        if r.get("type") != ActivityType.WORKFLOW_RUN.value
    ]
    if workflow_rows:
        to_flip.extend(
            r["_id"] for r in _workflow_rail_rows_without_live_run(
                db, workflow_rows, cutoff,
            )
        )

    # The flip stamps reaper_flipped_at so the bell sweep at the bottom can
    # notify — later, and only if the verdict stands. Ringing here off a
    # pre-flip snapshot had two failure modes: an extraction that completed
    # between the find and the update_many got a timeout bell for results
    # already on screen, and (because extractions report no mid-run progress)
    # a merely *slow* run past the threshold got belled and then finished.
    # The status guard is kept on the write: a row that completed between the
    # find and here is left alone.
    flipped_count = 0
    if to_flip:
        result = db.activity_event.update_many(
            {"_id": {"$in": to_flip}, "status": {"$in": ["running", "queued"]}},
            {
                "$set": {
                    "status": "failed",
                    "finished_at": now,
                    "last_updated_at": now,
                    "meta_summary.reaper_flipped_at": now,
                    "error": (
                        f"Timed out — no progress reported for over "
                        f"{threshold_minutes} minutes."
                    ),
                },
            },
        )
        flipped_count = result.modified_count

    # A row parked on a review is exempt from the sweep above, but only while
    # that review is actually pending. approve_review returns as soon as the
    # resume task is dispatched, and the marker is cleared deep inside that
    # task — after guards that raise on "Approval not found", "is not approved"
    # and "Workflow or result not found". If the workflows worker is down when
    # the message is sent, the message is lost, or any guard trips, the marker
    # stays and the row sits at "running" forever: precisely the condition this
    # reaper exists to catch, made unreachable by its own exemption.
    pending_uuids = [
        a["uuid"]
        for a in db.approval_request.find({"status": "pending"}, {"uuid": 1})
        if a.get("uuid")
    ]
    orphaned = db.activity_event.update_many(
        {
            "status": {"$in": ["running", "queued"]},
            "last_updated_at": {"$lt": cutoff},
            # Carries a marker, but not one of a review still awaiting a decision.
            "meta_summary.pending_review_uuid": {"$nin": [None, *pending_uuids]},
        },
        {
            "$set": {
                "status": "failed",
                "finished_at": now,
                "last_updated_at": now,
                "error": (
                    "Timed out — the review this run was waiting on is no "
                    "longer pending and the run never resumed."
                ),
            },
            "$unset": {"meta_summary.pending_review_uuid": ""},
        },
    )

    if flipped_count or orphaned.modified_count:
        logger.info(
            "Reaped %d stale activity events and %d parked on a decided review "
            "(threshold=%d min)",
            flipped_count, orphaned.modified_count, threshold_minutes,
        )

    # Bell sweep: tell owners about reaped runs, once, and only when the
    # reaper's verdict is conclusive. Which types ring is REAP_BELL_OWNERS'
    # call, not this loop's — only types whose entry is a callable are
    # queried. Extractions report no mid-run progress, so the flip above
    # happens for slow runs too, and the completion write then corrects the
    # rail. The bell therefore waits _EXTRACTION_BELL_DELAY_SECONDS after the
    # flip: no task outlives the Celery hard time limit, so a row still
    # failed then is genuinely dead. The atomic reap_notified claim makes the
    # bell fire exactly once even across overlapping ticks.
    bell_cutoff = now - datetime.timedelta(seconds=_EXTRACTION_BELL_DELAY_SECONDS)
    belled_types = [
        type_value for type_value, owner in REAP_BELL_OWNERS.items()
        if callable(owner)
    ]
    bell_rows = list(db.activity_event.find(
        {
            "type": {"$in": belled_types},
            "status": "failed",
            "meta_summary.reaper_flipped_at": {"$lte": bell_cutoff},
            "meta_summary.reap_notified": {"$ne": True},
        },
        {"type": 1, "user_id": 1, "search_set_uuid": 1, "title": 1},
    )) if belled_types else []
    for row in bell_rows:
        try:
            bell = REAP_BELL_OWNERS.get(row.get("type"))
            if not callable(bell):
                continue
            claimed = db.activity_event.update_one(
                {"_id": row["_id"], "meta_summary.reap_notified": {"$ne": True}},
                {"$set": {"meta_summary.reap_notified": True}},
            )
            if not claimed.modified_count:
                continue
            bell(db, row)
        except Exception:
            logger.exception(
                "Failed to notify owner of reaped %s activity %s",
                row.get("type"), row.get("_id"),
            )


# WorkflowResult rows need their own sweep, separate from the rail sweep
# above: the rail row and the run document are updated by different writers,
# and when a worker dies neither gets a terminal status. passive_tasks fixed
# this for automation-triggered runs on their retry-exhausted path; a manual
# run had no equivalent, so the SSE poller (which returns only on terminal
# status) streamed forever and the Run History spinner never stopped.
#
# Thresholds: a workflow task cannot legitimately run longer than the Celery
# hard time limit (3660s), so a run whose heartbeat is older than twice that
# is dead, full stop. A run with no heartbeat at all was never picked up —
# either the broker dropped the message or the row predates the field — and
# gets a full day, because batch runs are rate-limited to 1/s and a large
# batch legitimately sits queued for hours.
STALE_WORKFLOW_RUN_AGE_SECONDS = 3660 * 2
NEVER_STARTED_WORKFLOW_RUN_AGE_SECONDS = 86400


@celery_app.task(bind=True, name="tasks.activity.reap_stale_workflow_runs")
def reap_stale_workflow_runs_task(self) -> None:
    """Mark WorkflowResult rows abandoned by a dead worker as failed.

    Three sweeps:
      1. Picked up but no heartbeat for 2× the hard time limit — the worker
         was OOM-killed, hard-limit SIGKILLed, or replaced by a deploy.
      2. Never picked up and older than a day — the broker lost the message.
      3. Parked at ``pending_approval`` although its approval was approved
         hours ago — the resume message was lost, so the run every reviewer
         believes they released never moved again.

    Each reaped run also fails its activity-rail row (so rail and run agree)
    and rings the owner's bell exactly once, from here — the rail reaper
    above deliberately stays silent about workflow runs.

    Runs on the default queue on purpose: parking it on the workflows queue
    would let the very worker outage it exists to detect also silence it.
    """
    # This task is the bell for workflow runs; the contract map must agree,
    # or a rail-side change would double the bell (or drop it) unnoticed.
    assert REAP_BELL_OWNERS.get(ActivityType.WORKFLOW_RUN.value) is OWNED_ELSEWHERE, (
        "reap_stale_workflow_runs_task rings the workflow_run bell; "
        "REAP_BELL_OWNERS must mark that type OWNED_ELSEWHERE"
    )
    db = _get_db()
    now = datetime.datetime.now(datetime.timezone.utc)
    progress_cutoff = now - datetime.timedelta(seconds=STALE_WORKFLOW_RUN_AGE_SECONDS)
    queued_cutoff = now - datetime.timedelta(
        seconds=NEVER_STARTED_WORKFLOW_RUN_AGE_SECONDS,
    )

    stuck = list(db.workflow_result.find(
        {"$or": [
            {"status": "running", "last_progress_at": {"$lt": progress_cutoff}},
            # `None` matches a null or missing field, so rows written before
            # last_progress_at existed land in this gentler sweep too.
            {
                "status": {"$in": ["queued", "running"]},
                "last_progress_at": None,
                "start_time": {"$lt": queued_cutoff},
            },
        ]},
        {"workflow": 1, "session_id": 1, "status": 1, "last_progress_at": 1,
         "start_time": 1, "is_passive": 1, "trigger_type": 1, "automation_id": 1,
         "input_context.automation_id": 1, "input_context.automation_name": 1},
    ))

    # Sweep 3: approved at the gate, never resumed. The reject and expire
    # paths update the run through approval_service, so "approved" is the only
    # decision that strands a run at pending_approval when the resume message
    # is lost. The decision must be old enough that an in-flight resume (or a
    # backed-off Celery retry of one) cannot still be coming. One batched
    # lookup, not a find_one per run: expired-undecided reviews deliberately
    # leave their run parked forever (TIMEOUT_NONE), so the pending_approval
    # set grows monotonically with tenant age and would otherwise cost N
    # round trips per tick.
    parked = list(db.workflow_result.find(
        {"status": "pending_approval"},
        {"workflow": 1, "session_id": 1, "approval_request_id": 1, "status": 1,
         "start_time": 1, "is_passive": 1, "trigger_type": 1, "automation_id": 1,
         "input_context.automation_id": 1, "input_context.automation_name": 1},
    ))
    if parked:
        approved_old = {
            a["uuid"]
            for a in db.approval_request.find(
                {
                    "uuid": {"$in": [
                        r.get("approval_request_id") for r in parked
                        if r.get("approval_request_id")
                    ]},
                    "status": "approved",
                    "decision_at": {"$lt": progress_cutoff},
                },
                {"uuid": 1},
            )
        }
        stuck.extend(
            r for r in parked if r.get("approval_request_id") in approved_old
        )

    # A worker-crash batch reaps many runs of the same workflow; fetch each
    # workflow once, and only the two fields the notifier reads (a workflow
    # document drags validation plans and configs that can run to hundreds
    # of KB).
    workflow_cache: dict = {}

    def _workflow_doc(raw_id) -> dict:
        if isinstance(raw_id, str):
            # Rows migrated from the Flask era stored the id as a string; an
            # unconverted lookup finds nothing and the failure notified nobody.
            from bson import ObjectId

            try:
                raw_id = ObjectId(raw_id)
            except Exception:
                return {}
        if raw_id not in workflow_cache:
            workflow_cache[raw_id] = db.workflow.find_one(
                {"_id": raw_id}, {"name": 1, "user_id": 1},
            ) or {}
        return workflow_cache[raw_id]

    # A scheduled automation has no one watching it, so the bell must reach
    # the person who set the schedule — who need not own the workflow. This
    # mirrors passive_tasks' retry-exhausted path, which is the only other
    # place a passive run is failed. Cached per sweep like the workflow docs:
    # a nightly automation that dies every night reaps as a batch. Runs
    # written before WorkflowResult.automation_id existed carry the same id
    # in input_context (the trigger context has always been copied there),
    # so they resolve too; a passive run with neither keeps today's fallback
    # — the workflow owner's bell.
    automation_cache: dict = {}

    def _automation_doc(run: dict) -> dict:
        if not (run.get("is_passive") or run.get("trigger_type")):
            return {}
        ctx = run.get("input_context") or {}
        automation_id = run.get("automation_id") or ctx.get("automation_id")
        if not automation_id:
            return {}
        if automation_id not in automation_cache:
            from app.tasks.passive_tasks import _find_automation

            automation_cache[automation_id] = _find_automation(db, automation_id) or {}
        return automation_cache[automation_id]

    # A mature install's first sweep finds every run stranded before this
    # reaper existed — months of history. Flip them (housekeeping), but only
    # ring the bell for recent ones: thirty unread "Workflow failed" bells
    # about runs from last spring is noise, not disclosure.
    notify_floor = now - datetime.timedelta(days=7)

    reaped = 0
    for run in stuck:
        try:
            if run.get("status") == "pending_approval":
                error_msg = (
                    "This run was approved but never resumed — the message "
                    "asking a worker to continue it was lost. Run the "
                    "workflow again."
                )
            elif run.get("last_progress_at") is None:
                error_msg = (
                    "This run was never picked up by a worker. Run the "
                    "workflow again."
                )
            else:
                error_msg = (
                    "The worker running this workflow stopped reporting "
                    "progress and never finished — it likely crashed or was "
                    "restarted mid-run. Run the workflow again."
                )

            # Guard on the status we matched: a run that completed, failed, or
            # was canceled between the find and this write is left alone.
            flipped = db.workflow_result.update_one(
                {"_id": run["_id"], "status": run.get("status")},
                {"$set": {"status": "error", "error": error_msg}},
            )
            if not flipped.modified_count:
                continue
            reaped += 1

            # Bring the rail row into agreement. Matched by the result link
            # when the run got far enough to set it, by session otherwise.
            rail_or = [{"workflow_result": run["_id"]}]
            if run.get("session_id"):
                rail_or.append({"workflow_session_id": run["session_id"]})
            rail = db.activity_event.find_one_and_update(
                {"$or": rail_or, "status": {"$in": ["running", "queued"]}},
                {
                    "$set": {
                        "status": "failed",
                        "error": error_msg,
                        "finished_at": now,
                        "last_updated_at": now,
                    },
                    "$unset": {"meta_summary.pending_review_uuid": ""},
                },
                projection={"user_id": 1},
            )
            if rail is None:
                # Already reaped by the rail sweep, or the run had no rail row
                # (passive runs). Still need the owner for the bell.
                rail = db.activity_event.find_one(
                    {"$or": rail_or}, {"user_id": 1},
                )

            started = run.get("start_time")
            if started is not None and started.tzinfo is None:
                started = started.replace(tzinfo=datetime.timezone.utc)
            if started is not None and started < notify_floor:
                continue

            from app.services.failure_notifications import notify_workflow_failed

            automation_doc = _automation_doc(run)
            if automation_doc:
                # "Automation failed: <name>" to the person who scheduled it.
                notify_workflow_failed(
                    db,
                    workflow_doc=_workflow_doc(run.get("workflow")),
                    error=error_msg,
                    user_id=automation_doc.get("user_id"),
                    automation_name=(
                        (run.get("input_context") or {}).get("automation_name")
                        or automation_doc.get("name")
                        or None
                    ),
                )
            else:
                notify_workflow_failed(
                    db,
                    workflow_doc=_workflow_doc(run.get("workflow")),
                    error=error_msg,
                    user_id=(rail or {}).get("user_id"),
                )
        except Exception:
            logger.exception("Failed to reap stale workflow run %s", run.get("_id"))

    if reaped:
        logger.info("Reaped %d stale workflow run(s)", reaped)
