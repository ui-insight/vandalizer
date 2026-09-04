"""Celery tasks for workflow execution.

Uses pymongo (sync) for DB access  - same pattern as Flask Celery workers.
Task names use 'tasks.workflow_next.*' to coexist with Flask's 'tasks.workflow.*'.
"""

import logging

from app.celery_app import celery_app
from app.services.form_fill import DOC_META_TASKS, document_meta
from app.exceptions import TrialSpendBlockedError
from app.tasks import TRANSIENT_EXCEPTIONS

logger = logging.getLogger(__name__)

# Ceiling on how many times one run may be delivered to a worker. Legitimate
# paths spend a handful (first delivery + up to max_retries retries + a rare
# broker redelivery); a run that keeps OOM-killing its worker is requeued by
# reject_on_worker_lost with a fresh retry counter each time and would loop
# forever without this — invisible to the heartbeat reaper, since every pass
# rewrites last_progress_at.
MAX_DELIVERY_ATTEMPTS = 8


def _preload_form_filler_template(db, task_data: dict) -> None:
    """Attach a Form Filler task's fillable-PDF template bytes (see form_fill)."""
    from app.config import Settings
    from app.services.form_fill import load_form_filler_assets

    load_form_filler_assets(db, task_data, upload_dir=Settings().upload_dir)


def _wants_selected_document(task_data: dict) -> bool:
    """Whether the task expects `selected_doc_text` to be pre-loaded.

    True if `select_document` appears in the new `input_sources` list, or
    in the legacy single `input_source` field.
    """
    sources = task_data.get("input_sources")
    if isinstance(sources, list) and "select_document" in sources:
        return True
    return task_data.get("input_source") == "select_document"


def _resolve_saved_prompt_formatter(db, task_name: str, task_data: dict) -> None:
    """Resolve a linked saved Prompt/Formatter into the inline body in-place.

    Prompt and Formatter steps may link a standalone Library prompt/formatter
    (a SearchSet with set_type 'prompt'/'formatter'). The body lives in the
    set's first item (`searchphrase`, materialized on edit) or, for sets never
    edited since creation, in `extraction_config.content`. Resolving here — the
    same task-data prep layer that resolves extraction sets — keeps the saved
    item the single source of truth so edits propagate to every linked workflow.

    Mirrors the extraction resolver's silent fallback: if the set is missing the
    inline value is left as-is (PromptNode/FormatNode handle empties).
    """
    if task_name == "Prompt":
        link_field, body_field = "saved_prompt_uuid", "prompt"
    elif task_name in ("Formatter", "Format"):
        link_field, body_field = "saved_formatter_uuid", "format_template"
    else:
        return

    uuid = task_data.get(link_field)
    if not uuid:
        return
    ss = db.search_set.find_one({"uuid": uuid})
    if not ss:
        return
    item = db.search_set_item.find_one({"searchset": uuid})
    body = item.get("searchphrase") if item else None
    if not body:
        body = (ss.get("extraction_config") or {}).get("content")
    if body:
        task_data[body_field] = body


def _notify_approval_reviewers_sync(
    db, assigned_user_ids: list[str], workflow_name: str,
    step_name: str, instructions: str, approval_uuid: str,
) -> None:
    """Create in-app notifications and send emails to assigned reviewers (sync context)."""
    from app.config import Settings
    from app.services.notification_service import create_notification_sync

    settings = Settings()

    emails: list[tuple[str, str, str, str]] = []  # (user_id, to, subject, html)

    for user_id in assigned_user_ids:
        # In-app notification
        create_notification_sync(
            db,
            user_id=user_id,
            kind="approval_request",
            title=f"Approval needed: {workflow_name}",
            body=f'Step "{step_name}" is waiting for your review.',
            link=f"/reviews/{approval_uuid}",
        )

        # Email — rendered here, sent below on one loop for all reviewers.
        user_doc = db.user.find_one({"user_id": user_id})
        if user_doc and user_doc.get("email"):
            from app.services.email_service import approval_request_email

            subject, html = approval_request_email(
                reviewer_name=user_doc.get("name", user_id),
                workflow_name=workflow_name,
                step_name=step_name,
                instructions=instructions,
                approval_uuid=approval_uuid,
                frontend_url=settings.frontend_url,
            )
            emails.append((user_id, user_doc["email"], subject, html))

    if not emails:
        return

    from app.tasks import run_task_async

    async def _send_all() -> None:
        # send_email reaches Beanie twice — SystemConfig for the deployment's
        # branding, EmailLog for the audit row — and a Motor client is bound to
        # the loop it was created on. This sync task holds only a pymongo
        # handle, so the fresh loop needs its own Beanie init or both calls
        # raise CollectionWasNotInitialized: the mail still went out, but
        # unbranded and unlogged, with two Sentry errors per reviewer.
        # One init per task, not per reviewer — every init_db builds a Motor
        # client, and the other tasks in this package initialise once.
        from app.database import init_db
        from app.services.email_service import send_email

        await init_db(settings, skip_indexes=True)
        for user_id, to, subject, html in emails:
            try:
                await send_email(
                    to, subject, html, settings, email_type="approval_request",
                )
            except Exception:
                logger.exception("Failed to send approval email to %s", user_id)

    try:
        run_task_async(_send_all())
    except Exception:
        logger.exception("Failed to send approval emails for %s", approval_uuid)


def _bson_safe(value):
    """Coerce arbitrary step output into a MongoDB-storable shape.

    `data_for_review` is whatever the previous step emitted, which can include
    bytes, sets, tuples, or custom objects that pymongo cannot encode. A failed
    insert used to escape uncaught and leave the run frozen in "running" with no
    approval record, so anything we can't confidently store is stringified
    rather than allowed to raise.
    """
    import datetime as _dt

    from bson import ObjectId

    if value is None or isinstance(value, (str, bool, int, float, _dt.datetime, ObjectId)):
        return value
    if isinstance(value, dict):
        return {str(k): _bson_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_bson_safe(v) for v in value]
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _default_model_from_config(sys_config: dict) -> str:
    """Resolve the configured default model from a raw SystemConfig dict.

    The sync mirror of :func:`app.services.config_service.get_default_model_name`
    for Celery tasks, which hold the config as a pymongo document rather than a
    Beanie model. Returns "" when no model is configured at all.
    """
    models = [m for m in (sys_config.get("available_models") or []) if isinstance(m, dict)]

    configured_default = (sys_config.get("default_model") or "").strip()
    if configured_default and any(m.get("name") == configured_default for m in models):
        return configured_default

    for m in models:
        if m.get("name"):
            return m["name"]
    return ""


