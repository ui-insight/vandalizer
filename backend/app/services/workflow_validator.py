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

Both helpers are unchanged from the original Flask port so existing import
sites continue to work without edits.
"""

from __future__ import annotations

import json
import re

__all__ = ["_extract_json", "_resolve_model_name"]


def _get_db():
    from pymongo import MongoClient

    from app.config import Settings
    settings = Settings()
    return MongoClient(settings.mongo_host)[settings.mongo_db]


def _resolve_model_name(user_id: str | None = None) -> str:
    """Resolve model name using user config, falling back to system default.

    Synchronous (pymongo). Returns "" when no model can be resolved — callers
    should treat that as "no LLM configured" and skip or raise as appropriate.
    """
    db = _get_db()
    if user_id:
        user_config = db.user_model_config.find_one({"user_id": user_id})
        if user_config and user_config.get("name"):
            return user_config["name"]
    sys_cfg = db.system_config.find_one() or {}
    models = sys_cfg.get("available_models", [])
    if models and isinstance(models[0], dict):
        return models[0].get("name", "")
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
