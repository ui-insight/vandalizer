"""What a workflow run needs on record to be reproduced.

Evaluation work drives workflows through the API and has to log, per run, the
model that actually answered (its configured name, not a tag like "fast") and
every Vandalizer setting that shaped the result. The run already knew less
than that: ``WorkflowResult.model`` is the run's *default*, which a step's own
model, an optimizer override, a pinned extraction model or a fallback retry
can each replace.

Three sources, combined for the status endpoint by :func:`describe_run`:

- **Request settings**, captured at the MeteredModel chokepoint every LLM call
  goes through (:func:`request_fingerprint`), so what is reported is what was
  sent — including two-pass extraction sending one model two configurations.
- **The run's configuration**, snapshotted when the engine is built
  (:func:`build_run_config`): Vandalizer version, workflow version, a hash of
  the fully resolved step definitions, the optimizer override, the extraction
  config, and a hash of each input document's text.
- **Model configs** from System Config for each model the run called
  (:func:`model_config_snapshot`), taken when the pass ends, since an admin can
  edit a model's temperature or context window between runs.

Nothing here may carry a secret: model configs are copied through an
allow-list, and endpoints are reduced to their host.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping

import hashlib
import json
import logging
from typing import Optional, TypeVar, TypedDict, Unpack
from pymongo.database import Database
from pydantic_ai.models import Model, ModelRequestParameters
from app.services.metering import MeterScope
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Model settings that change what a provider returns. Transport-only settings
# (timeout, retries) are left out.
_REQUEST_SETTING_KEYS = (
    "temperature",
    "top_p",
    "max_tokens",
    "seed",
    "presence_penalty",
    "frequency_penalty",
    "stop_sequences",
    "thinking",
    "extra_body",
    "anthropic_thinking",
    "openai_reasoning_effort",
)

# System Config model fields that are safe to report and bear on the result.
# An allow-list, not a deny-list: the config also holds the (encrypted) API key.
_MODEL_CONFIG_KEYS = (
    "name",
    "tag",
    "external",
    "thinking",
    "temperature",
    "context_window",
    "response_reserve_tokens",
    "supports_structured",
    "multimodal",
    "supports_pdf",
)

# Task data the run builder attaches at runtime: the documents' text (hashed
# separately, per document) and the owner's id. Kept out of the definition
# hash so it changes when the configuration does and only then.
_RUNTIME_TASK_KEYS = frozenset({
    "user_id",
    "doc_texts",
    "doc_metas",
    "selected_doc_text",
    "selected_doc_meta",
})


def endpoint_host(url: Optional[str]) -> Optional[str]:
    """``scheme://host[:port]`` of an endpoint — never its path, query or userinfo."""
    if not url:
        return None
    try:
        parsed = urlparse(str(url))
    except ValueError:
        return None
    if not parsed.hostname:
        return None
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}" if parsed.scheme else host


T = TypeVar("T")


def _json_safe(value: dict) -> dict:
    # A JSON object round trip preserves the root mapping; nested runtime
    # values are encoded as strings when JSON has no representation for them.
    decoded: dict = json.loads(json.dumps(value, sort_keys=True, default=str))
    return decoded


def request_fingerprint(
    model: Model, model_settings: Mapping[str, object] | None, model_request_parameters: ModelRequestParameters | None = None,
) -> dict:
    """The parts of one LLM request that determine its answer.

    ``model`` is the MeteredModel making the call. Never raises: metering must
    not break an LLM call, so a field that can't be read is left out.
    """
    from app.services.llm_service import unwrap_model_base_url

    fp: dict = {}
    configured = getattr(model, "configured_model", None)
    if configured:
        fp["configured_model"] = configured
    try:
        fp["provider"] = model.system
    except Exception:
        pass
    try:
        host = endpoint_host(unwrap_model_base_url(model))
        if host:
            fp["endpoint"] = host
    except Exception:
        pass
    settings = model_settings or {}
    for key in _REQUEST_SETTING_KEYS:
        if key in settings and settings[key] is not None:
            fp[key] = settings[key]
    mode = getattr(model_request_parameters, "output_mode", None)
    if mode:
        fp["output_mode"] = mode
    try:
        return _json_safe(fp)
    except Exception:
        return {}


