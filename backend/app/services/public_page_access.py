"""Who may open a published Page link, until when, and who has.

Support ticket: a published link gave anyone who had it access forever, with
no way to limit it to signed-in people or to see whether it was opened.
Budget and award Pages carry sensitive figures and are shared for a review
period, so each public link (the main link and every separate version link)
now has:

* ``expires_at``: after it, the link answers "This link has expired" until
  the owner extends or republishes it. A reminder rings the owner's bell
  before it lapses.
* ``audience``: ``anyone`` with the link, or ``signed_in``: a verified
  account on this Vandalizer deployment, optionally only the listed
  ``emails``.
* a view record: how many times it was opened and when last, and for
  signed-in access, by whom (``page_link_viewers``, one row per person).

Main-link settings live on the Page (``public_*`` fields); a version link's on
its ``publications`` entry. Both are owner-only in the Page's metadata.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from fastapi import HTTPException
from pymongo.database import Database

AUDIENCES = ("anyone", "signed_in")
MAX_EMAILS = 50
MAX_LIFETIME = datetime.timedelta(days=366)
REMIND_BEFORE = datetime.timedelta(days=3)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

EXPIRED = "This link has expired. Ask the page owner for a new link."
NOT_INVITED = "This page is shared with specific people, and your account isn't one of them."
UNVERIFIED = "Verify your account's email address to view this page."


def _utc(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def normalize(expires_at: datetime.datetime | None, audience: str | None, emails: list[str] | None) -> dict:
    """Validated settings for one link."""
    audience = audience or "anyone"
    if audience not in AUDIENCES:
        raise HTTPException(422, "Choose who can open the link: anyone with it, or signed-in accounts.")
    expires = _utc(expires_at)
    if expires is not None:
        if expires <= now():
            raise HTTPException(422, "Choose an expiry date in the future.")
        if expires - now() > MAX_LIFETIME:
            raise HTTPException(422, "A link can be set to expire at most a year from now. Choose Never for no expiry.")
    cleaned = sorted({e.strip().lower() for e in (emails or []) if e and e.strip()})
    if cleaned and audience != "signed_in":
        raise HTTPException(422, "Specific people can only be set for a link that requires signing in.")
    if len(cleaned) > MAX_EMAILS:
        raise HTTPException(422, f"List at most {MAX_EMAILS} email addresses.")
    bad = [e for e in cleaned if not _EMAIL.match(e)]
    if bad:
        raise HTTPException(422, f"Not an email address: {bad[0]}")
    return {"expires_at": expires, "audience": audience, "emails": cleaned}


def main_settings(doc: dict) -> dict:
    return {"expires_at": _utc(doc.get("public_expires_at")), "audience": doc.get("public_audience") or "anyone",
            "emails": list(doc.get("public_emails") or [])}


def link_for_token(doc: dict, token: str) -> tuple[str, dict, str] | None:
    """(revision uuid, settings, "main" | "version") for a public token."""
    if doc.get("public_token") == token and doc.get("published_revision"):
        return doc["published_revision"], main_settings(doc), "main"
    for link in doc.get("publications") or []:
        if link.get("token") == token:
            return link["revision"], {"expires_at": _utc(link.get("expires_at")), "audience": link.get("audience") or "anyone",
                                      "emails": list(link.get("emails") or [])}, "version"
    return None


def is_expired(settings: dict, at: datetime.datetime | None = None) -> bool:
    expires = settings.get("expires_at")
    return expires is not None and expires <= (at or now())


def check(settings: dict, user: Any | None) -> None:
    """Raise unless *user* (None when signed out) may open a link with *settings*."""
    if is_expired(settings):
        raise HTTPException(410, EXPIRED)
    if settings.get("audience") != "signed_in":
        return
    if user is None:
        # The client refreshes an expired session on exactly this detail.
        raise HTTPException(401, "Not authenticated")
    emails = settings.get("emails") or []
    if not emails:
        # Any signed-in account. Not gated on a verified email: local password
        # accounts are unverified unless they used reset or magic login, so on
        # a deployment without SSO most team members would be refused.
        return
    # Named people: the address is the identity, and local sign-up lets anyone
    # register an address they don't own, so only a verified one counts.
    if not getattr(user, "email_verified", False):
        raise HTTPException(403, UNVERIFIED)
    if (getattr(user, "email", "") or "").strip().lower() not in emails:
        raise HTTPException(403, NOT_INVITED)


def record_view(db: Database[dict], doc: dict, token: str, kind: str, user: Any | None) -> None:
    """Count an opening; for a signed-in viewer, remember who. Never raises.

    The owner's own openings (checking the link works) are not views."""
    if user is not None and getattr(user, "user_id", None) and user.user_id == doc.get("user_id"):
        return
    at = now()
    try:
        if kind == "main":
            db.html_artifacts.update_one({"uuid": doc["uuid"], "public_token": token},
                                         {"$inc": {"public_views.count": 1}, "$set": {"public_views.last_at": at}})
        else:
            db.html_artifacts.update_one({"uuid": doc["uuid"]},
                                         {"$inc": {"publications.$[p].views.count": 1}, "$set": {"publications.$[p].views.last_at": at}},
                                         array_filters=[{"p.token": token}])
        if user is not None and getattr(user, "user_id", None):
            db.page_link_viewers.update_one(
                {"artifact_uuid": doc["uuid"], "token": token, "user_id": user.user_id},
                {"$inc": {"views": 1}, "$set": {"last_at": at, "name": getattr(user, "name", None) or "",
                                                "email": getattr(user, "email", None) or ""},
                 "$setOnInsert": {"first_at": at}},
                upsert=True,
            )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Could not record a view of page %s", doc.get("uuid"))


