"""Anonymous deployment telemetry — the once-daily heartbeat.

This is the privacy-first "how many deployments exist and roughly how heavily
are they used" signal for self-hosted Vandalizer. It is OPT-IN: nothing leaves
the box unless an admin sets both ``telemetry_enabled=True`` and a
``telemetry_endpoint`` (see ``app.config.Settings``).

What the heartbeat sends:
  - a stable random instance UUID (generated here, persisted in Mongo; it is not
    derived from anything identifying and cannot be reversed to an institution)
  - the running version and a coarse environment ("production" / "other")
  - usage as COARSE BUCKETS only ("11-50", never an exact count)

What it never sends: document content, filenames, titles, user identities,
emails, API keys, team names, or any free text. The payload is a fixed,
auditable shape — see ``build_heartbeat_payload`` — and every send is logged
locally when ``telemetry_log_payload`` is on, so an admin can read exactly what
was transmitted.

Sync (pymongo + httpx.Client) because it runs from a Celery beat task.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx
from pymongo.database import Database

from app.config import Settings
from app.services.version_service import get_current_version

logger = logging.getLogger(__name__)

# Dedicated single-doc collection. Kept separate from the SystemConfig singleton
# so telemetry state never rides along with operational config edits.
_STATE_COLLECTION = "telemetry_state"
_STATE_ID = "instance"

# Window over which a user counts as "active" for the active-user bucket.
ACTIVE_WINDOW_DAYS = 30

_POST_TIMEOUT_SECONDS = 5.0


def get_or_create_instance_id(db: Database[dict]) -> str:
    """Return this deployment's stable anonymous instance UUID, minting one on
    first call. The value is random (uuid4) — it identifies the *install*, not
    the institution, and is the only stable token in the heartbeat."""
    doc = db[_STATE_COLLECTION].find_one({"_id": _STATE_ID})
    if doc and doc.get("instance_id"):
        return str(doc["instance_id"])

    instance_id = str(uuid4())
    # upsert so two workers racing on first boot converge on one id (the unique
    # _id makes the second insert a no-op update rather than a duplicate row).
    db[_STATE_COLLECTION].update_one(
        {"_id": _STATE_ID},
        {"$setOnInsert": {"instance_id": instance_id, "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    # Re-read in case a racing worker won the insert with a different id.
    doc = db[_STATE_COLLECTION].find_one({"_id": _STATE_ID})
    return str((doc or {}).get("instance_id", instance_id))


def _bucket(n: int) -> str:
    """Collapse an exact count into a coarse, non-identifying range.

    Buckets (not raw numbers) are the whole point: "this deployment has between
    11 and 50 users" is useful for fleet sizing while revealing almost nothing
    about a specific institution.
    """
    if n <= 0:
        return "0"
    if n == 1:
        return "1"
    if n <= 10:
        return "2-10"
    if n <= 50:
        return "11-50"
    if n <= 200:
        return "51-200"
    if n <= 1000:
        return "201-1000"
    return "1000+"


def _coarse_environment(settings: Settings) -> str:
    """Only production vs. everything-else — never the free-text deployment label."""
    return "production" if settings.is_production else "other"


def resolve_runtime_config(db: Database[dict], settings: Settings) -> dict[str, Any]:
    """Resolve the effective telemetry decision from the DB + env defaults.

    Precedence: once an admin makes an explicit in-app decision
    (SystemConfig.telemetry_config.decided), that DB value is authoritative for
    enablement and identity. Until then, the env defaults (set by setup.sh)
    govern. Read with sync pymongo so the Celery heartbeat task stays sync.
    """
    doc = db["system_config"].find_one() or {}
    tele = doc.get("telemetry_config") or {}
    decided = bool(tele.get("decided"))

    enabled = bool(tele.get("enabled")) if decided else settings.telemetry_enabled
    organization = (tele.get("organization") if decided else "") or settings.telemetry_organization
    contact_email = (tele.get("contact_email") if decided else "") or settings.telemetry_contact_email

    return {
        "enabled": enabled,
        "organization": (organization or "").strip(),
        "contact_email": (contact_email or "").strip(),
        "endpoint": settings.telemetry_endpoint,
    }


def build_heartbeat_payload(
    db: Database[dict],
    settings: Settings,
    *,
    organization: str | None = None,
    contact_email: str | None = None,
) -> dict[str, Any]:
    """Assemble the exact, fixed-shape JSON that the heartbeat will POST.

    Pure assembly — no network. Kept separate so it can be unit-tested and so
    the local audit log and the wire payload are guaranteed identical. The
    identity args override the env defaults when provided (the caller resolves
    them via resolve_runtime_config); None falls back to settings.
    """
    if organization is None:
        organization = settings.telemetry_organization
    if contact_email is None:
        contact_email = settings.telemetry_contact_email
    now = datetime.now(timezone.utc)
    active_since = now - timedelta(days=ACTIVE_WINDOW_DAYS)

    user_count = db["user"].count_documents({})
    active_user_count = db["user"].count_documents({"last_login_at": {"$gte": active_since}})
    team_count = db["team"].count_documents({})
    document_count = db["smart_document"].count_documents({})
    workflow_count = db["workflow"].count_documents({})

    payload: dict[str, Any] = {
        "schema": 1,
        "instance_id": get_or_create_instance_id(db),
        "version": get_current_version(),
        "environment": _coarse_environment(settings),
        "sent_at": now.isoformat(),
        "metrics": {
            "users": _bucket(user_count),
            "active_users_30d": _bucket(active_user_count),
            "teams": _bucket(team_count),
            "documents": _bucket(document_count),
            "workflows": _bucket(workflow_count),
        },
    }

    # Voluntary identity tier — added ONLY when an organization is set. When
    # blank, the key is omitted entirely so the payload is honestly anonymous
    # (not an empty-string "identity"). contact_email rides along only if an org
    # was also given.
    organization = organization.strip()
    if organization:
        identity: dict[str, str] = {"organization": organization}
        contact_email = contact_email.strip()
        if contact_email:
            identity["contact_email"] = contact_email
        payload["identity"] = identity

    return payload


def send_heartbeat(db: Database[dict], settings: Settings) -> dict[str, Any]:
    """Build, locally log, and POST one heartbeat.

    Returns a small result dict describing what happened (for the Celery task's
    return value / logs). Never raises on a delivery failure — telemetry is
    best-effort and must never disrupt the deployment it reports on.
    """
    resolved = resolve_runtime_config(db, settings)
    if not resolved["enabled"]:
        return {"status": "disabled"}

    if not resolved["endpoint"]:
        # Enabled but no destination (endpoint blanked to hard-disable sending):
        # do nothing rather than guess a domain.
        logger.warning(
            "telemetry is enabled but telemetry_endpoint is empty — no heartbeat "
            "sent. Set telemetry_endpoint to opt in fully."
        )
        return {"status": "no_endpoint"}

    payload = build_heartbeat_payload(
        db,
        settings,
        organization=resolved["organization"],
        contact_email=resolved["contact_email"],
    )

    if settings.telemetry_log_payload:
        # The audit guarantee: an admin can grep the worker log and see the
        # complete, literal payload that was transmitted.
        logger.info("Telemetry heartbeat payload: %s", payload)

    try:
        with httpx.Client(timeout=_POST_TIMEOUT_SECONDS) as client:
            resp = client.post(resolved["endpoint"], json=payload)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.info("Telemetry heartbeat delivery failed: %s", exc)
        return {"status": "delivery_failed", "error": str(exc)}

    return {"status": "sent", "instance_id": payload["instance_id"]}
