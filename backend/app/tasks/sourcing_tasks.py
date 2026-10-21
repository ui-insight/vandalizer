"""Sourcing for finished workflow runs and step tests.

A run is marked completed, with its output saved, before anything here
starts: sourcing reads that saved output and writes only the run's
``sourcing`` field. It cannot delay, change or fail the result — when it
errors or runs out of time the run simply shows no underlines (see
``output_sourcing`` for what a source must pass to be linked).
"""

import datetime as _dt
import logging
import os
import time

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

TIME_BUDGET_SECONDS = 600
DISABLE_ENV = "WORKFLOW_SOURCING"
WORKERS_ENV = "WORKFLOW_SOURCING_WORKERS"


def sourcing_enabled() -> bool:
    """On unless the deployment turns it off (``WORKFLOW_SOURCING=off``)."""
    return os.environ.get(DISABLE_ENV, "on").strip().lower() not in ("0", "off", "false", "no")


def sourcing_workers() -> int:
    """Model calls a trace makes at once (``WORKFLOW_SOURCING_WORKERS``,
    1–32): fewer on a model server that is busy or rate-limits harder."""
    from app.services.output_sourcing import WORKERS

    try:
        return max(1, min(32, int(os.environ.get(WORKERS_ENV, "") or WORKERS)))
    except ValueError:
        return WORKERS


def _now():
    return _dt.datetime.now(_dt.timezone.utc)


def _get_db():
    from app.tasks.workflow_tasks import _get_db as get_db

    return get_db()


def run_document_uuids(workflow_doc: dict, trigger_step_data: dict, steps_data: list[dict] | None) -> list[str]:
    """Every document a run read: the trigger's, the workflow's fixed ones
    and any a task selected — the same set ``build_steps_data`` loads.
    Never raises; the sourcing task falls back to the run's trigger."""
    uuids: list[str] = []
    try:
        uuids.extend(u for u in (trigger_step_data or {}).get("doc_uuids") or [] if u)
        input_cfg = (workflow_doc or {}).get("input_config") or {}
        if input_cfg.get("trigger_type") != "no_input":
            for fd in input_cfg.get("fixed_documents") or []:
                u = fd.get("uuid") if isinstance(fd, dict) else str(fd)
                if u:
                    uuids.append(u)
        for step in steps_data or []:
            for task in step.get("tasks") or []:
                sel = (task.get("data") or {}).get("selected_document_uuid")
                if sel:
                    uuids.append(sel)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not list a run's documents for sourcing: %s", e)
    return [u for u in dict.fromkeys(uuids) if isinstance(u, str)]


def queue_run_sourcing(db, workflow_result_id, doc_uuids: list[str] | None) -> None:
    """Start sourcing a run that has just been saved as completed. Never
    raises: a run's result must not depend on this."""
    if not sourcing_enabled():
        return
    from bson import ObjectId

    oid = ObjectId(str(workflow_result_id))
    try:
        # `None` matches a missing field and the null Beanie writes when it
        # creates the run; `$exists: False` would miss every API-created run.
        marked = db.workflow_result.update_one(
            {"_id": oid, "status": "completed", "sourcing": None},
            {"$set": {"sourcing": {"version": 1, "status": "pending", "queued_at": _now()}}},
        )
        if not getattr(marked, "modified_count", 0):
            return
        trace_run_sources.delay(str(workflow_result_id), list(doc_uuids or []))
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not queue sourcing for run %s: %s", workflow_result_id, e)
        try:
            db.workflow_result.update_one(
                {"_id": oid},
                {"$set": {"sourcing": {"version": 1, "status": "failed", "error": "Could not start tracing sources."}}},
            )
        except Exception:  # noqa: BLE001
            pass


def _load_documents(db, doc_uuids: list[str], skip_origin_workflow: str | None = None) -> list[dict]:
    docs = []
    for uuid in dict.fromkeys(doc_uuids or []):
        doc = db.smart_document.find_one(
            {"uuid": uuid}, {"uuid": 1, "title": 1, "raw_text": 1, "text_markers": 1, "origin_workflow_id": 1},
        )
        if not doc or not doc.get("raw_text"):
            continue
        if skip_origin_workflow and doc.get("origin_workflow_id") == skip_origin_workflow:
            continue   # a run never reads its own output documents
        docs.append(doc)
    return docs


def _displayed(entry: dict):
    """What the UI shows for a step: its formatted output when it has one."""
    value = entry.get("formatted_output")
    return entry.get("output") if value is None else value


def run_targets(result_doc: dict) -> tuple[dict, list[dict]]:
    """``({target key: output value}, [knowledge-base passages])`` for a
    saved run: each step's output, keyed ``step:<steps_output key>``, and
    the deliverable, keyed ``final``."""
    from app.services.kb_grounding import merge_sources

    targets: dict = {}
    groups = [result_doc.get("retrieved_sources")]
    for key, entry in (result_doc.get("steps_output") or {}).items():
        if not isinstance(entry, dict) or entry.get("step_name") == "Document" or key == "Document":
            continue
        groups.append(entry.get("retrieved_sources"))
        value = _displayed(entry)
        if value is not None:
            targets[f"step:{key}"] = value
    final = result_doc.get("final_output")
    if isinstance(final, dict):
        for step in final.get("data") or []:
            if isinstance(step, dict):
                groups.append(step.get("retrieved_sources"))
        if final.get("output") is not None:
            targets["final"] = final.get("output")
    passages = [p for p in merge_sources(*groups) if isinstance(p.get("content"), str) and p["content"].strip()]
    return targets, passages