def _views(raw: dict | None) -> dict:
    raw = raw or {}
    last = _utc(raw.get("last_at"))
    return {"count": int(raw.get("count") or 0), "last_at": last.isoformat() if last else None}


def _viewers(db: Database[dict], doc: dict, token: str, limit: int = 20) -> list[dict]:
    rows = db.page_link_viewers.find({"artifact_uuid": doc["uuid"], "token": token}).sort("last_at", -1).limit(limit)
    out = []
    for row in rows:
        last = _utc(row.get("last_at"))
        out.append({"name": row.get("name") or "", "email": row.get("email") or "", "count": row.get("views", 0),
                    "last_at": last.isoformat() if last else None})
    return out


def describe(db: Database[dict], doc: dict) -> dict:
    """Owner-only: settings and views for the main link and each version link."""
    def entry(token: str | None, settings: dict, views: dict | None) -> dict | None:
        if not token:
            return None
        expires = settings.get("expires_at")
        return {"expires_at": expires.isoformat() if expires else None, "expired": is_expired(settings),
                "audience": settings["audience"], "emails": settings["emails"],
                "views": _views(views), "viewers": _viewers(db, doc, token)}
    main = entry(doc.get("public_token") if doc.get("published_revision") else None, main_settings(doc), doc.get("public_views"))
    versions = {}
    for link in doc.get("publications") or []:
        found = link_for_token(doc, link["token"])
        if found:
            versions[link["revision"]] = entry(link["token"], found[1], link.get("views"))
    return {"main": main, "versions": versions}


def apply_main(db: Database[dict], doc: dict, settings: dict) -> None:
    db.html_artifacts.update_one({"uuid": doc["uuid"], "user_id": doc["user_id"], "deleted_at": None}, {"$set": {
        "public_expires_at": settings["expires_at"], "public_audience": settings["audience"],
        "public_emails": settings["emails"], "public_reminded_at": None,
    }})


def apply_version(db: Database[dict], doc: dict, revision: str, settings: dict) -> None:
    db.html_artifacts.update_one({"uuid": doc["uuid"], "user_id": doc["user_id"], "deleted_at": None}, {"$set": {
        "publications.$[p].expires_at": settings["expires_at"], "publications.$[p].audience": settings["audience"],
        "publications.$[p].emails": settings["emails"], "publications.$[p].reminded_at": None,
    }}, array_filters=[{"p.revision": revision}])