def _build_steps_data(db, workflow_doc, workflow_id, trigger_step_data):
    """Materialize a workflow's steps into engine-ready ``steps_data``.

    Returns ``(steps_data, output_step_names)``.

    Shared by the initial run and every resume pass. These used to be two
    hand-maintained copies and had already drifted apart: the resume copy
    dropped extraction ``field_metadata`` (so enum/optional constraints were
    silently lost after an approval) and the ``input_config`` fixed-documents
    merge (so fixed inputs vanished on resume). A resumed run must execute the
    same configuration the first pass did, so there is one builder.
    """
    from app.services.workflow_engine import sanitize_step_name

    steps_data = [{"name": "Document", "data": trigger_step_data, "tasks": []}]

    # Track which steps the user designated as deliverables.
    output_step_names: list[str] = []

    for step_id in workflow_doc.get("steps", []):
        step_doc = db.workflow_step.find_one({"_id": step_id})
        if not step_doc:
            continue

        if step_doc.get("is_output"):
            output_step_names.append(sanitize_step_name(step_doc.get("name", "")))

        tasks = []
        for task_id in step_doc.get("tasks", []):
            task_doc = db.workflow_step_task.find_one({"_id": task_id})
            if not task_doc:
                continue

            # Resolve extraction keys from search set
            task_data = dict(task_doc.get("data", {}))
            if task_doc.get("name") == "Extraction" and task_data.get("search_set_uuid"):
                ss = db.search_set.find_one({"uuid": task_data["search_set_uuid"]})
                if ss:
                    items = list(db.search_set_item.find({
                        "searchset": task_data["search_set_uuid"],
                        "searchtype": "extraction",
                    }))
                    task_data["keys"] = [item["searchphrase"] for item in items]
                    # Preserve per-field validation (enum_values) and optional
                    # designations (is_optional) so workflow extraction honors the
                    # same constraints as a standalone run. Without this, the saved
                    # set's optional/enum metadata is silently dropped at execution.
                    task_data["field_metadata"] = [
                        {
                            "key": item["searchphrase"],
                            "is_optional": item.get("is_optional", False),
                            "enum_values": item.get("enum_values", []),
                        }
                        for item in items
                    ]
                    # UI is mutually exclusive between saved-set and manual fields,
                    # but older workflows may have both persisted. Drop stale manual
                    # fields so the saved set is unambiguously the source of truth.
                    task_data.pop("extractions", None)

            # Resolve a linked saved Prompt/Formatter into its inline body.
            _resolve_saved_prompt_formatter(db, task_doc.get("name"), task_data)

            # Pre-load doc texts for extraction and prompt nodes
            doc_uuids = list(trigger_step_data.get("doc_uuids", []))

            # Merge fixed documents from workflow input_config — except in
            # "no input" mode, where the workflow runs with no documents at
            # all (leftover fixed docs from a prior mode must not leak in).
            input_cfg = workflow_doc.get("input_config") or {}
            if input_cfg.get("trigger_type") != "no_input":
                fixed_doc_config = input_cfg.get("fixed_documents", [])
                for fd in fixed_doc_config:
                    fd_uuid = fd.get("uuid") if isinstance(fd, dict) else str(fd)
                    if fd_uuid and fd_uuid not in doc_uuids:
                        doc_uuids.append(fd_uuid)

            if doc_uuids:
                doc_texts = []
                doc_metas = []
                for uuid in doc_uuids:
                    doc = db.smart_document.find_one({"uuid": uuid})
                    if doc and doc.get("origin_workflow_id") == workflow_id:
                        logger.info(
                            "Skipping own-origin document %s to prevent workflow self-loop",
                            uuid,
                        )
                        continue
                    if doc and doc.get("raw_text"):
                        doc_texts.append(doc["raw_text"])
                        doc_metas.append(document_meta(doc))
                    else:
                        logger.warning(
                            "Document %s has no raw_text — it may still be processing or text extraction failed",
                            uuid,
                        )
                if not doc_texts:
                    logger.error(
                        "None of the %d input documents have raw_text available — workflow will produce no output",
                        len(doc_uuids),
                    )
                task_data["doc_texts"] = doc_texts
                if task_doc.get("name") in DOC_META_TASKS:
                    # Aligned 1:1 with doc_texts: the fill report and the
                    # extraction source sidecar both attribute a value to a
                    # document and page through these.
                    task_data["doc_metas"] = doc_metas

            # Pre-load specific document text when select_document is selected
            if _wants_selected_document(task_data) and task_data.get("selected_document_uuid"):
                sel_doc = db.smart_document.find_one({"uuid": task_data["selected_document_uuid"]})
                if sel_doc and sel_doc.get("raw_text"):
                    task_data["selected_doc_text"] = sel_doc["raw_text"]
                    if task_doc.get("name") in DOC_META_TASKS:
                        task_data["selected_doc_meta"] = document_meta(sel_doc)

            if task_doc.get("name") == "FormFiller":
                _preload_form_filler_template(db, task_data)

            tasks.append({"name": task_doc.get("name", ""), "data": task_data})

        steps_data.append({
            "name": step_doc.get("name", ""),
            "data": step_doc.get("data", {}),
            "tasks": tasks,
        })

    return steps_data, output_step_names


def _resume_point(engine, result_doc: dict) -> tuple[int, dict | None]:
    """Where a retried run should pick up, and what to feed the first step.

    ``execute_workflow_task`` carries ``autoretry_for=TRANSIENT_EXCEPTIONS,
    max_retries=3`` and used to restart at step 0 every time. A provider read
    timeout on step 4 therefore re-executed steps 1-3 up to three more times:
    an ``APICallNode`` POST fired four times, a ``save_to_folder`` wrote four
    copies, and the tokens were billed four times over. Retrying is right; the
    engine already supports resuming (the approval gate proves it), so a retry
    resumes too.

    Returns ``(start_index, initial_output)``. ``(0, None)`` — a full rerun —
    whenever the persisted state cannot justify skipping anything: no completed
    steps, a missing output for the last completed step, or a step count that
    does not fit the engine we just built (an edited workflow between attempts).
    """
    completed = int(result_doc.get("num_steps_completed") or 0)
    steps_output = result_doc.get("steps_output") or {}
    if completed <= 0 or not steps_output:
        return 0, None

    keys = engine.step_output_keys()
    if completed >= len(keys):
        # The workflow changed shape since the attempt that got this far.
        # Replaying against the new graph would attribute old outputs to
        # different steps, so start over.
        logger.warning(
            "Not resuming: %d steps completed but the engine has %d — rerunning "
            "from the start", completed, len(keys),
        )
        return 0, None

    last_output = steps_output.get(keys[completed])
    if not isinstance(last_output, dict):
        return 0, None
    return completed + 1, last_output


def _replay_step_entries(engine, steps_output: dict, upto_index: int) -> list[dict]:
    """Rebuild the engine's per-step ``data`` entries for earlier passes.

    ``engine.execute()`` returns only the steps *it* ran, so a resumed pass
    returns a ``data`` list covering the tail of the workflow. Persisting that
    as-is truncated the run record: everything before the approval gate
    disappeared from the saved output. Steps completed in earlier passes are
    still in ``steps_output``, so replay them into the same entry shape and
    prepend.

    Steps with no persisted output are skipped — notably the Approval node
    itself, whose output is never written (the engine returns on the pause
    sentinel before the progress update).
    """
    entries: list[dict] = []
    nodes = engine.get_topological_order()
    keys = engine.step_output_keys()

    for idx, node in enumerate(nodes):
        if idx >= upto_index:
            break
        output = steps_output.get(keys[idx])
        if not isinstance(output, dict):
            continue
        entry = {
            "name": node.name,
            "output": output.get("output"),
            "input": output.get("input"),
        }
        sources = output.get("retrieved_sources")
        if isinstance(sources, list) and sources:
            entry["retrieved_sources"] = sources
        warning = output.get("warning")
        if isinstance(warning, str) and warning:
            entry["warning"] = warning
        entries.append(entry)

    return entries


def _document_context_groups(steps_data: list[dict]) -> list[set[str]]:
    """Group attached document uuids by what lands in one prompt together.

    The Document trigger's docs are concatenated into the input that flows to
    every downstream step, so they share a prompt with each step's own attached
    doc. Docs attached to *different* steps never do — summing across the whole
    workflow would refuse runs that fit fine.
    """
    trigger_uuids: set[str] = set()
    for step in steps_data:
        if step.get("name") != "Document":
            continue
        for u in (step.get("data", {}) or {}).get("doc_uuids", []) or []:
            if u:
                trigger_uuids.add(u)

    groups: list[set[str]] = [set(trigger_uuids)] if trigger_uuids else []
    for step in steps_data:
        if step.get("name") == "Document":
            continue
        own: set[str] = set()
        for task in step.get("tasks", []) or []:
            sel = (task.get("data", {}) or {}).get("selected_document_uuid")
            if sel:
                own.add(sel)
        for u in (step.get("data", {}) or {}).get("doc_uuids", []) or []:
            if u:
                own.add(u)
        if own:
            groups.append(own | trigger_uuids)
    return groups


def _document_token_counts(db, uuids: set[str]) -> dict[str, dict]:
    """Fetch {uuid: {uuid, title, token_count}} for the given documents."""
    if not uuids:
        return {}
    docs = db.smart_document.find(
        {"uuid": {"$in": list(uuids)}},
        {"uuid": 1, "title": 1, "token_count": 1},
    )
    return {
        d["uuid"]: {
            "uuid": d.get("uuid"),
            "title": d.get("title") or d.get("uuid"),
            "token_count": d.get("token_count") or 0,
        }
        for d in docs
        if d.get("uuid")
    }


def _accumulate_activity_usage(db, workflow_result_id, engine, activity_id=None) -> None:
    """Fold one execution pass's token usage into the run's ActivityEvent.

    Each pass builds its own engine with its own ``UsageAccumulator``, so usage
    has to accumulate rather than overwrite. It previously did neither on the
    two paths that matter: a run that paused at an approval gate returned
    without recording anything (losing every token spent before the gate), and
    the resume task never touched the activity at all.

    Best-effort — token bookkeeping must never fail a run that has otherwise
    succeeded.
    """
    from bson import ObjectId

    try:
        if activity_id:
            query = {"_id": ObjectId(activity_id)}
        else:
            act = db.activity_event.find_one(
                {"workflow_result": ObjectId(workflow_result_id)}, {"_id": 1},
            )
            if not act:
                return
            query = {"_id": act["_id"]}

        tokens_in = engine.usage.tokens_in
        tokens_out = engine.usage.tokens_out
        db.activity_event.update_one(query, {"$inc": {
            "tokens_input": tokens_in,
            "tokens_output": tokens_out,
            "total_tokens": tokens_in + tokens_out,
        }})
    except Exception as e:
        logger.warning(
            "Could not record token usage for workflow result %s: %s",
            workflow_result_id, e,
        )


def _make_progress_updater(db, workflow_result_id):
    """Build the engine's ``workflow_result_updater`` callback.

    Values pass through :func:`_bson_safe`: the biggest writes here are whole
    step outputs, which are whatever a node emitted and can contain bytes or
    other shapes pymongo refuses. An unencodable write used to raise from
    inside ``execute()`` and kill an otherwise healthy run mid-way.
    """
    import datetime as _dt

    from bson import ObjectId

    def update_progress(updates: dict):
        set_ops = {k: _bson_safe(v) for k, v in updates.items()}
        if set_ops:
            # Heartbeat for tasks.activity.reap_stale_workflow_runs: a run
            # whose worker died stops writing this, which is how the reaper
            # tells a dead run from one that is merely slow.
            set_ops["last_progress_at"] = _dt.datetime.now(_dt.timezone.utc)
            db.workflow_result.update_one(
                {"_id": ObjectId(workflow_result_id)},
                {"$set": set_ops},
            )

    return update_progress


