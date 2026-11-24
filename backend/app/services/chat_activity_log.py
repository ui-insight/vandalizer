"""A chat's approval activity: what the user approved, and what it did.

Support ticket (NIFA subaward setup test): in a long chat the user couldn't
tell what they had approved, how many times, or whether it ran. Each card
showed only its own result, spread across the conversation; we had to check
Files and Projects by hand to learn whether "Move files" and "Add to inbox"
had run.

``build_activity_log`` reads the stored transcript and returns one timeline:

* one entry per decision: a card's button (``approval_for``/``decline_for``
  on the user turn) or a typed reply that carried out a waiting action,
  with what the next reply's confirmed call returned;
* one entry per card still waiting (its preview's call id is still armed);
* ``approvals``/``runs`` per action, so "Approved twice, ran once" shows.

The same entries feed Admin → Audit (``audit_turn``), so the log the user
sees and the audit record can't disagree.

Pure apart from ``load_activity_log``/``audit_turn``: the builder takes
plain message dicts, so its decisions are easy to pin in tests.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# What happened, as the timeline shows it.
DONE = "done"          # ✅ it ran
PARTIAL = "partial"    # ⚠️ part of it ran
NOT_RUN = "not_run"    # ❌ nothing ran
CANCELLED = "cancelled"  # the user's Cancel: nothing ran, by choice
WAITING = "waiting"    # card still waiting for the user
NO_RESULT = "no_result"  # approved; the reply hasn't finished yet

_SUMMARY_LIMIT = 240
_DETAIL_LIMIT = 300

_PAGE_TOOLS = {"create_html_artifact", "revise_html_artifact"}


def _clip(text: Any, limit: int) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime.datetime):
        # Messages are stamped with naive server-local time; say which.
        if value.tzinfo is None:
            value = value.astimezone()
        return str(value.astimezone(datetime.timezone.utc).isoformat())
    if isinstance(value, str):
        return value
    return None


def _unique(items: Iterable[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for item in items:
        cid = item.get("tool_call_id")
        if isinstance(cid, str) and cid:
            seen[cid] = item
    return list(seen.values())


def _calls(message: dict) -> list[dict]:
    segs = [s.get("call") for s in message.get("segments") or [] if isinstance(s, dict) and s.get("kind") == "tool_call"]
    return _unique([c for c in [*(message.get("tool_calls") or []), *segs] if isinstance(c, dict)])


def _results(message: dict) -> list[dict]:
    segs = [s.get("result") for s in message.get("segments") or [] if isinstance(s, dict) and s.get("kind") == "tool_result"]
    return _unique([r for r in [*(message.get("tool_results") or []), *segs] if isinstance(r, dict)])


def _canonical(args: Any) -> str:
    rest = {k: v for k, v in _as_dict(args).items() if k != "confirmed"}
    return json.dumps(rest, sort_keys=True, default=str)


def _is_preview(content: dict) -> bool:
    return content.get("needs_confirmation") is True


def _not_carried_out(content: dict) -> bool:
    """A confirmed call the gate turned back: shown again as a card, or refused."""
    return bool(content.get("needs_confirmation") or content.get("still_waiting"))


def _outcome_of(content: Any) -> tuple[str, str]:
    """``(outcome, detail)`` for a confirmed call's result."""
    if not isinstance(content, dict):
        text = _clip(content, _DETAIL_LIMIT)
        return DONE, text
    status = str(content.get("status") or "").lower()
    error = content.get("error")
    message = content.get("message") or content.get("summary") or ""
    if error or status in {"failed", "error"}:
        return NOT_RUN, _clip(error or message or "It failed.", _DETAIL_LIMIT)
    if status in {"canceled", "cancelled"}:
        return NOT_RUN, _clip(message or "It was canceled.", _DETAIL_LIMIT)
    if status == "partial":
        return PARTIAL, _clip(message or "Only part of it was done.", _DETAIL_LIMIT)
    return DONE, _clip(message, _DETAIL_LIMIT)


