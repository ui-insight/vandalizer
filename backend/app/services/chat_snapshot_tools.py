"""Chat's read of a project's award snapshot (app.services.award_snapshot).

Support ticket: "Summarize this project" answered from the award document
alone — nothing about the project's RA inbox deadlines, the overdue one, its
status or its saved pages. This tool hands chat the same snapshot the project
panel shows, each part labelled with where it came from.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import RunContext

from app.services.chat_deps import AgenticChatDeps

_CONFIRMED = {
    "supported": "confirmed on the page",
    "unassessed": "passage found; value not checked",
    "quote_unsupported": "NOT confirmed by the passage",
    "unverified": "source passage not found",
}


def _fact(f: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": f["label"],
        "value": f["value"],
        "source": f"{f['document_title']}, p. {f['page']}" if f.get("document_title") and f.get("page")
        else f.get("document_title"),
        "confirmed": _CONFIRMED.get(f.get("support") or "unverified", "source passage not found"),
    }


def _deadline(d: dict[str, Any]) -> dict[str, Any]:
    src = (d.get("sources") or [{}])[0]
    return {
        "title": d["title"],
        "due": (d.get("due_at") or "")[:10] or None,
        **({"due_text": d["due_text"]} if d.get("due_text") else {}),
        **({"days_until": d["days_until"]} if "days_until" in d else {}),
        "source": f"{src.get('document_title')}, p. {src.get('page')}" if src.get("page") else src.get("document_title"),
    }


async def get_award_snapshot(
    context: RunContext[AgenticChatDeps],
    project_uuid: Optional[str] = None,
) -> dict:
    """Where a project's award stands: key facts, budget by year, RA inbox deadlines, status and activity.

    Use this for "Summarize this project", "Where does this award stand?", "What's
    overdue on this award?" or any overview of a project, before reading its
    documents. Answer from it:

    - key facts and budget: read from the project's documents; cite each fact's
      source page as given, and say so when a fact is not confirmed;
    - deadlines: live from the project's RA inbox (upcoming, overdue with days
      past, done) — say they are from the RA inbox;
    - status, last run and saved pages: the project's own records.

    When facts is empty because the snapshot was never built, say so and suggest
    "Build snapshot" in the project's Award snapshot panel; you can still give the
    deadlines and status, and read the documents for facts if the user wants them.

    Args:
        context: The call context.
        project_uuid: The project; defaults to the one open in chat.
    """
    from app.services import award_snapshot, project_service
    from app.services.chat_tools import _err, _resolve_active_project

    if project_uuid:
        project = await project_service.get_authorized_project(project_uuid, context.deps.user)
    else:
        project = await _resolve_active_project(context)
    if not project:
        return _err(
            "No project is open.",
            hint="Open the project in chat, or pass its project_uuid (list it with list_projects).",
        )
    v = await award_snapshot.view(project, context.deps.user)
    # The deadlines below were read from the RA inbox this turn.
    context.deps.inbox_read = True
    dl = v["deadlines"]
    notes = []
    if v["status"] == "not_built":
        notes.append("The snapshot's facts have not been built yet (Build snapshot in the project's Award snapshot panel).")
    elif v["status"] == "building":
        notes.append("The facts are being re-read from the documents right now; the ones below may be about to change.")
    elif v["status"] == "error":
        notes.append(f"The last attempt to read the facts failed: {v.get('error')}")
    if v.get("out_of_date"):
        notes.append("The project's documents changed after these facts were read.")
    return {
        "project": v["project"]["title"],
        "status": v["project"]["state"],
        "facts_read_from_documents": [_fact(f) for f in v["facts"]],
        "budget_by_year": [_fact(f) for f in v["budget_years"]],
        # Not in the award documents read. Say so; don't fill them from a
        # summary or another file (support ticket).
        **({"not_stated_in_documents": v["not_found"]} if v.get("not_found") else {}),
        "facts_built_at": v.get("built_at"),
        "ra_inbox_deadlines": {
            "overdue": [_deadline(d) for d in dl["overdue"]],
            "upcoming": [_deadline(d) for d in dl["upcoming"]],
            "done": [_deadline(d) for d in dl["done"]],
            "still_needed_or_limits": [d["title"] for d in dl["needed"]],
        },
        "last_run": v.get("last_run"),
        "saved_pages": [p["title"] for p in v.get("pages", [])],
        **({"notes": notes} if notes else {}),
    }