def _clear_pause_marker(db, activity_id) -> None:
    """Drop the ``meta_summary.pending_review_uuid`` marker from an activity.

    Set by :func:`_pause_for_approval` while a run waits on a reviewer. Every
    path that takes the run out of that wait — resume, reject, timeout — has to
    clear it, or the row stays "awaiting approval" and the stale reaper keeps
    skipping it forever.
    """
    import datetime as _dt

    db.activity_event.update_one(
        {"_id": activity_id},
        {
            "$unset": {"meta_summary.pending_review_uuid": ""},
            "$set": {"last_updated_at": _dt.datetime.now(_dt.timezone.utc)},
        },
    )


def _pause_for_approval(db, final_output, engine, workflow_id, workflow_result_id,
                        search_from=0, activity_id=None):
    """Persist the approval request and flip the run to ``pending_approval``.

    Extracted from :func:`execute_workflow_task` so the whole sequence runs
    under a single guard in the caller: any failure here must surface as an
    error status instead of silently freezing the run.

    Args:
        search_from: Index the current execution pass started at. Used only as
            the floor for the legacy name-scan fallback; the engine normally
            stamps the exact paused index on the sentinel.
        activity_id: ActivityEvent for this run, when the caller knows it. The
            pause links the activity to the WorkflowResult and banks the pass's
            token usage — neither of which used to happen, so a paused run left
            an activity that no later pass could find and whose pre-gate tokens
            were never counted.
    """
    import uuid as uuid_mod
    from datetime import datetime, timedelta, timezone

    from bson import ObjectId

    from app.services.approval_service import (
        detect_artifact_kind,
        resolve_assignees_sync,
    )

    # Which step paused. The engine stamps the exact index on the sentinel;
    # fall back to a name scan bounded below by ``search_from`` for sentinels
    # produced before that stamp existed. The floor matters: all Approval nodes
    # share the name "Approval", so an unbounded scan on the *second* gate would
    # return the first gate's index and resume would replay it forever.
    stamped = final_output.get("_paused_step_index")
    if isinstance(stamped, int):
        step_index = stamped
    else:
        nodes = engine.get_topological_order()
        step_index = search_from
        for idx, node in enumerate(nodes):
            if idx >= search_from and node.name == "Approval":
                step_index = idx
                break

    approval_uuid = str(uuid_mod.uuid4())
    workflow_doc = db.workflow.find_one({"_id": ObjectId(workflow_id)})
    workflow_name = workflow_doc.get("name", "Workflow") if workflow_doc else "Workflow"
    result_doc = db.workflow_result.find_one({"_id": ObjectId(workflow_result_id)}) or {}
    source_doc_uuids = (result_doc.get("input_context") or {}).get("doc_uuids", [])

    assignee_role = final_output.get("_assignee_role", "specific_users")
    explicit_users = final_output.get("_assigned_to_user_ids", []) or []
    resolved_assignees = resolve_assignees_sync(
        db, assignee_role, workflow_doc or {}, explicit_users,
    )

    sla_days = final_output.get("_sla_days")
    expires_at = None
    if isinstance(sla_days, (int, float)) and sla_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=float(sla_days))

    artifact_data = final_output.get("_data_for_review")
    artifact_kind = detect_artifact_kind(artifact_data)
    safe_artifact = _bson_safe(artifact_data)

    db.approval_request.insert_one({
        "uuid": approval_uuid,
        "workflow_result_id": ObjectId(workflow_result_id),
        "workflow_id": ObjectId(workflow_id),
        "step_index": step_index,
        "step_name": "Approval",
        "workflow_name": workflow_name,
        "requester_user_id": (workflow_doc or {}).get("user_id"),
        "team_id": (workflow_doc or {}).get("team_id"),
        "source_doc_uuids": source_doc_uuids,
        "artifact_kind": artifact_kind,
        "data_for_review": safe_artifact if isinstance(safe_artifact, dict) else {"value": safe_artifact},
        "edited_artifact": None,
        "review_instructions": final_output.get("_review_instructions", ""),
        "assignee_role": assignee_role,
        "assigned_to_user_ids": resolved_assignees,
        "expires_at": expires_at,
        "timeout_action": final_output.get("_timeout_action", "none"),
        "escalation_user_ids": final_output.get("_escalation_user_ids", []),
        "status": "pending",
        "reviewer_user_id": None,
        "reviewer_comments": "",
        "decision_at": None,
        "expired_at": None,
        "escalated_at": None,
        "created_at": datetime.now(timezone.utc),
    })

    db.workflow_result.update_one(
        {"_id": ObjectId(workflow_result_id)},
        {"$set": {
            "status": "pending_approval",
            "paused_at_step_index": step_index,
            "approval_request_id": approval_uuid,
            "current_step_name": "Approval",
            "current_step_detail": "Waiting for human review",
        }},
    )

    # Link the activity to the run *now*, not at completion. The completion
    # block is the only other place that sets ``workflow_result``, and a paused
    # run never reaches it — so the resume pass's lookup by workflow_result
    # found nothing and the run's activity was orphaned mid-flight.
    #
    # The status stays "running": a run waiting on a gate has not reached a
    # terminal state, and ActivityStatus has no "paused" member to widen to
    # without touching every consumer of the activity rail.
    if activity_id:
        try:
            db.activity_event.update_one(
                {"_id": ObjectId(activity_id)},
                {"$set": {
                    "workflow_result": ObjectId(workflow_result_id),
                    # Marks the run as parked on a human rather than stalled.
                    # Three consumers read it: the activity rail and the run
                    # history render "awaiting approval" with a link straight
                    # to the review, and tasks.activity.reap_stale_running
                    # skips the row instead of failing a run whose only crime
                    # is that its reviewer has not looked yet.
                    "meta_summary.pending_review_uuid": approval_uuid,
                    "last_updated_at": datetime.now(timezone.utc),
                }},
            )
        except Exception as e:
            logger.warning("Could not link activity %s to paused run: %s", activity_id, e)

    _accumulate_activity_usage(db, workflow_result_id, engine, activity_id)

    review_instructions = final_output.get("_review_instructions", "")
    _notify_approval_reviewers_sync(
        db, resolved_assignees, workflow_name, "Approval",
        review_instructions, approval_uuid,
    )

    return {
        "status": "pending_approval",
        "approval_uuid": approval_uuid,
        "result_id": workflow_result_id,
    }


def _get_db():
    """Get sync pymongo database handle (shared per-process client)."""
    from app.tasks import get_sync_db

    return get_sync_db()


def _resolve_input_doc_uuids(workflow_doc: dict, trigger_step_data: dict) -> list[str]:
    """Effective input document uuids for a run: trigger docs plus fixed docs.

    Mirrors the merge that step-building performs (skips fixed docs in
    ``no_input`` mode) so the pre-flight readiness gate looks at exactly the
    documents the run will try to read.
    """
    doc_uuids = list((trigger_step_data or {}).get("doc_uuids", []) or [])
    input_cfg = workflow_doc.get("input_config") or {}
    if input_cfg.get("trigger_type") != "no_input":
        for fd in input_cfg.get("fixed_documents", []) or []:
            fd_uuid = fd.get("uuid") if isinstance(fd, dict) else str(fd)
            if fd_uuid and fd_uuid not in doc_uuids:
                doc_uuids.append(fd_uuid)
    return doc_uuids


def _missing_fixed_documents(db, workflow_doc: dict) -> list[str]:
    """Titles of fixed documents (Input tab) that no longer exist.

    A fixed document is configuration, not a per-run input: if it has been
    deleted from Files the workflow is misconfigured, and the run must say so
    rather than quietly cover fewer documents than the author set up (support
    ticket: output covered only the selected document, run marked Completed).
    Soft-deleted (retention) documents count as gone. ``no_input`` mode never
    loads fixed documents, so nothing is missing there.
    """
    input_cfg = workflow_doc.get("input_config") or {}
    if input_cfg.get("trigger_type") == "no_input":
        return []
    missing: list[str] = []
    for fd in input_cfg.get("fixed_documents") or []:
        uuid = (fd.get("uuid") if isinstance(fd, dict) else str(fd)) or ""
        if not uuid:
            continue
        doc = db.smart_document.find_one({"uuid": uuid}, {"title": 1, "soft_deleted": 1})
        if not doc or doc.get("soft_deleted"):
            title = (fd.get("title") if isinstance(fd, dict) else None) or (doc or {}).get("title") or uuid
            missing.append(title)
    return missing


