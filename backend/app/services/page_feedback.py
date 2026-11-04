"""Questions and flags from a Page's viewers to its owner.

Support ticket: Pages go to team members and, through public links, to grant
administrators, PIs and sponsors, but only the owner could act on one. A
viewer couldn't ask about a figure or flag one, nothing would have shown the
owner such feedback, and a public page didn't say who owned it.

A viewer picks the part of the Page the question is about (a section heading
or a figure cell, listed by ``anchors``; the Page itself runs in a sandbox
with scripts blocked, so a click inside it can't reach the app) and writes a
short question. Team members with access can always ask. Public-link viewers
can ask only when the owner turned on ``public_questions`` for the page, and
they leave an email address for the answer.

The owner gets a bell notification linking to the question, with the spot
highlighted on the page (``mark``). The owner answers in Vandalizer: a team
member gets the answer in their bell, a public asker by email, and with
"Show on page" the answer appears under the Page for everyone viewing that
version.
"""

from __future__ import annotations

import hashlib
import re
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup, Tag
from fastapi import HTTPException
from pymongo.database import Database

MAX_MESSAGE = 2000
MAX_ANSWER = 4000
MAX_ANCHORS = 300
MAX_OPEN_PER_PAGE = 200
_FIGURE = re.compile(r"\$\s?\d|\d\s?%|\d{1,3}(?:,\d{3})+")
_EMAIL = re.compile(r"^[^@\s<>]{1,64}@[^@\s<>]{1,255}\.[A-Za-z]{2,}$")
_MARK_STYLE = "outline:3px solid #f1b300;outline-offset:2px;background:#fff8e5"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# What a question can be about
# ---------------------------------------------------------------------------


def _anchor_elements(soup: BeautifulSoup) -> list[tuple[str, str, Tag]]:
    """(id, label, element) for each heading and each figure cell, in page order.

    Ids come from the element's position, so the same HTML always yields the
    same ids; a revision's HTML never changes, so an id stays valid for it.
    """
    out: list[tuple[str, str, Tag]] = []
    body = soup.body or soup
    for index, heading in enumerate(body.find_all(["h1", "h2", "h3", "h4"])):
        text = heading.get_text(" ", strip=True)
        if text:
            out.append((f"h{index}", f"Section: {text[:80]}", heading))
    for t, table in enumerate(body.find_all("table")):
        rows = table.find_all("tr")
        header = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])] if rows else []
        for r, row in enumerate(rows):
            cells = row.find_all(["th", "td"])
            label = next((c.get_text(" ", strip=True) for c in cells
                          if re.search(r"[A-Za-z]", c.get_text()) and not _FIGURE.search(c.get_text())), "")
            for c, cell in enumerate(cells):
                text = cell.get_text(" ", strip=True)
                if r == 0 or not _FIGURE.search(text):
                    continue
                column = header[c] if c < len(header) else ""
                where = " · ".join(p for p in (label[:50], column[:30]) if p)
                out.append((f"t{t}r{r}c{c}", f"{where} · {text[:40]}" if where else text[:40], cell))
    return out[:MAX_ANCHORS]


def anchors(html: str) -> list[dict[str, str]]:
    return [{"id": i, "label": label} for i, label, _el in _anchor_elements(BeautifulSoup(html or "", "html.parser"))]


def mark(soup: BeautifulSoup, anchor_id: str | None) -> None:
    """Highlight the anchored element in place (rendering only)."""
    if not anchor_id:
        return
    for i, _label, element in _anchor_elements(soup):
        if i == anchor_id:
            element["style"] = f"{element.get('style') or ''};{_MARK_STYLE}".lstrip(";")
            element["id"] = element.get("id") or "vandalizer-feedback-mark"
            return


# ---------------------------------------------------------------------------
# Who shared it
# ---------------------------------------------------------------------------


def shared_by(db: Database[dict], doc: dict) -> str | None:
    """"Shared by Jane Doe, University of Idaho Office of Sponsored Programs"."""
    settings = doc.get("sharing_contact") or {}
    if settings.get("hide_owner_name"):
        label = (settings.get("contact_label") or "").strip()
        return f"Shared by {label}" if label else None
    user = db.user.find_one({"user_id": doc["user_id"]}, {"name": 1, "organization_id": 1}) or {}
    name = (user.get("name") or "").strip()
    if not name:
        return None
    org_text = _organization(db, user.get("organization_id"))
    return f"Shared by {name}, {org_text}" if org_text else f"Shared by {name}"


def _organization(db: Database[dict], org_uuid: str | None) -> str | None:
    if not org_uuid:
        return None
    org = db.organization.find_one({"uuid": org_uuid}, {"name": 1, "parent_id": 1})
    if not org:
        return None
    names = [org["name"]]
    current = org
    for _ in range(6):
        if not current.get("parent_id"):
            break
        current = db.organization.find_one({"uuid": current["parent_id"]}, {"name": 1, "parent_id": 1}) or {}
        if current.get("name"):
            names.append(current["name"])
    root, own = names[-1], names[0]
    return own if root == own else f"{root} {own}"