class _Preview:
    __slots__ = ("call_id", "tool", "label", "summary", "args", "key", "preview_id", "time", "index")

    def __init__(self, result: dict, call: Optional[dict], time: Optional[str], index: int) -> None:
        content = _as_dict(result.get("content"))
        self.call_id: str = result["tool_call_id"]
        self.tool: str = str(result.get("tool_name") or (call or {}).get("tool_name") or "")
        from app.services.chat_tools import approve_button_label

        self.label: str = str(content.get("approval_label") or approve_button_label(self.tool))
        self.summary: str = _clip(content.get("preview") or content.get("summary") or "", _SUMMARY_LIMIT)
        self.args: str = _canonical((call or {}).get("args"))
        # Same action previewed again later carries the same key: repeats are
        # counted per action, not per card.
        self.key: str = str(content.get("approval_key") or self.call_id)
        pid = content.get("preview_id")
        self.preview_id: Optional[str] = pid if isinstance(pid, str) else None
        self.time = time
        self.index = index

    def matches(self, call: dict, result: dict) -> bool:
        """Whether a confirmed *call* is this exact action (for typed approvals)."""
        if call.get("tool_name") != self.tool:
            return False
        content = _as_dict(result.get("content"))
        if content.get("approval_key") and content.get("approval_key") == self.key:
            return True
        if self.tool in _PAGE_TOOLS:
            return bool(self.preview_id) and _as_dict(call.get("args")).get("preview_id") == self.preview_id
        return _canonical(call.get("args")) == self.args


def _reply_window(messages: list[dict], user_index: int) -> list[dict]:
    """The assistant turns answering the user turn at *user_index*."""
    out = []
    for m in messages[user_index + 1:]:
        if m.get("role") == "user":
            break
        if m.get("role") == "assistant":
            out.append(m)
    return out


def _attempts(replies: list[dict], preview: _Preview, *, by_button: bool) -> list[tuple[dict, dict]]:
    """Confirmed calls of *preview*'s action in *replies*, with their results.

    After a card's button the gate lets only that card's action run, so any
    confirmed call of its tool is this card's attempt. A typed reply names no
    card: only an exact match counts.
    """
    out = []
    for reply in replies:
        results = {r["tool_call_id"]: r for r in _results(reply)}
        for call in _calls(reply):
            if call.get("tool_name") != preview.tool or _as_dict(call.get("args")).get("confirmed") is not True:
                continue
            result = results.get(call.get("tool_call_id"))
            if result is None:
                continue
            if by_button or preview.matches(call, result):
                out.append((call, result))
    return out


def _decide_outcome(replies: list[dict], attempts: list[tuple[dict, dict]], *, last_turn: bool) -> tuple[str, str]:
    ran = [r for _, r in attempts if not _not_carried_out(_as_dict(r.get("content")))]
    if ran:
        return _outcome_of(ran[-1].get("content"))
    if not replies:
        if last_turn:
            return NO_RESULT, "The Assistant hasn't finished replying yet."
        return NOT_RUN, "The Assistant couldn't respond, so nothing was done."
    if attempts:
        return NOT_RUN, "It was no longer waiting for approval, so nothing ran."
    if any(r.get("interruption") for r in replies):
        return NOT_RUN, "The reply stopped before this ran."
    return NOT_RUN, "The Assistant replied without carrying it out."


