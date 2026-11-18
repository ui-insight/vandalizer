"""Award highlights for a principal investigator, from one award document.

Support ticket #1200: an email summary of an FDP subaward was possible only
by typing a prompt in chat, so nobody found it, the facts changed with the
wording, the PI's address wasn't picked up and nothing showed where a fact
came from.

This reads the same fixed set of facts every time with the extraction engine
and source capture, so each fact carries its page and passage. Three rules
keep it honest:

* A fact with no passage located in the document is reported as not found.
  The reader gets "Not found", never a value nobody can check.
* An email address is offered only if it is a well-formed address that
  appears in the document's own text.
* An FDP subaward names two PIs. One is suggested only when it is the only
  one named, or when exactly one is at the reader's institution; otherwise
  the reader chooses.

The email itself is written from these facts in the browser and sent by the
reader from their own mail program. Nothing here sends anything.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.models.document import SmartDocument
from app.models.user import User

logger = logging.getLogger(__name__)

# (key, label, what the extraction should look for). Keys are what the engine
# is asked for, so they read as field names in the prompt. The order is the
# order of the email.
FACT_FIELDS: list[tuple[str, str, str]] = [
    ("Total award amount", "Award amount",
     "The total amount of this award or subaward (amount obligated or total authorized), in dollars, as stated."),
    ("Period of performance start", "Start date",
     "The start date of the period of performance or project period."),
    ("Period of performance end", "End date",
     "The end date of the period of performance or project period."),
    ("Reporting deadlines", "Reporting deadlines",
     "Each report the recipient must submit (technical or progress, financial, final, invention, property) "
     "and when it is due, as the document states it. A short list separated by semicolons."),
    ("Invoicing rules", "Invoicing rules",
     "How and when to invoice: how often, the deadline for the final invoice, where invoices are sent and "
     "any required certification. Brief, in the document's own terms."),
    ("Key terms", "Key terms",
     "Up to five other terms the principal investigator should know, such as prior approvals, carryover, "
     "cost sharing, restrictions, or data and publication terms. Brief, separated by semicolons."),
]
CONTACT_FIELDS: list[tuple[str, str, str]] = [
    ("Administrative contact", "Administrative contact",
     "The administrative contact named in the document: name and email address as stated."),
    ("Financial contact", "Financial contact",
     "The financial or invoicing contact named in the document: name and email address as stated."),
]
# The two parties to a subaward. A prime award that is not a subaward has only
# the recipient, which is asked for under the second role.
PI_ROLES: list[tuple[str, str, str]] = [
    ("pass_through", "Pass-through entity",
     "For a subaward only: the pass-through entity (the organization issuing the subaward)."),
    ("recipient", "Subrecipient",
     "The subrecipient of a subaward. If the document is an award that is not a subaward, the award recipient."),
]
_PI_PARTS: list[tuple[str, str]] = [
    ("institution", "Institution name of {who}"),
    ("name", "Name of the principal investigator at {who}"),
    ("email", "Email address of the principal investigator at {who}, exactly as written in the document. "
              "Leave empty if no email address is written for them."),
]

EXTRACT_TIMEOUT_SECONDS = 180
_EMAIL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9-]+)+")


class HighlightsError(Exception):
    """A failure with a message fit to show the reader, and its HTTP status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _pi_key(role_label: str, part: str) -> str:
    return f"{role_label} principal investigator {part}" if part != "institution" else f"{role_label} institution"


def field_metadata() -> list[dict[str, Any]]:
    meta = [{"key": k, "description": d, "is_optional": True} for k, _l, d in FACT_FIELDS + CONTACT_FIELDS]
    for _role, label, who in PI_ROLES:
        for part, template in _PI_PARTS:
            meta.append({
                "key": _pi_key(label, part), "is_optional": True,
                "description": f"{template.format(who='this party')}. {who}",
            })
    return meta


def extract_keys() -> list[str]:
    return [m["key"] for m in field_metadata()]


# ---------------------------------------------------------------------------
# Turning what the engine returned into facts
# ---------------------------------------------------------------------------

def _fact(entity: dict, key: str, label: str) -> dict[str, Any]:
    """One fact, or the same shape with ``value: None`` when it wasn't found.

    A value whose passage can't be located in the document is not found: it
    can't be linked to a page, and it is exactly what a guess looks like.
    """
    from app.services.extraction_sources import SOURCE_KEY, _is_not_found, support_state_of

    missing = {"key": key, "label": label, "value": None, "page": None,
               "page_approximate": False, "quote": None, "support": None}
    value = entity.get(key)
    if isinstance(value, list):
        value = "; ".join(str(v) for v in value if v is not None and str(v).strip())
    elif isinstance(value, dict):
        return missing
    if value is None or _is_not_found(value) or not str(value).strip():
        return missing
    raw = (entity.get(SOURCE_KEY) or {}).get(key)
    src: dict[str, Any] = raw if isinstance(raw, dict) else {}
    support = support_state_of(src) if src else "unverified"
    if support == "unverified":
        return missing
    return {
        "key": key, "label": label, "value": " ".join(str(value).split()),
        "page": src.get("page") if isinstance(src.get("page"), int) else None,
        "page_approximate": bool(src.get("page_approximate")),
        "quote": src.get("quote"), "support": support,
    }


def _email_in_document(fact: dict[str, Any], raw_text: str) -> str | None:
    """The address in *fact*, only if it is written in the document itself."""
    match = _EMAIL.search(fact.get("value") or "")
    if not match:
        return None
    address = match.group(0).rstrip(".")
    return address if address.lower() in raw_text.lower() else None


