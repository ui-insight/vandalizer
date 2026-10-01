"""Validation helpers — shared LLM-output parsing + model resolution.

This module previously contained a full Flask-port plan generator + check
runner + scorer (PlanGenerator / CheckRunner / Scorer), but those were
superseded by the user-facing validation flow in :mod:`app.services.workflow_service`
(``generate_validation_plan``, ``_evaluate_checks_against_output``,
``_build_result``). The Flask port had no remaining callers and was deleted.

What remains here are the two small synchronous helpers that several KB /
extraction / workflow modules still depend on:

* ``_extract_json`` — strip markdown fences and pull a JSON object/list out
  of free-form LLM output.
* ``_resolve_model_name`` — synchronous (pymongo) lookup of the user's
  configured model name, with a system-default fallback. Used by Celery
  workers and other sync code paths where the async ``get_user_model_name``
  isn't available.

``_extract_json`` is unchanged from the original Flask port;
``_resolve_model_name`` now resolves tags and stale names the way the async
resolver does.
"""

from __future__ import annotations

import json
import re

__all__ = ["_extract_json", "_resolve_model_name"]


def _get_db():
    from app.tasks import get_sync_db

    return get_sync_db()


def _resolve_model_name(user_id: str | None = None) -> str:
    """Resolve model name using user config, falling back to system default.

    Synchronous (pymongo) twin of ``config_service.get_user_model_name`` and
    resolves the same way: the user's stored value may be a model's name or
    its tag, and only a value naming a *configured* model is used. It used to
    return the stored value verbatim, so a tag ("fast") or a model since
    renamed or removed in System Config reached the LLM layer as a bare name
    with no config — which ``detect_api_protocol`` reads as a local Ollama
    model and dials at the built-in ``http://localhost:11434/v1``. Inside the
    container nothing listens there (Sentry 7703225327: KB baseline probe,
    "Connection error." on every call).

    Returns "" when no model can be resolved — callers should treat that as
    "no LLM configured" and skip or raise as appropriate.
    """
    db = _get_db()
    sys_cfg = db.system_config.find_one() or {}
    models = [m for m in (sys_cfg.get("available_models") or []) if isinstance(m, dict)]

    def _configured(value: str | None) -> str:
        if not value:
            return ""
        for key in ("name", "tag"):
            for m in models:
                if m.get(key) == value and m.get("name"):
                    return m["name"]
        return ""

    if user_id:
        user_config = db.user_model_config.find_one({"user_id": user_id})
        resolved = _configured((user_config or {}).get("name"))
        if resolved:
            return resolved

    default = (sys_cfg.get("default_model") or "").strip()
    if default and any(m.get("name") == default for m in models):
        return default
    for m in models:
        if m.get("name"):
            return m["name"]
    return ""


def _extract_json(text: str) -> dict | list:
    """Extract JSON from LLM text output, handling markdown fences.

    Raises ``ValueError`` when nothing parses — callers should treat the LLM
    response as malformed.
    """
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for i, ch in enumerate(text):
        if ch in ("{", "["):
            try:
                return json.loads(text[i:])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Could not extract JSON from LLM output: {text[:200]}")