def model_config_snapshot(name: str, sys_config: Optional[dict]) -> dict:
    """The System Config entry for model ``name``, through the allow-list.

    A name no configured model carries (a model removed since, or one the
    provider reported under a prefix-stripped name) still gets an entry, so
    the caller can see it was looked up and found nothing.
    """
    from app.services.llm_service import _get_model_config_sync, detect_api_protocol

    config = _get_model_config_sync(name, sys_config)
    if not config:
        return {"name": name, "configured": False}
    snap = {k: config[k] for k in _MODEL_CONFIG_KEYS if k in config}
    snap["name"] = name
    snap["configured"] = True
    snap["api_protocol"] = detect_api_protocol(name, config)
    timeout = config.get("request_timeout_seconds")
    if timeout:
        snap["request_timeout_seconds"] = timeout
    host = endpoint_host((config.get("endpoint") or "").strip()) or endpoint_host(
        (sys_config or {}).get("llm_endpoint")
    )
    if host:
        snap["endpoint"] = host
    return _json_safe(snap)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _definition_view(steps_data: list[dict]) -> list[dict]:
    """``steps_data`` minus the runtime attachments, bytes replaced by a hash."""

    def clean(value: object) -> object:
        if isinstance(value, (bytes, bytearray)):
            return {"sha256": hashlib.sha256(bytes(value)).hexdigest()}
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(v) for v in value]
        return value

    view = []
    for step in steps_data:
        if step.get("name") == "Document":
            continue
        view.append({
            "name": step.get("name", ""),
            "data": clean(step.get("data") or {}),
            "tasks": [
                {
                    "name": t.get("name", ""),
                    "data": clean({
                        k: v for k, v in (t.get("data") or {}).items()
                        if k not in _RUNTIME_TASK_KEYS
                    }),
                }
                for t in step.get("tasks", [])
            ],
        })
    return view


def _configured_steps(steps_data: list[dict]) -> list[dict]:
    """Each step's tasks with the model and variant they were built with."""
    steps = []
    for index, step in enumerate(steps_data):
        if step.get("name") == "Document":
            continue
        tasks = []
        for task in step.get("tasks", []):
            data = task.get("data") or {}
            entry: dict = {"type": task.get("name", "")}
            for src, dst in (
                ("model", "model"),
                ("_fallback_model", "fallback_model"),
                ("prompt_variant", "prompt_variant"),
            ):
                if data.get(src):
                    entry[dst] = data[src]
            tasks.append(entry)
        steps.append({"index": index, "name": step.get("name", ""), "tasks": tasks})
    return steps


def _input_documents(db: Database[dict], workflow_doc: dict, trigger_step_data: dict) -> list[dict]:
    uuids = list((trigger_step_data or {}).get("doc_uuids") or [])
    input_cfg = workflow_doc.get("input_config") or {}
    if input_cfg.get("trigger_type") != "no_input":
        for fd in input_cfg.get("fixed_documents") or []:
            fd_uuid = fd.get("uuid") if isinstance(fd, dict) else str(fd)
            if fd_uuid and fd_uuid not in uuids:
                uuids.append(fd_uuid)
    docs = []
    for uuid in uuids:
        doc = db.smart_document.find_one(
            {"uuid": uuid}, {"uuid": 1, "title": 1, "extension": 1, "raw_text": 1},
        )
        if not doc:
            docs.append({"uuid": uuid, "found": False})
            continue
        text = doc.get("raw_text") or ""
        docs.append({
            "uuid": uuid,
            "title": doc.get("title"),
            "extension": doc.get("extension"),
            "text_chars": len(text),
            "text_sha256": _hash_text(text) if text else None,
        })
    return docs


def build_run_config(
    db: Database[dict],
    *,
    workflow_doc: dict,
    steps_data: list[dict],
    trigger_step_data: dict,
    model: Optional[str],
    sys_config: Optional[dict],
    config_override: Optional[dict],
) -> dict:
    """Snapshot the configuration a run's engine was built from.

    Call after ``build_workflow_engine``: the builder writes each task's
    resolved model, fallback and prompt variant into ``steps_data``, and those
    belong in the record.
    """
    from app.services.extraction_engine import ExtractionEngine
    from app.services.quality_service import compute_config_hash
    from app.services.version_service import get_current_version

    definition = _definition_view(steps_data)
    try:
        extraction_config = ExtractionEngine(
            system_config_doc=sys_config or {},
        )._get_extraction_config_from_sys()
    except Exception:
        logger.warning("Could not snapshot the extraction config", exc_info=True)
        extraction_config = None
    return _json_safe({
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "vandalizer_version": get_current_version(),
        "workflow": {
            "id": str(workflow_doc.get("_id")) if workflow_doc.get("_id") else None,
            "name": workflow_doc.get("name"),
            "version": workflow_doc.get("version"),
            "definition_hash": compute_config_hash(_json_safe({"steps": definition})),
            "config_override": config_override or None,
        },
        "default_model": model,
        "steps": _configured_steps(steps_data),
        "extraction_config": extraction_config,
        "documents": _input_documents(db, workflow_doc, trigger_step_data),
    })


