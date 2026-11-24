"""Questions and flags from a page's viewers to its owner, and the owner's answers.

Support ticket: pages reached team members and, through public links, grant
admins, PIs and sponsors, but only the owner could act on one. Nobody else
could ask about a figure, and a public page didn't say whose it was.

* A viewer picks a spot on the page (the embed script reports the element's
  path and text) and writes a short question or flag. Team members can always
  ask; public-link viewers only when the owner turned that on, with an
  optional email address so the answer can reach them.
* The owner gets a bell notification linking to the spot, and can answer,
  resolve it, or turn it into a Request changes.
* The answer reaches the asker: a bell notification for a team member, an
  email for a public viewer who left one, and, when the owner chooses, a
  short note on the page for everyone who opens it.
* Shared and public pages say who shared them.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.models.artifact import Artifact
from app.models.page_feedback import FeedbackAnchor, FeedbackAnswer, PageFeedback
from app.models.user import User

logger = logging.getLogger(__name__)

MAX_MESSAGE = 2000
MAX_ANCHOR_TEXT = 300
MAX_ANSWER = 4000
MAX_CONTACT = 200
# Open questions one public link may hold before more are refused, so a
# leaked link can't bury the owner.
MAX_OPEN_PUBLIC = 50
_EMAIL = re.compile(r"^[^@\s<>]{1,64}@[^@\s<>]{1,190}\.[A-Za-z]{2,24}$")
_PATH = re.compile(r"^\d{1,4}(?:/\d{1,4}){0,40}$")


def _clean(text: object, limit: int) -> str:
    return " ".join(str(text or "").split())[:limit]


def clean_anchor(raw: Any) -> FeedbackAnchor:
    raw = raw if isinstance(raw, dict) else {}
    path = raw.get("path")
    return FeedbackAnchor(
        path=path if isinstance(path, str) and _PATH.fullmatch(path) else None,
        text=_clean(raw.get("text"), MAX_ANCHOR_TEXT),
    )


def clean_email(value: object) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > 254 or not _EMAIL.fullmatch(text):
        raise ValueError("Enter a valid email address, or leave it blank.")
    return text


def settings_of(doc: dict) -> dict[str, Any]:
    stored = doc.get("feedback")
    raw: dict[str, Any] = stored if isinstance(stored, dict) else {}
    contact = raw.get("contact") if isinstance(raw.get("contact"), str) else None
    return {"public_questions": bool(raw.get("public_questions")), "contact": contact or None}


async def shared_by(doc: dict) -> str:
    """'Shared by <name>, <organization>' — or the owner's own contact line."""
    from app.models.organization import Organization
    from app.models.team import Team

    contact = settings_of(doc)["contact"]
    owner = await User.find_one(User.user_id == doc["user_id"])
    name = (owner.name if owner else None) or "the page's owner"
    if contact:
        return f"Shared by {name}, {contact}"
    where = None
    if owner and owner.organization_id:
        org = await Organization.find_one(Organization.uuid == owner.organization_id)
        where = org.name if org else None
    if not where and doc.get("team_id"):
        team = await Team.find_one(Team.uuid == doc["team_id"])
        where = team.name if team else None
    return f"Shared by {name}, {where}" if where else f"Shared by {name}"


def _version(doc: dict, revision: str) -> int:
    for i, rev in enumerate(doc.get("revisions") or [], 1):
        if rev.get("uuid") == revision:
            return int(rev.get("version") or i)
    raise ValueError("That version of the page isn't available.")


def serialize(fb: PageFeedback, *, for_owner: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "uuid": fb.uuid,
        "revision": fb.revision,
        "version": fb.version,
        "anchor": fb.anchor.model_dump(),
        "message": fb.message,
        "kind": fb.kind,
        "status": fb.status,
        "author_kind": fb.author_kind,
        "author_name": fb.author_name or ("A public viewer" if fb.author_kind == "public" else "A team member"),
        "created_at": fb.created_at.isoformat(),
        "answer": {
            "text": fb.answer.text, "by_name": fb.answer.by_name, "at": fb.answer.at.isoformat(),
            "on_page": fb.answer.on_page,
        } if fb.answer else None,
    }
    if for_owner:
        out["author_email"] = fb.author_email
    return out


async def _notify_owner(doc: dict, fb: PageFeedback) -> None:
    from app.services.notification_service import create_notification

    spot = f"“{fb.anchor.text[:80]}”" if fb.anchor.text else "the page"
    who = fb.author_name or ("A public viewer" if fb.author_kind == "public" else "A team member")
    await create_notification(
        user_id=doc["user_id"],
        kind="page_feedback",
        title=f"{'Flag' if fb.kind == 'flag' else 'Question'} on {doc.get('title') or 'your page'}: {spot}",
        body=f"{who}: {fb.message[:300]}",
        link=f"/pages/{doc['uuid']}?feedback={fb.uuid}",
        item_kind="page_feedback",
        item_id=fb.uuid,
        item_name=doc.get("title") or "Page",
    )


