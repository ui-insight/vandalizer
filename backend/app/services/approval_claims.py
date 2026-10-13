"""Catch a chat reply that points at an approval button no tool prepared.

The approval card (with its "Create workflow" / "Run workflow" / "Approve …"
button) renders only from a write tool's confirmed=false preview. A model that
writes "click the Create workflow button to confirm" without calling the tool
leaves the user looking for a button that isn't there (support ticket). The
prompt already forbids it; this is the check that doesn't depend on the model
listening. The agent's output validator sends such a reply back once, telling
the model to call the tool so the card appears.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic_ai import ModelRetry, RunContext

from app.services.chat_tools import _APPROVE_BUTTON_LABELS

if TYPE_CHECKING:
    from app.services.chat_deps import AgenticChatDeps

# Every name an approval card's approve button can carry: the named labels,
# and "Approve <tool>" for the rest. "Confirm" is not one, but it is what
# models call it, so it counts too.
_LABEL = (
    "(?:"
    + "|".join(re.escape(label) for label in _APPROVE_BUTTON_LABELS.values())
    + r"|approve(?:\s+[a-z][a-z ]{0,40}?)?|confirm)"
)
_DECORATION = r"[\s*_`\"'“”‘’]*"

_PROMISES = [
    # "the **Create workflow** button", "Confirm button"
    re.compile(rf"\b{_LABEL}{_DECORATION}\s+button\b", re.IGNORECASE),
    # "click the Create workflow", "press **Approve**"
    re.compile(
        rf"\b(?:click|press|tap|hit|select)\b(?:\s+on)?(?:\s+the)?{_DECORATION}{_LABEL}\b",
        re.IGNORECASE,
    ),
    # "[Create workflow]" written as a button (not a link, not [ACTION:…] markup)
    re.compile(rf"\[\s*{_LABEL}\s*\](?!\()", re.IGNORECASE),
    re.compile(r"\bapproval card\b", re.IGNORECASE),
]

# A card from the previous turn may still be waiting ("click Create workflow
# above"). Each turn adds the user's message and the reply.
_TURNS_A_CARD_STAYS_LIVE = 2


def promises_approval_button(text: str) -> bool:
    """Whether *text* tells the user to use an approval card's button."""
    return any(pattern.search(text or "") for pattern in _PROMISES)


def approval_card_is_live(deps: "AgenticChatDeps") -> bool:
    """Whether a preview armed this turn or last turn has a card on screen."""
    conversation = getattr(deps, "conversation", None)
    marker = int(getattr(deps, "turn_marker", 0) or 0)
    for entry in getattr(conversation, "pending_confirmations", None) or []:
        if isinstance(entry, dict) and int(entry.get("turn", -1)) >= marker - _TURNS_A_CARD_STAYS_LIVE:
            return True
    return False


RETRY_INSTRUCTION = (
    "Your reply tells the user to use an approval button, but there is no "
    "approval card: you described the action without calling its tool. The "
    "card only appears when you call the tool. Call it now with "
    "confirmed=false (for example create_workflow, run_workflow or "
    "create_knowledge_base, with the details you described), then say in one "
    "sentence what you prepared. Do not repeat your previous reply."
)


def require_approval_card(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, a reply promising a missing card."""
    deps = ctx.deps
    if (
        ctx.partial_output
        or deps is None
        or getattr(deps, "approval_card_retry_used", False)
        or not promises_approval_button(output)
        or approval_card_is_live(deps)
    ):
        return output
    # Once only: a second miss is accepted rather than failing the turn.
    deps.approval_card_retry_used = True
    raise ModelRetry(RETRY_INSTRUCTION)
