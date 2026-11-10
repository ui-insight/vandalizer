"""Which waiting actions one user turn may carry out.

Support ticket: with several approval cards waiting (Move files, Add to inbox
×3, Save to folder), clicking Move files carried out all of them. Every card
sent the same "Yes, go ahead", and the confirm gate only asked whether an
action had been previewed on an earlier turn — so one click approved
everything armed.

Now a turn names what it approves:

* A card's button sends its preview's tool call id (``approval_for``). Only
  the action that card previewed may run; the other cards keep waiting.
* A card's Cancel sends ``decline_for``; that action is disarmed and nothing
  runs.
* A typed approval ("yes, go ahead", "approve it") names no card. It may run
  the waiting action only when exactly one was previewed in the latest turn
  that previewed anything. With several, nothing runs and the assistant asks
  the user to approve each card.

Pure: no database, so the gate's decision is easy to pin in tests.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TurnApproval:
    # Fingerprints of the armed actions this turn may execute.
    approved: frozenset[str]
    # Pending entries left after a decline (None: unchanged).
    remaining: list[dict] | None = None
    # How this turn decided, for the gate's message to the model.
    mode: str = "none"  # "card" | "typed_single" | "typed_ambiguous" | "declined" | "none"
    waiting: int = 0


def _entries(pending: list | None) -> list[dict]:
    return [p for p in (pending or []) if isinstance(p, dict) and p.get("fp")]


def decide(
    pending: list | None, *, approval_for: str | None = None, decline_for: str | None = None,
) -> TurnApproval:
    entries = _entries(pending)
    if decline_for:
        remaining = [p for p in entries if p.get("call_id") != decline_for]
        return TurnApproval(frozenset(), remaining=remaining, mode="declined", waiting=len(remaining))
    if approval_for:
        chosen = frozenset(p["fp"] for p in entries if p.get("call_id") == approval_for)
        return TurnApproval(chosen, mode="card", waiting=len(entries))
    if not entries:
        return TurnApproval(frozenset(), mode="none")
    latest = max(int(p.get("turn", 0) or 0) for p in entries)
    newest = [p for p in entries if int(p.get("turn", 0) or 0) == latest]
    if len(newest) == 1:
        return TurnApproval(frozenset({newest[0]["fp"]}), mode="typed_single", waiting=len(entries))
    return TurnApproval(frozenset(), mode="typed_ambiguous", waiting=len(newest))


def pending_call_ids(pending: list | None) -> list[str]:
    """The cards still waiting: their previews' tool call ids, for the client.

    The client keeps exactly these cards clickable, so a turn that decided one
    card (or a typed reply that decided none) never strands the others.
    """
    return [p["call_id"] for p in _entries(pending) if isinstance(p.get("call_id"), str)]


def _label(entry: dict) -> str:
    """A waiting card as the user sees it: its button, and what it does."""
    label = entry.get("label") or str(entry.get("tool") or "action").replace("_", " ")
    summary = entry.get("summary")
    return f'"{label}" ({summary})' if summary else f'"{label}"'


_SHORT_REPLY = (
    "Reply in one or two short sentences: what happened, then the next step. "
    "Put tables, notes and caveats in a :::details block."
)


def approval_reminder(
    decision: TurnApproval, pending: list | None, *,
    approval_for: str | None = None, decline_for: str | None = None,
) -> str:
    """What this turn decided, named by card, for the model.

    Support ticket: "Yes, go ahead" didn't say which card it approved, so chat
    sometimes ran it and sometimes explained again. Empty when nothing waits.
    """
    entries = _entries(pending)
    if not entries:
        return ""

    def still_waiting(after: dict | None) -> str:
        rest = [_label(p) for p in entries if p is not after]
        return f" Still waiting after it, in order: {', '.join(rest)}." if rest else ""

    if decision.mode == "card":
        chosen = next((p for p in entries if p.get("call_id") == approval_for), None)
        if chosen is None:
            return ""
        return (
            f"The user approved the card {_label(chosen)}. Run exactly that action now: call "
            f"{chosen.get('tool')} with the same arguments as its preview and confirmed=true. "
            f"Do not run any other waiting action.{still_waiting(chosen)} {_SHORT_REPLY}"
        )
    if decision.mode == "declined":
        skipped = next((p for p in entries if p.get("call_id") == decline_for), None)
        what = _label(skipped) if skipped else "a waiting step"
        return (
            f"The user skipped {what}; it will not run. Say so in a few words and move on to "
            f"the next step.{still_waiting(skipped)} {_SHORT_REPLY}"
        )
    if decision.mode == "typed_single":
        only = next((p for p in entries if p["fp"] in decision.approved), None)
        if only is None:
            return ""
        return (
            f"One step is waiting for approval: {_label(only)}. If the user's message approves "
            f"it, run it now (call {only.get('tool')} with the same arguments and confirmed=true). "
            f"Otherwise answer them and end by pointing to that card as the next step. {_SHORT_REPLY}"
        )
    if decision.mode == "typed_ambiguous":
        latest = max(int(p.get("turn", 0) or 0) for p in entries)
        labels = [_label(p) for p in entries if int(p.get("turn", 0) or 0) == latest]
        return (
            f"{len(labels)} steps are waiting for approval: {', '.join(labels)}. The user's "
            "message names none of them, so run none. If it is an approval (yes, go ahead, do "
            "it), reply with only the question \"Which one: <button> or <button>?\" using those "
            "button names, and nothing else. Otherwise answer briefly and point to the first card."
        )
    return ""


def blocked_instruction(mode: str, waiting: int) -> str:
    """What the model is told when it tries to run an action this turn didn't approve."""
    if mode == "card":
        why = "The user approved a different card, not this action."
    elif mode == "typed_ambiguous":
        why = (
            f"{waiting} actions are waiting for approval and the user's message didn't say which one; "
            "a typed approval can't approve several actions at once."
        )
    elif mode == "declined":
        why = "The user cancelled a different card; this action was not approved."
    else:
        why = "The user has not approved this action."
    return (
        f"NOT DONE. {why} Do not run it again this turn and do not say it is done. "
        "Tell the user which actions are still waiting and that each one runs only when they "
        "approve its own card."
    )
