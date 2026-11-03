"""Living Pages: the files a Page was built from, and whether they changed.

Each saved revision records ``source.documents`` — the files the page was
built from, as ``{uuid, title, version_number}``. When one of those files gets
a new version ("Upload new version" on the file), the Page screen shows what
changed and offers to update the page through the usual chat preview, the
owner gets a bell notification, and a published link says newer data exists.

Staleness is derived at read time from the file's version chain
(``SmartDocument.superseded_by``), so nothing has to be kept in sync when a
version is uploaded or deleted.
"""
from __future__ import annotations

import difflib
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pymongo.database import Database

if TYPE_CHECKING:
    from app.models.document import SmartDocument

logger = logging.getLogger(__name__)

MAX_SOURCES = 20
MAX_CHAIN = 50
MAX_CHANGES = 8
_SNIPPET = 90
_DOC_FIELDS = {"uuid": 1, "title": 1, "version_number": 1, "superseded_by": 1, "soft_deleted": 1,
               "processing": 1, "task_status": 1, "created_at": 1, "user_id": 1, "team_id": 1}


def entry(doc: dict) -> dict:
    """The snapshot a revision keeps of one source file."""
    return {"uuid": doc["uuid"], "title": doc.get("title") or "Untitled file",
            "version_number": doc.get("version_number") or 1}


def resolve(db: Database[dict], uuids: list[str]) -> list[dict]:
    """Snapshot entries for ``uuids`` (already authorized), in order, deduplicated."""
    seen: list[str] = []
    for uuid in uuids:
        if isinstance(uuid, str) and uuid and uuid not in seen:
            seen.append(uuid)
    if not seen:
        return []
    found = {d["uuid"]: d for d in db.smart_document.find({"uuid": {"$in": seen[:MAX_SOURCES]}}, _DOC_FIELDS)}
    return [entry(found[u]) for u in seen[:MAX_SOURCES] if u in found]


def revision_sources(revision: dict) -> list[dict]:
    documents = (revision.get("source") or {}).get("documents") or []
    return [d for d in documents if isinstance(d, dict) and d.get("uuid")]


def lineage(db: Database[dict], uuid: str) -> str | None:
    doc = db.smart_document.find_one({"uuid": uuid}, {"uuid": 1, "version_root": 1})
    if not doc:
        return None
    root: str = doc.get("version_root") or doc["uuid"]
    return root


def carry_forward(db: Database[dict], previous: list[dict], used: list[str]) -> list[str]:
    """Sources for a revised page: the previous ones, each swapped for a newer
    version of the same file when this turn used one."""
    roots = {lineage(db, u): u for u in used}
    result = [roots.get(lineage(db, d["uuid"])) or d["uuid"] for d in previous]
    return result if result else used


def _head(db: Database[dict], doc: dict) -> dict:
    """Follow ``superseded_by`` to the newest stored version."""
    current = doc
    for _ in range(MAX_CHAIN):
        nxt = current.get("superseded_by")
        if not nxt:
            break
        found = db.smart_document.find_one({"uuid": nxt}, _DOC_FIELDS)
        if not found or found.get("soft_deleted"):
            break
        current = found
    return current


def _text(db: Database[dict], uuid: str) -> str:
    doc = db.smart_document.find_one({"uuid": uuid}, {"raw_text": 1})
    return str((doc or {}).get("raw_text") or "")


def freshness(db: Database[dict], documents: list[dict], *, changes: bool = False) -> list[dict]:
    """Each source with ``status``: current, updated (a newer version exists) or missing."""
    result = []
    for source in documents[:MAX_SOURCES]:
        item: dict[str, Any] = {"uuid": source["uuid"], "title": source.get("title") or "Untitled file",
                                "version_number": source.get("version_number") or 1}
        doc = db.smart_document.find_one({"uuid": source["uuid"]}, _DOC_FIELDS)
        if not doc or doc.get("soft_deleted"):
            result.append({**item, "status": "missing"})
            continue
        head = _head(db, doc)
        if head["uuid"] == doc["uuid"]:
            result.append({**item, "status": "current"})
            continue
        created = head.get("created_at")
        ready = not head.get("processing") and head.get("task_status") not in {"error", "failed"}
        latest = {"uuid": head["uuid"], "title": head.get("title") or "Untitled file",
                  "version_number": head.get("version_number") or 1,
                  "created_at": created.isoformat() if isinstance(created, datetime) else None,
                  "ready": ready}
        updated: dict[str, Any] = {**item, "status": "updated", "latest": latest}
        if changes and ready:
            updated["changes"] = summarize_changes(_text(db, doc["uuid"]), _text(db, head["uuid"]))
        result.append(updated)
    return result


def newer_data_available(db: Database[dict], revision: dict) -> bool:
    return any(s["status"] == "updated" for s in freshness(db, revision_sources(revision)))


# ── Change summary ──────────────────────────────────────────────────────────

_SEPARATOR = re.compile(r"^:?-{2,}:?$")


def _cells(line: str) -> list[str] | None:
    text = line.strip()
    if len(text) < 2 or not text.startswith("|") or not text.endswith("|"):
        return None
    return [c.strip() for c in text[1:-1].split("|")]