def fixed_documents_missing_message(titles: list[str]) -> str:
    n = len(titles)
    return (
        f"{n} fixed document{'s' if n != 1 else ''} configured on this workflow's Input tab "
        f"no longer exist{'s' if n == 1 else ''}: {', '.join(titles)}. "
        f"{'It was' if n == 1 else 'They were'} deleted from Files. Remove "
        f"{'it' if n == 1 else 'them'} from the Input tab or add a replacement, then run again."
    )


def _classify_input_documents(db, workflow_doc: dict, doc_uuids: list[str]):
    """Split a run's input documents by text-extraction readiness.

    Returns ``(ready, processing, failed)`` where ``processing``/``failed`` are
    lists of display titles. Own-origin documents (this workflow's own prior
    output) are ignored — step-building skips them to avoid self-loops, so they
    must not count toward or against readiness. ``ready`` counts documents that
    already have usable ``raw_text``; ``processing`` are still extracting (a
    race worth retrying); ``failed`` have finished with no text (extraction
    failed, empty, or the document is missing).
    """
    workflow_id = str(workflow_doc.get("_id", ""))
    ready = 0
    processing: list[str] = []
    failed: list[str] = []
    for uuid in doc_uuids:
        doc = db.smart_document.find_one(
            {"uuid": uuid},
            {"raw_text": 1, "processing": 1, "origin_workflow_id": 1, "title": 1},
        )
        if doc and doc.get("origin_workflow_id") == workflow_id:
            continue
        if doc and doc.get("raw_text"):
            ready += 1
        elif doc and doc.get("processing"):
            processing.append(doc.get("title") or uuid)
        else:
            failed.append((doc.get("title") if doc else None) or uuid)
    return ready, processing, failed


def _spend_block_code(exc: BaseException) -> str:
    """Machine-readable code for a TrialSpendBlockedError.

    The family has two members and they need different remedies: an
    exhausted budget wants a top-up, an unverified account wants the
    confirmation link. Hardcoding "budget_exhausted" for both offered the
    wrong fix to the one a click solves.
    """
    from app.exceptions import TrialUnverifiedError

    return "email_unverified" if isinstance(exc, TrialUnverifiedError) else "budget_exhausted"


def _activity_owner(db, activity_id) -> str | None:
    """The user who launched the run, from its activity-rail entry.

    The rail row carries the launcher, who may differ from the workflow's
    owner (a teammate running a shared workflow) — bells about a run should
    reach the person who started it when known.
    """
    if not activity_id:
        return None
    from bson import ObjectId

    try:
        row = db.activity_event.find_one({"_id": ObjectId(activity_id)}, {"user_id": 1})
        return (row or {}).get("user_id")
    except Exception:
        return None


def _mark_workflow_failed(
    db, workflow_result_id, activity_id, error_msg, error_payload=None, notify=True,
):
    """Flip a WorkflowResult (and its activity rail entry) to a failed state
    with a user-facing message, matching the pre-flight oversize handler.

    `notify=False` suppresses the bell entry for a failure Celery is still going
    to retry — the run is not actually over yet.
    """
    from bson import ObjectId

    update = {"status": "error", "error": error_msg}
    if error_payload is not None:
        update["error_payload"] = error_payload
    db.workflow_result.update_one(
        {"_id": ObjectId(workflow_result_id)}, {"$set": update}
    )
    activity = None
    if activity_id:
        from datetime import datetime, timezone

        try:
            db.activity_event.update_one(
                {"_id": ObjectId(activity_id)},
                {"$set": {
                    "status": "failed",
                    "error": error_msg[:2000],
                    "finished_at": datetime.now(timezone.utc),
                }},
            )
            activity = db.activity_event.find_one(
                {"_id": ObjectId(activity_id)}, {"user_id": 1},
            )
        except Exception:
            pass

    if not notify:
        return

    # A run that fails after the user has navigated away leaves no trace they
    # would see, so the bell is the only signal. Resolve the owner from the
    # activity rail entry (which carries the user who launched it) and fall
    # back to the workflow's owner for runs with no activity record.
    try:
        from app.services.failure_notifications import notify_workflow_failed

        result_doc = db.workflow_result.find_one(
            {"_id": ObjectId(workflow_result_id)}, {"workflow": 1},
        ) or {}
        workflow_doc = db.workflow.find_one({"_id": result_doc.get("workflow")}) or {}
        notify_workflow_failed(
            db,
            workflow_doc=workflow_doc,
            error=error_msg,
            user_id=(activity or {}).get("user_id"),
        )
    except Exception:
        logger.exception(
            "Failed to notify owner of workflow failure (result %s)", workflow_result_id,
        )