def build_result(entity: dict, doc: SmartDocument, reader: dict[str, Any]) -> dict[str, Any]:
    raw_text = doc.raw_text or ""
    pis = []
    for role, label, _who in PI_ROLES:
        institution = _fact(entity, _pi_key(label, "institution"), "Institution")
        name = _fact(entity, _pi_key(label, "name"), "Principal investigator")
        email_fact = _fact(entity, _pi_key(label, "email"), "Email")
        if not name["value"]:
            continue
        pis.append({
            "role": role, "role_label": label, "institution": institution, "name": name,
            "email": _email_in_document(email_fact, raw_text), "email_source": email_fact,
        })
    suggested, reason = suggest_pi(pis, reader)
    return {
        "document": {"uuid": doc.uuid, "title": doc.title},
        "facts": [_fact(entity, k, label) for k, label, _d in FACT_FIELDS],
        "contacts": [_fact(entity, k, label) for k, label, _d in CONTACT_FIELDS],
        "pis": pis,
        "suggested_pi": suggested,
        "suggestion_reason": reason,
        "sender_name": reader.get("name"),
    }


# ---------------------------------------------------------------------------
# Which PI
# ---------------------------------------------------------------------------

_NAME_NOISE = re.compile(r"\b(the|of|at|and|for|inc|llc|board|regents|trustees|system|foundation)\b|[^a-z0-9 ]")


def _plain(name: str | None) -> str:
    return " ".join(_NAME_NOISE.sub(" ", (name or "").lower()).split())


def _domain(address: str | None) -> str | None:
    """The last two labels of an address's domain: mail.colostate.edu → colostate.edu."""
    if not address or "@" not in address:
        return None
    labels = address.rsplit("@", 1)[1].lower().strip(".").split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else None


def _at_readers_institution(pi: dict[str, Any], reader: dict[str, Any]) -> bool:
    domain = _domain(reader.get("email"))
    if domain and _domain(pi.get("email")) == domain:
        return True
    institution = _plain(pi["institution"].get("value"))
    if len(institution) < 5:
        return False
    for name in reader.get("institutions") or []:
        mine = _plain(name)
        if len(mine) >= 5 and (mine in institution or institution in mine):
            return True
    return False


def suggest_pi(pis: list[dict[str, Any]], reader: dict[str, Any]) -> tuple[int | None, str | None]:
    """Index of the PI to address, and why; ``(None, None)`` when the reader must choose."""
    if len(pis) == 1:
        return 0, "only_one"
    matches = [i for i, pi in enumerate(pis) if _at_readers_institution(pi, reader)]
    if len(matches) == 1:
        return matches[0], "your_institution"
    return None, None


async def reader_context(user: User) -> dict[str, Any]:
    """What is known about the person asking: name, email and institution names."""
    institutions: list[str] = []
    if getattr(user, "organization_id", None):
        try:
            from app.services import organization_service

            org_uuid: str | None = user.organization_id
            for _ in range(10):  # the department, then its parents
                org = await organization_service.get_organization(org_uuid) if org_uuid else None
                if org is None:
                    break
                if org.name:
                    institutions.append(org.name)
                org_uuid = org.parent_id
        except Exception:  # noqa: BLE001 — the institution only improves the suggestion
            logger.warning("Could not read the organization for award highlights", exc_info=True)
    return {"name": getattr(user, "name", None), "email": getattr(user, "email", None), "institutions": institutions}


# ---------------------------------------------------------------------------
# Reading the document
# ---------------------------------------------------------------------------

async def build(doc: SmartDocument, user: User) -> dict[str, Any]:
    from app.models.system_config import SystemConfig
    from app.services.config_service import get_user_model_name
    from app.services.extraction_engine import ExtractionEngine, ExtractionError
    from app.services.metering import metered_async
    from app.services.trial_budget import TrialBudgetExceededError

    raw_text = doc.raw_text or ""
    if not raw_text.strip():
        if getattr(doc, "processing", False):
            raise HighlightsError(409, "This document is still being read. Try again when it has finished.")
        raise HighlightsError(422, "This document has no readable text, so there is nothing to pull highlights from.")

    model = await get_user_model_name(user.user_id)
    engine = ExtractionEngine(system_config_doc=(await SystemConfig.get_config()).model_dump())

    def run() -> list:
        return engine.extract(
            extract_keys(), model=model, doc_texts=[raw_text], field_metadata=field_metadata(),
            capture_sources=True,
            doc_metadata=[{"uuid": doc.uuid, "title": doc.title, "text_markers": doc.text_markers or []}],
        )

    try:
        async with metered_async(
            "award_highlights", user_id=user.user_id,
            team_id=str(user.current_team) if getattr(user, "current_team", None) else None,
        ):
            entities = await asyncio.wait_for(asyncio.to_thread(run), timeout=EXTRACT_TIMEOUT_SECONDS)
    except TrialBudgetExceededError:
        raise HighlightsError(402, "Your account's token budget is used up, so the document couldn't be read.")
    except asyncio.TimeoutError:
        raise HighlightsError(504, "Reading the document took too long. Try again.")
    except ExtractionError as exc:
        from app.services.extraction_errors import describe_extraction_failure

        logger.warning("Award highlights failed for document %s: %s", doc.uuid, exc)
        status, message = describe_extraction_failure(exc)
        raise HighlightsError(status, message)

    entity = next((e for e in (entities if isinstance(entities, list) else [entities]) if isinstance(e, dict)), {})
    return build_result(entity, doc, await reader_context(user))