def _parse(text: str) -> tuple[dict[tuple, tuple[list[str], list[str]]], list[str], set[str]]:
    """Table rows keyed by (sheet, row label, occurrence), plus the other lines.

    Spreadsheets are read as Markdown tables under ``## Sheet`` headings; the
    first row of each table is its header.
    """
    rows: dict[tuple, tuple[list[str], list[str]]] = {}
    other: list[str] = []
    sheets: set[str] = set()
    sheet, header = "", None
    seen: dict[tuple, int] = {}
    for line in text.splitlines():
        cells = _cells(line)
        if cells is None:
            header = None
            stripped = line.strip()
            if stripped.startswith("## "):
                sheet = stripped[3:].strip()
                sheets.add(sheet)
            elif stripped:
                other.append(stripped)
            continue
        if all(_SEPARATOR.match(c) for c in cells if c):
            continue
        if header is None:
            header = cells
            continue
        label = next((c for c in cells if c), "")
        base = (sheet, label)
        seen[base] = seen.get(base, 0) + 1
        rows[(sheet, label, seen[base])] = (header, cells)
    return rows, other, sheets


def _clip(text: str) -> str:
    return text if len(text) <= _SNIPPET else text[:_SNIPPET - 1].rstrip() + "…"


def _line_change(old: str, new: str) -> str:
    """The differing middle of two lines, word-trimmed."""
    a, b = old.split(), new.split()
    start = 0
    while start < min(len(a), len(b)) and a[start] == b[start]:
        start += 1
    end = 0
    while end < min(len(a), len(b)) - start and a[-1 - end] == b[-1 - end]:
        end += 1
    context = " ".join(a[max(0, start - 3):start])
    old_mid = " ".join(a[start:len(a) - end]) or "(nothing)"
    new_mid = " ".join(b[start:len(b) - end]) or "(nothing)"
    prefix = f"{_clip(context)}: " if context else ""
    return f"{prefix}{_clip(old_mid)} → {_clip(new_mid)}"


def summarize_changes(old_text: str, new_text: str) -> dict:
    """A short, human list of what changed between two versions of a file."""
    old_rows, old_other, old_sheets = _parse(old_text)
    new_rows, new_other, new_sheets = _parse(new_text)
    many_sheets = len(old_sheets | new_sheets) > 1
    changes: list[str] = []

    def where(key: tuple) -> str:
        return f"{key[0]} · {key[1]}" if many_sheets and key[0] else str(key[1])

    for key, (header, cells) in new_rows.items():
        if key not in old_rows:
            changes.append(f"Added row: {_clip(where(key))}")
            continue
        old_header, old_cells = old_rows[key]
        for i in range(max(len(cells), len(old_cells))):
            before = old_cells[i] if i < len(old_cells) else ""
            after = cells[i] if i < len(cells) else ""
            if before == after:
                continue
            column = header[i] if i < len(header) and header[i] else f"column {i + 1}"
            changes.append(f"{_clip(where(key))} · {_clip(column)}: {_clip(before) or '(blank)'} → {_clip(after) or '(blank)'}")
    for key in old_rows:
        if key not in new_rows:
            changes.append(f"Removed row: {_clip(where(key))}")

    matcher = difflib.SequenceMatcher(a=old_other, b=new_other, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        pairs = min(i2 - i1, j2 - j1) if op == "replace" else 0
        for k in range(pairs):
            changes.append(_line_change(old_other[i1 + k], new_other[j1 + k]))
        changes.extend(f"Removed: {_clip(line)}" for line in old_other[i1 + pairs:i2])
        changes.extend(f"Added: {_clip(line)}" for line in new_other[j1 + pairs:j2])

    return {"items": changes[:MAX_CHANGES], "more": max(0, len(changes) - MAX_CHANGES),
            "total": len(changes)}


# ── Owner notification ──────────────────────────────────────────────────────

async def notify_source_revised(previous: "SmartDocument", latest: "SmartDocument") -> None:
    """Tell each owner whose page was built from ``previous`` that it changed.

    Only pages whose latest revision used that version. Never raises: the
    upload already succeeded.
    """
    try:
        from app.models.artifact import Artifact
        from app.services.notification_service import create_notification

        cursor = Artifact.get_motor_collection().find(
            {"deleted_at": None, "revisions.source.documents.uuid": previous.uuid},
            {"uuid": 1, "user_id": 1, "title": 1, "latest_revision": 1, "revisions.uuid": 1,
             "revisions.source.documents.uuid": 1},
        )
        async for page in cursor:
            latest_revision: dict = next((r for r in page.get("revisions", []) if r.get("uuid") == page.get("latest_revision")), {})
            if previous.uuid not in {d.get("uuid") for d in revision_sources(latest_revision)}:
                continue
            await create_notification(
                user_id=page["user_id"], kind="page_source_updated",
                title=f"New version of {latest.title}",
                body=f"“{page.get('title') or 'Your page'}” was built from version {previous.version_number or 1}. "
                     "Review what changed and update the page.",
                link=f"/pages/{page['uuid']}", item_kind="page", item_id=page["uuid"],
                item_name=page.get("title"), coalesce_key=f"page-source:{page['uuid']}",
            )
    except Exception:
        logger.exception("Could not notify page owners about new version %s", latest.uuid)