class RunConfigInput(TypedDict):
    workflow_doc: dict
    steps_data: list[dict]
    trigger_step_data: dict
    model: str | None
    sys_config: dict | None
    config_override: dict | None


def snapshot_run_config(db: Database[dict], workflow_result_id: object, **kwargs: Unpack[RunConfigInput]) -> None:
    """Store :func:`build_run_config` on the run, once.

    The first pass wins: a retry or approval resume rebuilds the engine, and
    the record should describe the run as it started. Best-effort — a run must
    not fail because its record could not be written.
    """
    from bson import ObjectId

    try:
        config = build_run_config(db, **kwargs)
        db.workflow_result.update_one(
            {"_id": ObjectId(str(workflow_result_id)), "run_config": None},
            {"$set": {"run_config": config}},
        )
    except Exception:
        logger.warning(
            "Could not record the run config for workflow result %s",
            workflow_result_id, exc_info=True,
        )


def record_pass_usage(db: Database[dict], workflow_result_id: object, scope: MeterScope | None, sys_config: Optional[dict]) -> None:
    """Append one execution pass's per-step model usage to the run.

    Appended, not set: a retried or approval-resumed run executes in several
    passes, each with its own metering scope. Best-effort.
    """
    from bson import ObjectId

    from app.services.metering import model_usage_rows

    try:
        rows = model_usage_rows(scope)
        if not rows:
            return
        names: list[str] = []
        for row in rows:
            for fp in row.get("settings") or [{}]:
                name = fp.get("configured_model") or row.get("model")
                if name and name not in names:
                    names.append(name)
        configs = [model_config_snapshot(n, sys_config) for n in names]
        db.workflow_result.update_one(
            {"_id": ObjectId(str(workflow_result_id))},
            {"$push": {
                "model_usage": {"$each": [_json_safe(row) for row in rows]},
                "model_configs": {"$each": configs},
            }},
        )
    except Exception:
        logger.warning(
            "Could not record model usage for workflow result %s",
            workflow_result_id, exc_info=True,
        )


def _merge_usage(rows: list[dict]) -> list[dict]:
    """Fold several passes' rows into one per (step, model), settings deduped."""
    merged: dict[tuple, dict] = {}
    for row in rows or []:
        key = (row.get("step_index"), row.get("step"), row.get("model"))
        entry = merged.get(key)
        if entry is None:
            entry = merged[key] = {
                "step_index": key[0], "step": key[1], "model": key[2],
                "tokens_input": 0, "tokens_output": 0, "requests": 0,
                "settings": [],
            }
        entry["tokens_input"] += row.get("tokens_input") or 0
        entry["tokens_output"] += row.get("tokens_output") or 0
        entry["requests"] += row.get("requests") or 0
        for fp in row.get("settings") or []:
            if fp not in entry["settings"]:
                entry["settings"].append(fp)
    return sorted(
        merged.values(),
        key=lambda r: (r["step_index"] is None, r["step_index"] or 0, str(r["model"])),
    )


def describe_run(result: object) -> Optional[dict]:
    """The ``run_metadata`` block of a run's status payload.

    ``None`` for a run with nothing recorded (it predates this, or never
    reached a worker).
    """
    from app.services.metering import summarize_model_usage

    def field(name: str, kind: type[T]) -> T | None:
        value = getattr(result, name, None)
        return value if isinstance(value, kind) else None

    run_config = field("run_config", dict)
    usage = field("model_usage", list) or []
    if not run_config and not usage:
        return None

    configs: dict[str, dict] = {}
    for cfg in field("model_configs", list) or []:
        name = cfg.get("name") if isinstance(cfg, dict) else None
        if name and name not in configs:
            configs[name] = cfg

    return {
        **(run_config or {}),
        "default_model": (run_config or {}).get("default_model") or field("model", str),
        # The models whose calls were metered, most tokens first.
        "models_used": summarize_model_usage(usage)["models"],
        "model_usage": _merge_usage(usage),
        "model_configs": list(configs.values()),
    }