async def submit(
    doc: dict, *, revision: str, anchor: Any, message: str, kind: str,
    author: Optional[User] = None, public_token: Optional[str] = None,
    name: Optional[str] = None, email: Optional[str] = None,
) -> PageFeedback:
    """Record a viewer's question and tell the owner. Raises ValueError for the viewer."""
    text = (message or "").strip()
    if not text:
        raise ValueError("Write your question first.")
    if len(text) > MAX_MESSAGE:
        raise ValueError(f"Keep it under {MAX_MESSAGE} characters.")
    if kind not in ("question", "flag"):
        kind = "question"
    if author is not None and author.user_id == doc["user_id"]:
        raise ValueError("This is your page. Use Request changes to change it.")
    if author is None:
        if not settings_of(doc)["public_questions"]:
            raise PermissionError("The owner isn't taking questions on this page.")
        open_count = await PageFeedback.find(
            {"artifact_uuid": doc["uuid"], "author_kind": "public", "status": "open"},
        ).count()
        if open_count >= MAX_OPEN_PUBLIC:
            raise PermissionError("This page has too many unanswered questions right now. Try again later.")
    fb = PageFeedback(
        artifact_uuid=doc["uuid"], owner_user_id=doc["user_id"], revision=revision,
        version=_version(doc, revision), anchor=clean_anchor(anchor), message=text, kind=kind,
        author_kind="member" if author else "public",
        author_user_id=author.user_id if author else None,
        author_name=(author.name or "") if author else _clean(name, 120),
        author_email=None if author else clean_email(email),
        public_token=public_token,
    )
    await fb.insert()
    try:
        await _notify_owner(doc, fb)
    except Exception:
        logger.exception("Could not notify the owner of page feedback %s", fb.uuid)
    return fb


async def answer(doc: dict, fb: PageFeedback, owner: User, text: str, *, on_page: bool) -> PageFeedback:
    """The owner's answer, delivered to whoever asked."""
    body = (text or "").strip()
    if not body:
        raise ValueError("Write an answer first.")
    if len(body) > MAX_ANSWER:
        raise ValueError(f"Keep the answer under {MAX_ANSWER} characters.")
    fb.answer = FeedbackAnswer(text=body, by_user_id=owner.user_id, by_name=owner.name or "", on_page=on_page)
    fb.status = "answered"
    await fb.save()
    try:
        await _deliver_answer(doc, fb)
    except Exception:
        logger.exception("Could not deliver the answer to page feedback %s", fb.uuid)
    return fb


async def _deliver_answer(doc: dict, fb: PageFeedback) -> None:
    from app.config import Settings
    from app.services.notification_service import create_notification

    title = doc.get("title") or "a page"
    if fb.author_kind == "member" and fb.author_user_id:
        await create_notification(
            user_id=fb.author_user_id,
            kind="page_feedback_answer",
            title=f"Answer on {title}",
            body=f"{fb.answer.by_name or 'The owner'}: {fb.answer.text[:300]}" if fb.answer else None,
            link=f"/pages/{doc['uuid']}?feedback={fb.uuid}",
            item_kind="page_feedback",
            item_id=fb.uuid,
            item_name=title,
        )
    elif fb.author_kind == "public" and fb.author_email and fb.answer:
        from app.services.email_service import page_feedback_answer_email, send_email

        settings = Settings()
        link = f"{settings.frontend_url.rstrip('/')}/a/{fb.public_token}?feedback={fb.uuid}" if fb.public_token else None
        subject, html = page_feedback_answer_email(
            title=title, question=fb.message, spot=fb.anchor.text, answer=fb.answer.text,
            owner=fb.answer.by_name, link=link,
        )
        await send_email(fb.author_email, subject, html, settings, email_type="page_feedback_answer")


async def set_status(fb: PageFeedback, status: str) -> PageFeedback:
    if status not in ("open", "resolved", "answered"):
        raise ValueError("Unknown status.")
    if status == "answered" and not fb.answer:
        raise ValueError("Answer it first.")
    fb.status = status
    await fb.save()
    return fb


async def for_owner(doc: dict) -> list[dict[str, Any]]:
    items = await PageFeedback.find(PageFeedback.artifact_uuid == doc["uuid"]).sort("-created_at").to_list()
    return [serialize(fb, for_owner=True) for fb in items]


async def for_member(doc: dict, user: User, revision: str) -> list[dict[str, Any]]:
    """What a team member sees: their own questions, and answers shown on this version."""
    items = await PageFeedback.find(
        {"artifact_uuid": doc["uuid"], "$or": [
            {"author_user_id": user.user_id},
            {"answer.on_page": True, "revision": revision},
        ]},
    ).sort("-created_at").to_list()
    return [serialize(fb, for_owner=False) for fb in items]


async def for_public(doc: dict, revision: str) -> list[dict[str, Any]]:
    """What anyone with the link sees: answers the owner chose to show on this version."""
    items = await PageFeedback.find(
        {"artifact_uuid": doc["uuid"], "revision": revision, "answer.on_page": True},
    ).sort("-created_at").to_list()
    out = []
    for fb in items:
        row = serialize(fb, for_owner=False)
        # A public viewer's name is theirs to give, not the owner's to show.
        row["author_name"] = "A team member" if fb.author_kind == "member" else "A viewer"
        out.append(row)
    return out


async def update_settings(doc: dict, body: dict) -> dict[str, Any]:
    current = settings_of(doc)
    if "public_questions" in body:
        if not isinstance(body["public_questions"], bool):
            raise ValueError("public_questions must be true or false.")
        current["public_questions"] = body["public_questions"]
    if "contact" in body:
        contact = _clean(body["contact"], MAX_CONTACT + 1)
        if len(contact) > MAX_CONTACT:
            raise ValueError(f"Keep the contact line under {MAX_CONTACT} characters.")
        current["contact"] = contact or None
    await Artifact.get_motor_collection().update_one({"uuid": doc["uuid"]}, {"$set": {"feedback": current}})
    return current


def as_change_request(fb: PageFeedback | dict) -> str:
    """A Request changes prompt built from a viewer's question."""
    item = fb if isinstance(fb, dict) else serialize(fb, for_owner=True)
    spot = item["anchor"]["text"]
    who = item["author_name"]
    lead = f"On “{spot}” (version {item['version']}), " if spot else f"On version {item['version']}, "
    return f"{lead}{who} asked: {item['message']}\n\nUpdate the page to address this."