def _judge(model: str, sys_config: dict):
    from app.services.workflow_engine import _run_form_filler_model

    def ask(instructions: str, prompt: str) -> str:
        return _run_form_filler_model(model, instructions, prompt, system_config_doc=sys_config, usage_acc=None)

    return ask


def _model_for(db, sys_config: dict, preferred: str | None, user_id: str | None) -> str:
    if preferred:
        return preferred
    from app.tasks.workflow_tasks import default_model_for_owner

    return default_model_for_owner(db, sys_config, user_id)


def _trace(targets: dict, documents: list[dict], passages: list[dict], *, model: str, sys_config: dict,
           user_id: str | None, team_id: str | None, first: set[str] | None = None, publish=None) -> dict:
    from app.services.metering import metered
    from app.services.output_sourcing import trace_sources

    started = time.monotonic()
    with metered("workflow_sourcing", user_id=user_id, team_id=team_id):
        payload = trace_sources(
            targets, documents, passages,
            ask=_judge(model, sys_config),
            deadline=started + TIME_BUDGET_SECONDS,
            workers=sourcing_workers(),
            first=first,
            publish=publish,
        )
    payload["model"] = model
    payload["seconds"] = round(time.monotonic() - started, 1)
    return payload


def _publisher(db, oid):
    """Write what is settled so far into the run while it is still being
    traced: the UI draws these underlines and keeps polling. Only while the
    trace still owns the field — never over a finished result."""
    def publish(partial: dict) -> None:
        db.workflow_result.update_one(
            {"_id": oid, "sourcing.status": "running"},
            {"$set": {
                "sourcing.targets": partial.get("targets") or {},
                "sourcing.sources": partial.get("sources") or [],
                "sourcing.updated_at": _now(),
            }},
        )
    return publish


@celery_app.task(
    bind=True,
    name="tasks.workflow_next.trace_sources",
    max_retries=0,
    soft_time_limit=TIME_BUDGET_SECONDS + 120,
    time_limit=TIME_BUDGET_SECONDS + 180,
)
def trace_run_sources(self, workflow_result_id: str, doc_uuids: list[str] | None = None):
    """Source a completed run's outputs into ``workflow_result.sourcing``."""
    from bson import ObjectId

    db = _get_db()
    oid = ObjectId(workflow_result_id)
    claimed = db.workflow_result.update_one(
        {"_id": oid, "status": "completed", "sourcing.status": "pending"},
        {"$set": {"sourcing.status": "running", "sourcing.started_at": _now()}},
    )
    if not claimed.modified_count:
        return {"status": "skipped"}
    try:
        result_doc = db.workflow_result.find_one({"_id": oid}) or {}
        workflow_doc = db.workflow.find_one(
            {"_id": result_doc.get("workflow")}, {"user_id": 1, "team_id": 1},
        ) if result_doc.get("workflow") else None
        workflow_doc = workflow_doc or {}
        uuids = doc_uuids or ((result_doc.get("input_context") or {}).get("doc_uuids") or [])
        targets, passages = run_targets(result_doc)
        sys_config = db.system_config.find_one() or {}
        user_id = workflow_doc.get("user_id")
        payload = _trace(
            targets,
            _load_documents(db, uuids, skip_origin_workflow=str(result_doc.get("workflow") or "")),
            passages,
            model=_model_for(db, sys_config, result_doc.get("model"), user_id),
            sys_config=sys_config, user_id=user_id, team_id=workflow_doc.get("team_id"),
            # The deliverable first, and shown as its statements are settled.
            first={"final"}, publish=_publisher(db, oid),
        )
    except Exception as e:  # noqa: BLE001 — the run is done; this only loses the underlines
        logger.warning("Sourcing failed for run %s: %s", workflow_result_id, e)
        payload = {"version": 1, "status": "failed", "error": "Sources could not be traced for this run."}
    payload["finished_at"] = _now()
    db.workflow_result.update_one({"_id": oid}, {"$set": {"sourcing": payload}})
    return {"status": payload.get("status")}


@celery_app.task(
    bind=True,
    name="tasks.workflow_next.trace_test_sources",
    max_retries=0,
    soft_time_limit=TIME_BUDGET_SECONDS + 120,
    time_limit=TIME_BUDGET_SECONDS + 180,
)
def trace_test_sources(self, output, doc_uuids: list[str], passages: list[dict], model: str | None = None,
                       user_id: str | None = None):
    """Source a step test's output; the result is polled like the test."""
    try:
        db = _get_db()
        sys_config = db.system_config.find_one() or {}
        return _trace(
            {"test": output}, _load_documents(db, doc_uuids), passages or [],
            model=_model_for(db, sys_config, model, user_id),
            sys_config=sys_config, user_id=user_id, team_id=None,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Sourcing failed for a step test: %s", e)
        return {"version": 1, "status": "failed", "error": "Sources could not be traced for this test."}


def queue_test_sourcing(output, doc_uuids: list[str], passages: list[dict], model: str | None,
                        user_id: str | None) -> str | None:
    """Start sourcing a step test's output; the task id, or None. Never raises."""
    if not sourcing_enabled():
        return None
    try:
        return trace_test_sources.delay(output, list(doc_uuids or []), passages or [], model, user_id).id
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not queue sourcing for a step test: %s", e)
        return None