def update_settings(db: Database[dict], doc: dict, public_questions: bool | None,
                    hide_owner_name: bool | None, contact_label: str | None) -> dict:
    update: dict[str, Any] = {}
    if public_questions is not None:
        update["public_questions"] = bool(public_questions)
    if hide_owner_name is not None:
        update["sharing_contact.hide_owner_name"] = bool(hide_owner_name)
    if contact_label is not None:
        update["sharing_contact.contact_label"] = contact_label.strip()[:120]
    if update:
        db.html_artifacts.update_one({"uuid": doc["uuid"], "user_id": doc["user_id"]}, {"$set": update})
    fresh = db.html_artifacts.find_one({"uuid": doc["uuid"]})
    return fresh or doc


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


def _anchor_label(html: str, anchor_id: str | None) -> str | None:
    if not anchor_id:
        return None
    for item in anchors(html):
        if item["id"] == anchor_id:
            return item["label"]
    raise HTTPException(422, "Choose a part of the page from the list, or ask about the whole page.")


def create(db: Database[dict], doc: dict, revision: dict, *, message: str, anchor_id: str | None,
           asker: dict) -> dict:
    message = (message or "").strip()
    if not message:
        raise HTTPException(422, "Write your question or note.")
    if len(message) > MAX_MESSAGE:
        raise HTTPException(422, f"Keep it to {MAX_MESSAGE} characters.")
    if db.page_feedback.count_documents({"artifact_uuid": doc["uuid"], "status": "open"}) >= MAX_OPEN_PER_PAGE:
        raise HTTPException(429, "This page has too many open questions. Try again after the owner answers some.")
    version = next((i for i, r in enumerate(doc["revisions"], 1) if r["uuid"] == revision["uuid"]), None)
    item = {
        "uuid": uuid_mod.uuid4().hex,
        "artifact_uuid": doc["uuid"],
        "owner_user_id": doc["user_id"],
        "revision": revision["uuid"],
        "version": version,
        "page_title": doc.get("title") or revision["title"],
        "anchor_id": anchor_id or None,
        "anchor_label": _anchor_label(revision["html"], anchor_id),
        "message": message,
        "asker": asker,
        "status": "open",
        "answer": None,
        "created_at": _now(),
    }
    db.page_feedback.insert_one(dict(item))
    return item


def list_for_owner(db: Database[dict], artifact_uuid: str) -> list[dict]:
    rows = list(db.page_feedback.find({"artifact_uuid": artifact_uuid}).sort("created_at", -1).limit(200))
    return [serialize(r, owner=True) for r in rows]


def answer(db: Database[dict], doc: dict, feedback_uuid: str, text: str, show_on_page: bool) -> dict:
    text = (text or "").strip()
    if not text:
        raise HTTPException(422, "Write an answer.")
    if len(text) > MAX_ANSWER:
        raise HTTPException(422, f"Keep the answer to {MAX_ANSWER} characters.")
    item = db.page_feedback.find_one({"uuid": feedback_uuid, "artifact_uuid": doc["uuid"]})
    if not item:
        raise HTTPException(404, "Question not found")
    answer_doc = {"text": text, "answered_at": _now(), "show_on_page": bool(show_on_page)}
    db.page_feedback.update_one({"uuid": feedback_uuid}, {"$set": {"answer": answer_doc, "status": "answered"}})
    item.update(answer=answer_doc, status="answered")
    return item


def close(db: Database[dict], doc: dict, feedback_uuid: str) -> None:
    result = db.page_feedback.update_one(
        {"uuid": feedback_uuid, "artifact_uuid": doc["uuid"]}, {"$set": {"status": "closed"}},
    )
    if not result.matched_count:
        raise HTTPException(404, "Question not found")


def page_notes(db: Database[dict], artifact_uuid: str, revision_uuid: str) -> list[dict]:
    """Answers the owner chose to show under this version of the page."""
    rows = db.page_feedback.find({
        "artifact_uuid": artifact_uuid, "revision": revision_uuid, "answer.show_on_page": True,
    }).sort("created_at", 1).limit(50)
    return [{"about": r.get("anchor_label"), "question": r["message"], "answer": r["answer"]["text"],
             "answered_at": r["answer"]["answered_at"]} for r in rows]


def serialize(item: dict, owner: bool = False) -> dict:
    asker = item.get("asker") or {}
    out = {
        "uuid": item["uuid"], "artifact_uuid": item["artifact_uuid"], "revision": item["revision"],
        "version": item.get("version"), "anchor_id": item.get("anchor_id"), "anchor_label": item.get("anchor_label"),
        "message": item["message"], "status": item["status"], "answer": item.get("answer"),
        "created_at": item["created_at"],
    }
    if owner:
        out["asker"] = {"kind": asker.get("kind"), "name": asker.get("name"), "email": asker.get("email")}
    return out


def ip_key(ip: str | None) -> str:
    return hashlib.sha256((ip or "").encode()).hexdigest()[:16]


def valid_email(value: str) -> bool:
    return bool(_EMAIL.match((value or "").strip()))
