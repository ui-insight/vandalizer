""""Run now" for an automation: pick the documents its trigger would pick.

An automation could only be tested by making its trigger fire for real —
uploading into the watched folder, calling the API, or waiting for the
schedule — and if the output settings were wrong that sent a real email to
real people. Running the workflow on its own proves only the workflow.

A manual run goes through exactly the passive pipeline a real trigger uses
(trigger event → execute → output delivery), so storage, notifications and
webhooks fire as configured. The only thing this module decides is *which
documents* — the same way the trigger would:

* ``folder_watch``: the files currently in the watched folder that pass the
  automation's type / exclude-pattern filters (newest first, capped).
* ``schedule``: the configured document set, or the configured folder.
* ``api`` / ``m365_intake``: nothing arrives on its own, so the caller must
  choose documents.

A caller may always pass explicit documents; then they win.
"""

from __future__ import annotations

import fnmatch
from typing import Any

from app.models.automation import Automation
from app.models.document import SmartDocument

# A manual run is a test, not a backfill. Cap what a folder contributes so
# "Run now" on a folder with 400 files does not fan out 400 documents into one
# run; the response says how many matched so the cap is visible.
RUN_NOW_FOLDER_LIMIT = 25

TRIGGER_TYPES_NEEDING_DOCUMENTS = frozenset({"api", "m365_intake"})


def filter_documents_for_trigger(documents: list[dict], trigger_config: dict | None) -> list[dict]:
    """Apply a folder-watch automation's ``file_types`` and ``exclude_patterns``
    the way the upload path does (``document_tasks``), so a manual run picks up
    the same files a real upload would."""
    cfg = trigger_config or {}
    allowed_types = cfg.get("file_types") or []
    raw_patterns = cfg.get("exclude_patterns") or ""
    if isinstance(raw_patterns, str):
        patterns = [p.strip() for p in raw_patterns.split(",") if p.strip()]
    else:
        patterns = [str(p).strip() for p in raw_patterns if str(p).strip()]
    out: list[dict] = []
    for doc in documents:
        if allowed_types and (doc.get("extension") or "") not in allowed_types:
            continue
        title = doc.get("title") or ""
        if any(fnmatch.fnmatch(title, pat) for pat in patterns):
            continue
        out.append(doc)
    return out


async def _folder_documents(folder_id: str) -> list[dict]:
    docs = await SmartDocument.find(
        {"folder": folder_id, "processing": False, "soft_deleted": {"$ne": True}},
    ).sort("-created_at").to_list()
    return [{"uuid": d.uuid, "title": d.title, "extension": d.extension} for d in docs]


async def _documents_by_uuid(uuids: list[str]) -> list[dict]:
    if not uuids:
        return []
    docs = await SmartDocument.find({"uuid": {"$in": uuids}}).to_list()
    by_uuid = {d.uuid: d for d in docs}
    return [
        {"uuid": u, "title": by_uuid[u].title, "extension": by_uuid[u].extension}
        for u in uuids if u in by_uuid
    ]


async def select_run_now_documents(
    auto: Automation, *, chosen_uuids: list[str] | None = None,
) -> dict[str, Any]:
    """Decide the documents for a manual run.

    Returns ``{"documents": [{uuid, title, extension}], "source", "matched",
    "reason"}``. ``source`` is ``chosen`` / ``folder`` / ``configured``;
    ``matched`` is how many were eligible before the folder cap; ``reason``
    is set (and ``documents`` empty) when nothing can be selected — the
    message to show the user.
    """
    trigger_type = auto.trigger_type or "folder_watch"
    cfg = auto.trigger_config or {}

    if chosen_uuids:
        docs = await _documents_by_uuid(chosen_uuids)
        return {"documents": docs, "source": "chosen", "matched": len(docs), "reason": None}

    if trigger_type == "folder_watch":
        folder_id = cfg.get("folder_id")
        if not folder_id:
            return {"documents": [], "source": "folder", "matched": 0,
                    "reason": "This automation has no watched folder yet. Choose a folder in Trigger, then run again."}
        matched = filter_documents_for_trigger(await _folder_documents(folder_id), cfg)
        if not matched:
            return {"documents": [], "source": "folder", "matched": 0,
                    "reason": "The watched folder has no documents that pass this automation's file filters. "
                              "Add a file to the folder, or choose documents to run with."}
        return {"documents": matched[:RUN_NOW_FOLDER_LIMIT], "source": "folder",
                "matched": len(matched), "reason": None}

    if trigger_type == "schedule":
        uuids = cfg.get("document_uuids") or []
        if uuids:
            docs = await _documents_by_uuid(list(uuids))
            if not docs:
                return {"documents": [], "source": "configured", "matched": 0,
                        "reason": "None of this schedule's configured documents exist any more."}
            return {"documents": docs, "source": "configured", "matched": len(docs), "reason": None}
        folder_id = cfg.get("folder_id")
        if folder_id:
            matched = await _folder_documents(folder_id)
            if not matched:
                return {"documents": [], "source": "folder", "matched": 0,
                        "reason": "The scheduled folder has no documents."}
            return {"documents": matched[:RUN_NOW_FOLDER_LIMIT], "source": "folder",
                    "matched": len(matched), "reason": None}
        return {"documents": [], "source": "configured", "matched": 0,
                "reason": "This schedule has no documents or folder configured. Choose documents to run with."}

    # api / m365_intake / anything else: documents arrive with the trigger.
    return {"documents": [], "source": "chosen", "matched": 0,
            "reason": "This trigger receives its documents when it fires. Choose documents to run with."}