def clear_main(db: Database[dict], doc: dict) -> None:
    db.html_artifacts.update_one({"uuid": doc["uuid"]}, {"$unset": {
        "public_expires_at": "", "public_audience": "", "public_emails": "", "public_views": "", "public_reminded_at": "",
    }})


def live_links(db: Database[dict], user_id: str) -> list[dict]:
    """Every public link the user's Pages have, soonest to expire first."""
    docs = db.html_artifacts.find(
        {"user_id": user_id, "deleted_at": None, "$or": [{"public_token": {"$ne": None}}, {"publications.0": {"$exists": True}}]},
        {"revisions.html": 0},
    )
    links = []
    for doc in docs:
        numbers = {r["uuid"]: r.get("version", i) for i, r in enumerate(doc.get("revisions") or [], 1)}
        tokens = ([(doc["public_token"], "main")] if doc.get("public_token") and doc.get("published_revision") else []) \
            + [(link["token"], "version") for link in doc.get("publications") or []]
        for token, kind in tokens:
            found = link_for_token(doc, token)
            if not found:
                continue
            revision, settings, _ = found
            raw_views = doc.get("public_views") if kind == "main" else next(
                (link.get("views") for link in doc.get("publications") or [] if link.get("token") == token), None)
            expires = settings["expires_at"]
            links.append({"artifact_uuid": doc["uuid"], "title": doc.get("title") or "Page", "kind": kind,
                          "version": numbers.get(revision), "url": f"/a/{token}",
                          "expires_at": expires.isoformat() if expires else None, "expired": is_expired(settings),
                          "audience": settings["audience"], "restricted_to": len(settings["emails"]),
                          "views": _views(raw_views)})
    far = datetime.datetime.max.replace(tzinfo=datetime.timezone.utc).isoformat()
    return sorted(links, key=lambda link: (not link["expired"], link["expires_at"] or far, link["title"]))


def remind_expiring(db: Database[dict], at: datetime.datetime | None = None) -> int:
    """Bell the owner once per link that expires within REMIND_BEFORE."""
    from app.services.notification_service import create_notification_sync

    at = at or now()
    soon = at + REMIND_BEFORE
    sent = 0
    for doc in db.html_artifacts.find({"deleted_at": None, "$or": [
        {"public_expires_at": {"$gt": at, "$lte": soon}, "public_reminded_at": None},
        {"publications": {"$elemMatch": {"expires_at": {"$gt": at, "$lte": soon}, "reminded_at": None}}},
    ]}, {"revisions.html": 0}):
        title = doc.get("title") or "Your page"
        due: list[tuple[str, datetime.datetime, dict[str, Any]]] = []
        expires = _utc(doc.get("public_expires_at"))
        if doc.get("public_token") and expires and at < expires <= soon and not doc.get("public_reminded_at"):
            due.append(("main", expires, {"public_reminded_at": at}))
        for link in doc.get("publications") or []:
            link_expires = _utc(link.get("expires_at"))
            if link_expires and at < link_expires <= soon and not link.get("reminded_at"):
                due.append((link["revision"], link_expires, {}))
        for which, expires_at, _ in due:
            # Claim before ringing, so two workers never send the same reminder.
            if which == "main":
                result = db.html_artifacts.update_one({"uuid": doc["uuid"], "public_reminded_at": None},
                                                      {"$set": {"public_reminded_at": at}})
            else:
                result = db.html_artifacts.update_one({"uuid": doc["uuid"]}, {"$set": {"publications.$[p].reminded_at": at}},
                                                      array_filters=[{"p.revision": which, "p.reminded_at": None}])
            if result.modified_count != 1:
                continue  # another worker reminded it
            when = f"{expires_at:%b} {expires_at.day}, {expires_at.year}"
            create_notification_sync(
                db, user_id=doc["user_id"], kind="page_link_expiring",
                title=f"Public link for “{title}” expires {when}",
                body="Extend it from Share if people still need it, or let it lapse.",
                link=f"/pages/{doc['uuid']}#share", item_kind="page", item_id=doc["uuid"], item_name=title,
            )
            sent += 1
    return sent