def build_activity_log(messages: list[dict], pending_call_ids: Iterable[str] = ()) -> dict:
    """The approval timeline for a transcript.

    *messages* are ``ChatMessage.to_dict()`` dicts in order, each with a
    ``created_at``. *pending_call_ids* are the cards the server still has
    armed (``approval_scope.pending_call_ids``).
    """
    pending = {c for c in pending_call_ids if isinstance(c, str)}
    previews: list[_Preview] = []
    for i, m in enumerate(messages):
        if m.get("role") != "assistant":
            continue
        calls = {c["tool_call_id"]: c for c in _calls(m)}
        for r in _results(m):
            content = _as_dict(r.get("content"))
            # A second copy of the same action in one reply shows no card.
            if _is_preview(content) and not content.get("already_waiting"):
                previews.append(_Preview(r, calls.get(r["tool_call_id"]), _iso(m.get("created_at")), i))

    last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
    entries: list[dict] = []
    for p in previews:
        decided = False
        for j in range(p.index + 1, len(messages)):
            m = messages[j]
            if m.get("role") != "user":
                continue
            replies = _reply_window(messages, j)
            base = {
                "call_id": p.call_id, "action_key": p.key, "tool": p.tool, "action": p.label,
                "summary": p.summary, "time": _iso(m.get("created_at")), "message_index": j,
            }
            if m.get("decline_for") == p.call_id:
                decided = True
                entries.append({**base, "decision": "cancelled", "via": "button",
                                "outcome": CANCELLED, "detail": "You cancelled it. Nothing ran."})
            elif m.get("approval_for") == p.call_id:
                decided = True
                attempts = _attempts(replies, p, by_button=True)
                outcome, detail = _decide_outcome(replies, attempts, last_turn=j == last_user)
                entries.append({**base, "decision": "approved", "via": "button", "outcome": outcome, "detail": detail})
            elif not m.get("approval_for") and not m.get("decline_for"):
                # A typed "yes": recorded only when it carried this action out.
                attempts = _attempts(replies, p, by_button=False)
                ran = [r for _, r in attempts if not _not_carried_out(_as_dict(r.get("content")))]
                if ran:
                    decided = True
                    outcome, detail = _outcome_of(ran[-1].get("content"))
                    entries.append({**base, "decision": "approved", "via": "typed",
                                    "said": _clip(m.get("content"), 120), "outcome": outcome, "detail": detail})
        if p.call_id in pending and not decided:
            entries.append({
                "call_id": p.call_id, "action_key": p.key, "tool": p.tool, "action": p.label,
                "summary": p.summary, "time": p.time, "message_index": p.index,
                "decision": "waiting", "via": None, "outcome": WAITING, "preview_id": p.preview_id,
                "detail": "Waiting for you to approve or cancel it.",
            })

    # Repeats: approvals and runs per action, for "Approved twice, ran once".
    counts: dict[str, list[int]] = {}
    for e in entries:
        if e["decision"] == "approved":
            c = counts.setdefault(e["action_key"], [0, 0])
            c[0] += 1
            c[1] += e["outcome"] in (DONE, PARTIAL)
    for e in entries:
        approvals, runs = counts.get(e["action_key"], (0, 0))
        e["approvals"] = approvals
        e["runs"] = runs
        e["repeated"] = approvals > 1

    entries.sort(key=lambda e: (e["message_index"], e["time"] or ""))
    for n, e in enumerate(entries):
        e["id"] = f"{e['call_id']}:{e['message_index']}:{n}"

    return {
        "entries": entries,
        "waiting": sum(1 for e in entries if e["outcome"] == WAITING),
        "repeated": sorted({e["action"] for e in entries if e["repeated"]}),
        "latest_turn": last_user,
    }


async def load_activity_log(conversation: Any) -> dict:
    """``build_activity_log`` for a stored conversation."""
    from app.models.chat import ChatMessage
    from app.services.approval_scope import pending_call_ids

    docs = await ChatMessage.find({"_id": {"$in": conversation.messages or []}}).to_list()
    order = {mid: i for i, mid in enumerate(conversation.messages or [])}
    docs.sort(key=lambda d: order.get(d.id, 0))
    messages = [{**d.to_dict(), "created_at": d.created_at} for d in docs]
    return build_activity_log(messages, pending_call_ids(conversation.pending_confirmations))


async def audit_turn(conversation: Any, user: Any) -> int:
    """Record the latest turn's approvals and cancellations in Admin → Audit.

    Returns how many entries were written. Never raises.
    """
    try:
        from app.services import audit_service

        log = await load_activity_log(conversation)
        # Only the newest user turn: earlier ones were audited when they ran.
        mine = [
            e for e in log["entries"]
            if e["message_index"] == log["latest_turn"] and e["decision"] != "waiting"
        ]
        for e in mine:
            await audit_service.log_event(
                action="chat.action_approved" if e["decision"] == "approved" else "chat.action_cancelled",
                actor_user_id=user.user_id,
                resource_type="chat",
                resource_id=conversation.uuid,
                resource_name=conversation.title,
                team_id=getattr(conversation, "team_id", None),
                organization_id=getattr(user, "organization_id", None),
                detail={
                    "action": e["action"],
                    "tool": e["tool"],
                    "summary": e["summary"],
                    "via": e["via"],
                    "outcome": e["outcome"],
                    "result": e["detail"],
                    "approvals": e["approvals"],
                    "runs": e["runs"],
                    "card_id": e["call_id"],
                },
            )
        return len(mine)
    except Exception:
        logger.exception("Failed to audit chat approvals for %s", getattr(conversation, "uuid", "?"))
        return 0