@celery_app.task(
    bind=True,
    name="tasks.workflow_next.execution",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    rate_limit="1/s",
    max_retries=3,
    default_retry_delay=5,
    # Ack after the task finishes, not on delivery. Workers ack on delivery by
    # default, so an OOM kill or a deploy replacing the worker mid-run lost the
    # message for good: no retry, no failure handler, and the WorkflowResult
    # sat at "running" forever. Redelivery is safe *here specifically* because
    # this task is built for re-entry — the resume-at-step logic below skips
    # completed steps, and the atomic `finalized_at` claim makes the post-run
    # side effects run exactly once. Do not copy these two flags onto tasks
    # without that machinery.
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_workflow_task(self, workflow_result_id, workflow_id, trigger_step_data, model, activity_id=None):
    """Execute a full workflow.

    Args:
        workflow_result_id: WorkflowResult document ID (str).
        workflow_id: Workflow document ID (str).
        trigger_step_data: Dict with 'doc_uuids' for the Document trigger step.
        model: LLM model name.
        activity_id: Optional ActivityEvent ID to track this run in the rail.
    """
    from bson import ObjectId

    from app.services.workflow_engine import (
        WorkflowCancelled,
        WorkflowStepError,
        build_workflow_engine,
    )

    db = _get_db()

    # Load workflow and result
    workflow_doc = db.workflow.find_one({"_id": ObjectId(workflow_id)})
    result_doc = db.workflow_result.find_one({"_id": ObjectId(workflow_result_id)})

    if not workflow_doc or not result_doc:
        raise ValueError(f"Workflow {workflow_id} or result {workflow_result_id} not found")

    # With acks_late, this task can be delivered more than once: a broker
    # visibility-timeout redelivery, or a requeue after worker loss. A run
    # that reached a terminal state in the meantime — the user canceled it,
    # the reaper failed it, an earlier delivery completed it — must stay
    # there; without this guard a late redelivery flipped "canceled" back to
    # "running" and finished a run the user explicitly stopped.
    if result_doc.get("status") in ("completed", "error", "canceled"):
        logger.info(
            "Skipping delivery of workflow run %s — already terminal (%s)",
            workflow_result_id, result_doc.get("status"),
        )
        return {"status": "skipped_terminal", "result_id": workflow_result_id}

    # Bound the poison-message loop: reject_on_worker_lost requeues with a
    # fresh retry counter, so a run that deterministically OOM-kills its
    # worker would otherwise loop forever — invisible to the heartbeat reaper,
    # because every pass rewrites last_progress_at. Delivery attempts are
    # counted on the run document itself, which survives requeues.
    from pymongo import ReturnDocument

    counted = db.workflow_result.find_one_and_update(
        {"_id": ObjectId(workflow_result_id)},
        {"$inc": {"delivery_attempts": 1}},
        projection={"delivery_attempts": 1},
        return_document=ReturnDocument.AFTER,
    ) or {}
    if counted.get("delivery_attempts", 1) > MAX_DELIVERY_ATTEMPTS:
        _mark_workflow_failed(
            db, workflow_result_id, activity_id,
            "This run repeatedly crashed the worker executing it (usually a "
            "step that runs the worker out of memory) and has been stopped. "
            "Reduce the input size — or convert large documents to a "
            "Knowledge Base — and run the workflow again.",
        )
        return {"status": "error", "result_id": workflow_result_id}

    # Load system config for sync engine
    sys_config = db.system_config.find_one() or {}

    # Pre-flight readiness gate. A run dispatched right after upload (e.g. a
    # batch run over freshly uploaded files) can reach the worker before text
    # extraction finishes, so every input document still has empty raw_text and
    # the workflow would silently "complete" with no output. Rather than run on
    # nothing, wait for extraction (retry) when documents are still processing,
    # and fail with an actionable message when extraction has genuinely failed.
    missing_fixed = _missing_fixed_documents(db, workflow_doc)
    if missing_fixed:
        # Configuration error, not a transient: no retry, no Sentry, a failed
        # run with instructions — the same treatment as unreadable input.
        logger.warning(
            "Workflow %s aborted pre-flight: fixed document(s) no longer exist: %s",
            workflow_id, missing_fixed,
        )
        _mark_workflow_failed(
            db, workflow_result_id, activity_id, fixed_documents_missing_message(missing_fixed),
            error_payload={
                "code": "fixed_documents_missing",
                "missing_documents": missing_fixed[:20],
            },
        )
        return

    input_doc_uuids = _resolve_input_doc_uuids(workflow_doc, trigger_step_data)
    if input_doc_uuids:
        ready, processing, failed = _classify_input_documents(
            db, workflow_doc, input_doc_uuids
        )
        # Only gate when the run has no usable text at all — this is exactly the
        # "will produce no output" condition. A partial set (some docs ready)
        # proceeds as before.
        if ready == 0 and (processing or failed):
            if processing and self.request.retries < self.max_retries:
                delay = 10 * (self.request.retries + 1)
                logger.info(
                    "Workflow %s input still extracting (%d processing); "
                    "retry %d/%d in %ds",
                    workflow_id, len(processing),
                    self.request.retries + 1, self.max_retries, delay,
                )
                raise self.retry(countdown=delay)

            def _titles(names: list[str]) -> str:
                shown = ", ".join(names[:3])
                if len(names) > 3:
                    shown += f", and {len(names) - 3} more"
                return shown

            if processing:
                error_msg = (
                    "Input document(s) were still being processed after several "
                    f"retries: {_titles(processing)}. Wait for text extraction to "
                    "finish (check the document's status), then run again."
                )
            else:
                error_msg = (
                    "This workflow's input document(s) have no readable text: "
                    f"{_titles(failed)}. Text extraction may have failed (image-only, "
                    "encrypted, or a temporary OCR outage). Open the document to retry "
                    "extraction, or re-upload it, then run the workflow again."
                )
            # Warning, not error: this is a handled, user-actionable outcome —
            # the run is marked failed with instructions and the bell fires —
            # not a fault in the worker. The oversize pre-flight below logs at
            # the same level; paging Sentry for every run against an
            # unextracted document is noise (VANDALIZER-BACKEND-1T).
            logger.warning(
                "Workflow %s aborted pre-flight: no input document has raw_text "
                "(processing=%d, failed=%d)",
                workflow_id, len(processing), len(failed),
            )
            _mark_workflow_failed(
                db, workflow_result_id, activity_id, error_msg,
                error_payload={
                    "code": "input_documents_unready",
                    "unready_documents": (processing + failed)[:20],
                },
            )
            return

    # Build steps data from workflow steps
    steps_data, output_step_names = _build_steps_data(
        db, workflow_doc, workflow_id, trigger_step_data,
    )

    user_id = workflow_doc.get("user_id")

    # Check if the user is an admin (gates code execution)
    user_doc = db.user.find_one({"user_id": user_id}) if user_id else None
    is_admin = bool(user_doc and user_doc.get("is_admin"))

    # Progress updater using pymongo
    update_progress = _make_progress_updater(db, workflow_result_id)

    # Above the engine build, which is outside the try: a bad task type raises
    # ValueError from the builder, and leaving the row at "queued" with no
    # output_step_names hides a run that is never coming back. Only the
    # progress fields wait for the resume decision below.
    import datetime as _dt

    db.workflow_result.update_one(
        {"_id": ObjectId(workflow_result_id)},
        {"$set": {
            "status": "running",
            "num_steps_total": len(steps_data) - 1,
            "output_step_names": output_step_names,
            # First heartbeat: marks the run as picked up by a worker, which
            # moves it from the reaper's generous never-started sweep to the
            # strict no-progress one.
            "last_progress_at": _dt.datetime.now(_dt.timezone.utc),
        }},
    )

    # The builder refuses definitions it cannot honor (unknown task type, a
    # Code Execution task for a non-admin) instead of skipping the step; the
    # build sits outside the main try, so the refusal must mark the run
    # failed here or it would strand the row at "running" for the reaper.
    try:
        engine = build_workflow_engine(
            steps_data=steps_data,
            model=model,
            user_id=user_id,
            system_config_doc=sys_config,
            allow_code_execution=is_admin,
            config_override=workflow_doc.get("config_override"),
        )
    except WorkflowStepError as e:
        _mark_workflow_failed(db, workflow_result_id, activity_id, str(e))
        return {"status": "error", "result_id": workflow_result_id}

    # Any pickup resumes where a previous attempt stopped, decided from the
    # run document itself: a fresh run has no stored step output, so
    # _resume_point returns (0, None) for it. Deciding from the message
    # instead — retry counter, or the broker's `redelivered` flag — misses
    # the acks_late redelivery cases (a requeue after worker loss arrives
    # with retries == 0, and `redelivered` semantics vary by transport), and
    # restarting from step 0 would discard completed steps and re-spend
    # their tokens.
    start_index, initial_output = _resume_point(engine, result_doc)
    prior_steps_output = (result_doc.get("steps_output") or {}) if start_index else {}
    if start_index:
        logger.info(
            "Workflow %s (retry %d/%d) resuming at step %d of %d",
            workflow_id, self.request.retries, self.max_retries,
            start_index, len(steps_data) - 1,
        )

    # A resuming retry keeps the progress it already earned — clearing this is
    # what made the run restart from zero.
    if not start_index:
        db.workflow_result.update_one(
            {"_id": ObjectId(workflow_result_id)},
            {"$set": {"num_steps_completed": 0, "steps_output": {}}},
        )


    # Pre-flight oversize check: refuse the run cleanly when the documents one
    # step reads would blow the model's input budget — either a single giant
    # doc, or a package that only overflows once concatenated. The user sees a
    # guided "Convert to Knowledge Base" affordance instead of a mid-step 400
    # from the LLM gateway.
    try:
        from app.services.context_budget import find_context_overflow

        # Resolve the actual model config so context_window and
        # response_reserve_tokens overrides are honored.
        model_cfg = None
        for m in (sys_config.get("available_models") or []):
            if m.get("name") == model:
                model_cfg = m
                break

        groups = _document_context_groups(steps_data)
        token_counts = _document_token_counts(db, set().union(*groups) if groups else set())

        # Score every group; report the worst. Groups are per-step, so docs that
        # never share a prompt are never summed together.
        overflow = None
        for group in groups:
            candidate = find_context_overflow(
                documents=[token_counts[u] for u in sorted(group) if u in token_counts],
                model_name=model,
                model_config=model_cfg,
            )
            if candidate and (overflow is None or candidate.total_tokens > overflow.total_tokens):
                overflow = candidate

        if overflow:
            docs = overflow.documents
            titles = ", ".join(o.title for o in docs[:3])
            if len(docs) > 3:
                titles += f", and {len(docs) - 3} more"
            if overflow.kind == "single":
                error_msg = (
                    f"{titles} is too large to read inline with the selected model. "
                    "Convert it to a Knowledge Base and use a Knowledge Base Query step instead."
                )
            else:
                error_msg = (
                    f"These {len(docs)} documents total {overflow.total_tokens:,} tokens, "
                    f"which exceeds the {overflow.budget:,} tokens the selected model can "
                    f"read in one step ({titles}). Convert them to a Knowledge Base and use "
                    "a Knowledge Base Query step instead, or run them one at a time."
                )
            error_payload = {
                "code": "context_over_budget_convertible",
                "suggested_action": "convert_to_kb",
                "oversize_documents": [o.to_dict() for o in docs],
                "overflow_kind": overflow.kind,
                "total_tokens": overflow.total_tokens,
                "input_budget": overflow.budget,
            }
            _mark_workflow_failed(
                db, workflow_result_id, activity_id, error_msg,
                error_payload=error_payload,
            )
            logger.warning(
                "Workflow %s aborted pre-flight: %s overflow, docs %s total=%s budget=%s model=%s",
                workflow_id, overflow.kind, [o.uuid for o in docs],
                overflow.total_tokens, overflow.budget, model,
            )
            return
    except Exception:
        # The pre-flight is best-effort; don't let it block a valid run.
        logger.exception("Pre-flight oversize check failed for workflow %s", workflow_id)

    # Mark activity as running
    if activity_id:
        try:
            db.activity_event.update_one(
                {"_id": ObjectId(activity_id)},
                {"$set": {"status": "running"}},
            )
        except Exception as e:
            logger.warning("Could not update activity to running: %s", e)

    # Polled by the engine between steps. The cancel endpoint flips the result
    # status to "canceled"; this lets a run that is between steps stop cleanly
    # (a mid-step stop is handled out-of-band by Celery task revocation).
    _cancel_check_oid = ObjectId(workflow_result_id)

    def should_cancel() -> bool:
        # A swallowed DB blip used to make a user's Cancel silently not take —
        # the run kept going and kept spending. False remains the failure
        # answer (spuriously canceling healthy runs on a blip is worse), but
        # never quietly: the error log names the consequence. No retry here —
        # a dead connection blocks for the full server-selection timeout, and
        # pymongo already retries reads internally, so a second attempt only
        # doubles the stall for the same answer.
        try:
            doc = db.workflow_result.find_one(
                {"_id": _cancel_check_oid}, {"status": 1},
            )
            return bool(doc and doc.get("status") == "canceled")
        except Exception as e:
            logger.error(
                "Cancel check failed for run %s (%s) — a pending Cancel "
                "will not take effect this step",
                workflow_result_id, e,
            )
            return False

    def check_budget() -> None:
        # The same gate metered() applies at run entry, re-applied between
        # steps: a trial account that crosses its budget mid-run stops at the
        # next step boundary instead of overrunning arbitrarily (#808).
        # The run's own spend is still in the live MeterScope — its ledger row
        # is not written until the scope exits — so it is passed explicitly;
        # without it the gate would re-read an unchanged total every time.
        from app.services.metering import current_scope
        from app.services.trial_budget import check_sync

        scope = current_scope()
        in_flight = (scope.tokens_in + scope.tokens_out) if scope else 0
        check_sync(user_id, extra_used=in_flight)

    try:
        from app.services.metering import metered
        with metered(
            "workflow",
            user_id=user_id,
            team_id=workflow_doc.get("team_id"),
            activity_id=activity_id,
        ):
            final_output, data = engine.execute(
                workflow_result_updater=update_progress,
                start_index=start_index,
                initial_output=initial_output,
                should_cancel=should_cancel,
                check_budget=check_budget,
            )
        if start_index:
            # execute() reports only the steps this pass ran. Without the
            # earlier ones the saved record would begin mid-workflow — the same
            # correction the approval resume already makes.
            data = _replay_step_entries(
                engine, prior_steps_output, start_index,
            ) + (data or [])
    except WorkflowCancelled:
        logger.info(
            "Workflow %s canceled by user (result %s)", workflow_id, workflow_result_id,
        )
        db.workflow_result.update_one(
            {"_id": ObjectId(workflow_result_id)},
            {"$set": {"status": "canceled", "error": "Canceled by user"}},
        )
        if activity_id:
            try:
                from datetime import datetime, timezone
                db.activity_event.update_one(
                    {"_id": ObjectId(activity_id)},
                    {"$set": {
                        "status": "canceled",
                        "error": "Canceled by user",
                        "finished_at": datetime.now(timezone.utc),
                    }},
                )
            except Exception:
                pass
        # Clean terminal stop — do not re-raise (no retry).
        return {"status": "canceled", "result_id": workflow_result_id}
    except WorkflowStepError as e:
        # A step failed (blocked URL, HTTP error, bad config, ...). This is a
        # deterministic, user-facing failure: mark the run failed and stop —
        # no re-raise, so it neither retries nor lands in Sentry as a crash.
        logger.warning("Workflow %s failed: %s", workflow_id, e)
        _mark_workflow_failed(db, workflow_result_id, activity_id, str(e))
        return {"status": "error", "result_id": workflow_result_id}
    except TrialSpendBlockedError as e:
        # The between-steps budget gate tripped (#808): the trial budget ran
        # out mid-run. A clean, honest stop at a step boundary — completed
        # steps are preserved in steps_output, nothing truncated is presented
        # as complete, and retrying cannot help until the budget changes.
        logger.warning(
            "Workflow %s stopped at a step boundary — trial budget exhausted",
            workflow_id,
        )
        _mark_workflow_failed(
            db, workflow_result_id, activity_id, str(e),
            error_payload={"code": _spend_block_code(e)},
        )
        return {"status": "error", "result_id": workflow_result_id}
    except Exception as e:
        logger.error("Workflow execution failed for %s: %s", workflow_id, e)
        from app.services.failure_notifications import is_final_attempt

        _mark_workflow_failed(
            db, workflow_result_id, activity_id, str(e),
            notify=is_final_attempt(self, e),
        )
        raise

    # Check if workflow paused for approval. The handling below must run under a
    # guard: it used to sit outside any try/except, so a single failure (a
    # non-BSON-serializable review artifact, a notifier error, etc.) escaped
    # uncaught and left the run frozen in "running" with no approval record and
    # no notification. Surface any failure as an error status instead.
    if isinstance(final_output, dict) and final_output.get("_approval_pause"):
        try:
            return _pause_for_approval(
                db, final_output, engine, workflow_id, workflow_result_id,
                activity_id=activity_id,
            )
        except Exception as e:
            logger.exception(
                "Approval gate handling failed for workflow %s (result %s)",
                workflow_id, workflow_result_id,
            )
            from app.services.failure_notifications import is_final_attempt

            _mark_workflow_failed(
                db, workflow_result_id, activity_id, f"Approval gate failed: {e}",
                notify=is_final_attempt(self, e),
            )
            raise

    # Aggregate citations from every step that produced retrieved_sources so
    # the frontend can render them next to the workflow output without
    # walking the steps_output dict itself.
    retrieved_sources: list[dict] = []
    for step in data or []:
        sources = step.get("retrieved_sources") if isinstance(step, dict) else None
        if isinstance(sources, list):
            retrieved_sources.extend(sources)

    # Save final result. The status guard matters: cancellation flips the row to
    # "canceled" out-of-band, and a step already in flight keeps running until
    # the Celery revoke lands (or finishes first). Writing "completed"
    # unconditionally would undo the user's stop and leave a batch they halted
    # reporting success.
    db.workflow_result.update_one(
        {"_id": ObjectId(workflow_result_id), "status": {"$ne": "canceled"}},
        {"$set": {
            "status": "completed",
            "final_output": {"output": final_output, "data": data},
            "retrieved_sources": retrieved_sources,
        }},
    )

    # Everything below runs *after* execute() returned, and sits outside the
    # try — so an AutoReconnect on the $inc, or a Redis blip on the
    # auto-validate dispatch further down, retries the whole task. The resume
    # then correctly skips every step and lands right back here, re-running
    # side effects that already happened: a second library document (the
    # filename template carries {time}, so it is a new file, not an overwrite)
    # and another increment, up to four times.
    #
    # Claimed atomically instead. `{"finalized_at": None}` matches a missing
    # field too, so runs that predate this are claimable exactly once.
    import datetime as _dt

    claimed = db.workflow_result.update_one(
        {"_id": ObjectId(workflow_result_id), "finalized_at": None},
        {"$set": {"finalized_at": _dt.datetime.now(_dt.timezone.utc)}},
    )
    if claimed.modified_count:
        # Save output to library if configured. Manual runs don't go through
        # process_outputs (which also fires notifications/webhooks/chains for
        # passive runs); this targets storage only.
        storage_cfg = (workflow_doc.get("output_config") or {}).get("storage") or {}
        if storage_cfg.get("enabled") and storage_cfg.get("destination_folder"):
            try:
                from app.services.output_handlers import save_results_to_folder
                fresh_result = db.workflow_result.find_one({"_id": ObjectId(workflow_result_id)})
                if fresh_result:
                    save_results_to_folder(fresh_result, storage_cfg)
            except Exception as e:
                # The run completed and its results are viewable, but the
                # configured deliverable never left the building — recorded on
                # the run and belled, not just logged (#810). Guarded like the
                # rest of the finalize block: this sits after the finalized_at
                # claim, so an escape here (e.g. a correlated Mongo failover)
                # would strand the activity and skip num_executions on the
                # retry that finds the claim already taken.
                logger.exception("Failed to save workflow output to library: %s", e)
                try:
                    detail = "The output could not be saved to the library."
                    db.workflow_result.update_one(
                        {"_id": ObjectId(workflow_result_id)},
                        {"$push": {"delivery_failures": f"{detail} {str(e)[:200]}"}},
                    )
                    from app.services.failure_notifications import notify_delivery_failed

                    notify_delivery_failed(
                        db, workflow_doc=workflow_doc, detail=detail, error=e,
                        user_id=_activity_owner(db, activity_id),
                    )
                except Exception:
                    logger.exception(
                        "Could not record delivery failure for run %s",
                        workflow_result_id,
                    )

        # Increment workflow execution count
        db.workflow.update_one(
            {"_id": ObjectId(workflow_id)},
            {"$inc": {"num_executions": 1}},
        )
    else:
        logger.info(
            "Workflow %s finalize side effects already ran; skipping on retry",
            workflow_result_id,
        )

    # Update activity and generate AI title
    if activity_id:
        try:
            from datetime import datetime, timezone
            doc_uuids = trigger_step_data.get("doc_uuids", [])
            # Read step counts from the WorkflowResult
            wr_doc = db.workflow_result.find_one(
                {"_id": ObjectId(workflow_result_id)},
                {"num_steps_completed": 1, "num_steps_total": 1},
            )
            usage_update = {
                "status": "completed",
                "finished_at": datetime.now(timezone.utc),
                "last_updated_at": datetime.now(timezone.utc),
                "workflow_result": ObjectId(workflow_result_id),
                "steps_completed": (wr_doc or {}).get("num_steps_completed", 0),
                "steps_total": (wr_doc or {}).get("num_steps_total", 0),
            }
            db.activity_event.update_one(
                {"_id": ObjectId(activity_id)},
                {"$set": usage_update},
            )
            # Tokens accumulate ($inc) rather than overwrite — this run may be
            # the tail of a multi-pass execution and must not erase the tokens
            # earlier passes banked.
            _accumulate_activity_usage(db, workflow_result_id, engine, activity_id)
            from app.tasks.activity_tasks import generate_activity_description_task
            generate_activity_description_task.delay(activity_id, "workflow_run", doc_uuids)
        except Exception as e:
            logger.warning("Could not finalize activity for workflow %s: %s", workflow_id, e)

    # Fire-and-forget auto-validation if validation plan exists
    from app.tasks.quality_tasks import auto_validate_workflow
    auto_validate_workflow.delay(workflow_id)

    return {
        "status": "completed",
        "result_id": workflow_result_id,
        "workflow_id": workflow_id,
    }


@celery_app.task(
    bind=True,
    name="tasks.workflow_next.execution_step_test",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=2,
    default_retry_delay=5,
)
def execute_task_step_test(self, task_name, task_data, doc_uuids):
    """Test a single workflow step.

    Args:
        task_name: e.g. "Extraction", "Prompt", "Formatter"
        task_data: Task data dict.
        doc_uuids: List of document UUIDs for the trigger step.
    """
    from app.services.workflow_engine import (
        APICallNode,
        AddDocumentNode,
        BrowserAutomationNode,
        CodeExecutionNode,
        CrawlerNode,
        DataExportNode,
        DescribeImageNode,
        DocumentNode,
        DocumentRendererNode,
        ExtractionNode,
        FormatNode,
        FormFillerNode,
        KnowledgeBaseQueryNode,
        MultiTaskNode,
        PackageBuilderNode,
        PromptNode,
        ResearchNode,
        WebsiteNode,
        WorkflowEngine,
        WorkflowStepError,
    )

    db = _get_db()
    sys_config = db.system_config.find_one() or {}

    # Pre-load doc texts
    doc_texts = []
    doc_metas = []
    for uuid in doc_uuids:
        doc = db.smart_document.find_one({"uuid": uuid})
        if doc and doc.get("raw_text"):
            doc_texts.append(doc["raw_text"])
            doc_metas.append(document_meta(doc))
    task_data["doc_texts"] = doc_texts
    if task_name in DOC_META_TASKS:
        task_data["doc_metas"] = doc_metas

    # Pre-load specific document text when select_document is selected
    if _wants_selected_document(task_data) and task_data.get("selected_document_uuid"):
        sel_doc = db.smart_document.find_one({"uuid": task_data["selected_document_uuid"]})
        if sel_doc and sel_doc.get("raw_text"):
            task_data["selected_doc_text"] = sel_doc["raw_text"]
            if task_name in DOC_META_TASKS:
                task_data["selected_doc_meta"] = document_meta(sel_doc)

    if task_name == "FormFiller":
        _preload_form_filler_template(db, task_data)

    # Resolve a linked saved Prompt/Formatter so Test Step uses the live body.
    _resolve_saved_prompt_formatter(db, task_name, task_data)

    engine = WorkflowEngine()
    nodes = []

    doc_node = DocumentNode({"doc_uuids": doc_uuids})
    nodes.append(doc_node)
    engine.add_node(doc_node)

    if task_name == "Extraction":
        process_node = ExtractionNode(data=task_data)
    elif task_name == "Prompt":
        process_node = PromptNode(data=task_data)
    elif task_name == "Formatter":
        process_node = FormatNode(data=task_data)
    elif task_name == "AddWebsite":
        process_node = WebsiteNode(data=task_data)
    elif task_name == "AddDocument":
        process_node = AddDocumentNode(data=task_data)
    elif task_name == "DescribeImage":
        process_node = DescribeImageNode(data=task_data)
    elif task_name == "CodeNode":
        process_node = CodeExecutionNode(data=task_data)
    elif task_name == "CrawlerNode":
        process_node = CrawlerNode(data=task_data)
    elif task_name == "ResearchNode":
        process_node = ResearchNode(data=task_data)
    elif task_name == "APINode":
        process_node = APICallNode(data=task_data)
    elif task_name == "DocumentRenderer":
        process_node = DocumentRendererNode(data=task_data)
    elif task_name == "FormFiller":
        process_node = FormFillerNode(data=task_data)
    elif task_name == "DataExport":
        process_node = DataExportNode(data=task_data)
    elif task_name == "PackageBuilder":
        process_node = PackageBuilderNode(data=task_data)
    elif task_name in ("BrowserAutomation", "Browser"):
        # Same alias the builder accepts — the editor persists "Browser".
        process_node = BrowserAutomationNode(data=task_data)
    elif task_name == "KnowledgeBaseQuery":
        process_node = KnowledgeBaseQueryNode(data=task_data)
    else:
        raise ValueError(f"Unknown task type: {task_name}")

    process_node._sys_cfg = sys_config

    multi_node = MultiTaskNode(task_name)
    multi_node.add_tasks([process_node])
    nodes.append(multi_node)
    engine.add_node(multi_node)

    for i in range(1, len(nodes)):
        engine.connect(nodes[i - 1], nodes[i])

    try:
        final_output, steps = engine.execute()
    except WorkflowStepError as e:
        # Deterministic config/user error (blocked URL, HTTP failure, bad
        # headers…). Return a structured failure instead of raising: the task
        # then neither retries nor produces a Sentry error event, the poll
        # endpoint gets the clean message without a result-backend exception
        # round-trip, and the step's full output (request preview included)
        # stays available for debugging — Test Step has no
        # workflow_result_updater to persist it anywhere else.
        return {
            "step_test_failed": True,
            "error": str(e),
            "output": e.step_output,
        }
    # A step can complete with a warning (fields a Form Filler could not
    # fill, an empty input, …). The run UI shows those on the step; Test
    # Step used to drop them and show a clean "Test Completed" over output
    # that needed checking. Wrap so the poll endpoint can hand it through.
    warnings = [
        s["warning"] for s in steps
        if isinstance(s, dict) and isinstance(s.get("warning"), str) and s["warning"]
    ]
    if warnings:
        return {"step_test_warning": " | ".join(warnings), "output": final_output}
    return final_output


@celery_app.task(
    bind=True,
    name="tasks.workflow.resume_after_approval",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=5,
    # Same reasoning as execute_workflow_task: a worker dying mid-resume used
    # to eat the message, leaving the approved run at "running" forever with
    # the reviewer certain they had approved it. Redelivery re-runs the
    # post-gate steps, and the `finalized_at` claim keeps the side effects
    # single-shot.
    acks_late=True,
    reject_on_worker_lost=True,
)
def resume_workflow_after_approval(self, approval_uuid):
    """Resume a workflow after an approval request has been approved."""
    from bson import ObjectId

    from app.services.workflow_engine import WorkflowStepError, build_workflow_engine

    db = _get_db()

    approval_doc = db.approval_request.find_one({"uuid": approval_uuid})
    if not approval_doc:
        raise ValueError(f"Approval {approval_uuid} not found")
    if approval_doc.get("status") != "approved":
        raise ValueError(f"Approval {approval_uuid} is not approved")

    workflow_result_id = str(approval_doc["workflow_result_id"])
    workflow_id = str(approval_doc["workflow_id"])
    step_index = approval_doc.get("step_index", 0)

    workflow_doc = db.workflow.find_one({"_id": ObjectId(workflow_id)})
    result_doc = db.workflow_result.find_one({"_id": ObjectId(workflow_result_id)})
    if not workflow_doc or not result_doc:
        raise ValueError(f"Workflow or result not found for approval {approval_uuid}")

    sys_config = db.system_config.find_one() or {}

    # Rebuild steps_data through the same builder the initial run uses, so the
    # resumed pass executes the identical configuration.
    trigger_data = result_doc.get("input_context", {}) or {}
    steps_data, _ = _build_steps_data(db, workflow_doc, workflow_id, trigger_data)

    user_id = workflow_doc.get("user_id")

    # Check if the user is an admin (gates code execution)
    user_doc = db.user.find_one({"user_id": user_id}) if user_id else None
    is_admin = bool(user_doc and user_doc.get("is_admin"))

    # If the reviewer edited the artifact, downstream steps see the edited
    # version. Otherwise replay the original snapshot.
    edited = approval_doc.get("edited_artifact")
    saved_output = edited if edited not in (None, {}) else approval_doc.get("data_for_review")
    initial_output = {"output": saved_output, "step_name": "Approval"} if saved_output else None

    # Update result to running. Refuse if the run was canceled while it sat at
    # the gate: cancel_batch expires the pending approvals it cancels, but a
    # reviewer holding a stale page can still approve one, and resuming would
    # restart a run the user explicitly stopped — spending tokens hours later.
    import datetime as _dt

    # Positive status filter, not just "$ne canceled": a run the reaper
    # already failed (approved-but-never-resumed, or a dead worker) must not
    # be silently resurrected by a late resume delivery after its owner was
    # told to re-run it — that executes the post-gate steps twice. "running"
    # stays eligible so a Celery retry of this task can proceed past its own
    # first attempt's write.
    resumed = db.workflow_result.update_one(
        {
            "_id": ObjectId(workflow_result_id),
            "status": {"$in": ["pending_approval", "running"]},
        },
        {"$set": {
            "status": "running",
            "current_step_detail": "Resuming after approval",
            "last_progress_at": _dt.datetime.now(_dt.timezone.utc),
        }},
    )
    if resumed.matched_count == 0:
        logger.info(
            "Not resuming workflow_result %s after approval — it was "
            "canceled or already finalized",
            workflow_result_id,
        )
        return {"status": "canceled", "result_id": workflow_result_id}

    update_progress = _make_progress_updater(db, workflow_result_id)

    # Steps after an approval gate must run on the model the run started with.
    # That model is snapshotted on the result at dispatch; runs that predate the
    # field fall back to the configured default rather than to a hardcoded model
    # name, which is never a configured model and so reaches the provider with
    # no API key.
    model = result_doc.get("model") or _default_model_from_config(sys_config)

    # Resolved before the build so its refusal handler can reach it too.
    _act = db.activity_event.find_one(
        {"workflow_result": ObjectId(workflow_result_id)}, {"_id": 1}
    )

    # Same build-refusal handling as execute_workflow_task: an unknown task
    # type or a rejected Code Execution task fails the run with the builder's
    # message instead of stranding it at "running".
    try:
        engine = build_workflow_engine(
            steps_data=steps_data,
            model=model,
            user_id=user_id,
            system_config_doc=sys_config,
            allow_code_execution=is_admin,
            config_override=workflow_doc.get("config_override"),
        )
    except WorkflowStepError as e:
        _mark_workflow_failed(
            db, workflow_result_id, _act["_id"] if _act else None, str(e),
        )
        # Every path out of the approval wait must drop the pause marker
        # (see _clear_pause_marker) — leaving it would show a failed run as
        # "awaiting approval" forever and exempt it from the stale reaper.
        if _act:
            _clear_pause_marker(db, _act["_id"])
        return {"status": "error", "result_id": workflow_result_id}

    # The run is moving again: drop the pause marker so the rail stops showing
    # "awaiting approval" and the stale reaper starts covering this row again.
    # Done before execute() rather than after, because a pass that fails or
    # pauses on a second gate never reaches the finalize block below.
    if _act:
        try:
            _clear_pause_marker(db, _act["_id"])
        except Exception as e:
            logger.warning(
                "Could not clear pause marker on activity %s: %s", _act["_id"], e,
            )

    # This task carries the same autoretry_for + max_retries=3 as the initial
    # execution, and had no resume index of its own: a transient failure at
    # step 8 re-ran steps 4-7 — API POSTs, folder writes, tokens — up to four
    # times, the identical bug the initial path just fixed. `num_steps_completed`
    # and `steps_output` are already advanced by this pass, so the same helper
    # applies; take whichever is further along, since a first pass through this
    # task must still start at the gate.
    resume_index, resume_output = step_index + 1, initial_output
    if self.request.retries:
        retry_index, retry_output = _resume_point(engine, result_doc)
        if retry_index > resume_index:
            resume_index, resume_output = retry_index, retry_output
        logger.info(
            "Workflow %s approval-resume retry %d/%d resuming at step %d",
            workflow_id, self.request.retries, self.max_retries, resume_index,
        )

    def check_budget() -> None:
        # Same mid-run budget gate as execute_workflow_task (#808), including
        # the live scope's not-yet-flushed spend.
        from app.services.metering import current_scope
        from app.services.trial_budget import check_sync

        scope = current_scope()
        in_flight = (scope.tokens_in + scope.tokens_out) if scope else 0
        check_sync(user_id, extra_used=in_flight)

    try:
        from app.services.metering import metered
        with metered(
            "workflow",
            user_id=user_id,
            team_id=workflow_doc.get("team_id"),
            activity_id=str(_act["_id"]) if _act else None,
        ):
            final_output, data = engine.execute(
                workflow_result_updater=update_progress,
                start_index=resume_index,
                initial_output=resume_output,
                check_budget=check_budget,
            )
        # execute() reports only the steps this pass ran. Prepend the ones
        # earlier passes completed, replayed from the persisted steps_output,
        # or the saved run record would show a workflow that began at the
        # approval gate and everything before it would vanish from the output.
        data = _replay_step_entries(
            engine, result_doc.get("steps_output") or {}, resume_index,
        ) + (data or [])
    except WorkflowStepError as e:
        # Deterministic step failure — mark the run failed, don't retry.
        logger.warning("Workflow %s failed after resume: %s", workflow_id, e)
        db.workflow_result.update_one(
            {"_id": ObjectId(workflow_result_id)},
            {"$set": {"status": "error", "error": str(e)}},
        )
        return {"status": "error", "result_id": workflow_result_id}
    except TrialSpendBlockedError as e:
        # Same between-steps budget stop as execute_workflow_task (#808).
        logger.warning(
            "Resumed workflow %s stopped at a step boundary — trial budget exhausted",
            workflow_id,
        )
        _mark_workflow_failed(
            db, workflow_result_id,
            str(_act["_id"]) if _act else None, str(e),
            error_payload={"code": _spend_block_code(e)},
        )
        return {"status": "error", "result_id": workflow_result_id}
    except Exception as e:
        logger.error("Workflow resume failed for %s: %s", workflow_id, e)
        from app.services.failure_notifications import is_final_attempt

        _mark_workflow_failed(
            db, workflow_result_id,
            str(_act["_id"]) if _act else None, str(e),
            notify=is_final_attempt(self, e),
        )
        raise

    # A workflow may have more than one approval gate. Resuming past the first
    # one can land on another, so the resume path needs the same pause handling
    # as the initial run — without it the second gate's sentinel was treated as
    # a normal final output and the run was marked "completed" with no review
    # ever created for the second reviewer.
    if isinstance(final_output, dict) and final_output.get("_approval_pause"):
        try:
            return _pause_for_approval(
                db, final_output, engine, workflow_id, workflow_result_id,
                search_from=step_index + 1,
                activity_id=str(_act["_id"]) if _act else None,
            )
        except Exception as e:
            logger.exception(
                "Approval gate handling failed on resume for workflow %s (result %s)",
                workflow_id, workflow_result_id,
            )
            db.workflow_result.update_one(
                {"_id": ObjectId(workflow_result_id)},
                {"$set": {"status": "error", "error": f"Approval gate failed: {e}"}},
            )
            raise

    # Citations are aggregated over the whole run, not just this pass — `data`
    # now spans every step, including the pre-gate ones replayed above.
    retrieved_sources: list[dict] = []
    for step in data or []:
        sources = step.get("retrieved_sources") if isinstance(step, dict) else None
        if isinstance(sources, list):
            retrieved_sources.extend(sources)

    db.workflow_result.update_one(
        {"_id": ObjectId(workflow_result_id)},
        {"$set": {
            "status": "completed",
            "final_output": {"output": final_output, "data": data},
            "retrieved_sources": retrieved_sources,
        }},
    )

    # Same claim the non-approval path makes, for the same reason: this task
    # carries autoretry_for with max_retries=3, and everything above it is
    # idempotent ($set) while the increment is not. A failure after execute()
    # succeeds — the final-result write, a Mongo blip — retries the whole task,
    # the resume correctly skips every step, and execution lands right back
    # here to count the same run a second, third and fourth time.
    #
    # `{"finalized_at": None}` matches a missing field too, so an approval-gated
    # run that predates this is claimable exactly once. It also means this path
    # finally stamps `finalized_at`, which it never did — leaving every
    # approval-gated run permanently unclaimed.
    import datetime as _dt

    claimed = db.workflow_result.update_one(
        {"_id": ObjectId(workflow_result_id), "finalized_at": None},
        {"$set": {"finalized_at": _dt.datetime.now(_dt.timezone.utc)}},
    )
    if claimed.modified_count:
        db.workflow.update_one(
            {"_id": ObjectId(workflow_id)},
            {"$inc": {"num_executions": 1}},
        )
    else:
        logger.info(
            "Approval-gated workflow %s finalize side effects already ran; "
            "skipping on retry", workflow_result_id,
        )

    # Finalize the activity. The resume path used to skip this entirely, so a
    # run that passed through an approval gate left its activity stuck at
    # "running" forever and never reported the tokens it spent.
    if _act:
        try:
            from datetime import datetime, timezone

            wr_doc = db.workflow_result.find_one(
                {"_id": ObjectId(workflow_result_id)},
                {"num_steps_completed": 1, "num_steps_total": 1},
            )
            db.activity_event.update_one(
                {"_id": _act["_id"]},
                {"$set": {
                    "status": "completed",
                    "finished_at": datetime.now(timezone.utc),
                    "last_updated_at": datetime.now(timezone.utc),
                    "steps_completed": (wr_doc or {}).get("num_steps_completed", 0),
                    "steps_total": (wr_doc or {}).get("num_steps_total", 0),
                }},
            )
        except Exception as e:
            logger.warning(
                "Could not finalize activity for resumed workflow %s: %s", workflow_id, e,
            )
    _accumulate_activity_usage(
        db, workflow_result_id, engine, str(_act["_id"]) if _act else None,
    )

    return {
        "status": "completed",
        "result_id": workflow_result_id,
        "workflow_id": workflow_id,
    }
