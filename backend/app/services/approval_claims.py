"""Catch a chat reply that claims a step no tool call backs.

Two shapes: a reply pointing at an approval button no tool prepared, and a
reply that ends by announcing a step it never took (bottom of this module).

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
    # "click the Create workflow", "press **Approve**", "use **Create workflow**"
    re.compile(
        rf"\b(?:click|press|tap|hit|select|use)\b(?:\s+on)?(?:\s+the)?{_DECORATION}{_LABEL}\b",
        re.IGNORECASE,
    ),
    # "review the card", "review the workflow card", "the preview card".
    # Not a bare "the card below": a run or extraction card is a card too.
    re.compile(r"\breview\s+the\s+(?:[a-z]+\s+)?card\b|\b(?:preview|confirmation)\s+card\b", re.IGNORECASE),
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


# Added after a reply that still points at an approval card once the model
# has had its retry. Support ticket: "I've prepared the workflow — review the
# card and use Create workflow" with no tool call, no card and no way to
# finish. The streamed text can't be taken back, so the user is told plainly.
UNPREPARED_CARD_NOTE = (
    "\n\n_Note: no approval card was actually prepared for this reply, so "
    "nothing has been created or run. Ask me to try again._"
)


def unprepared_card_note(text: str, deps: "AgenticChatDeps | None") -> str | None:
    """The note to add when *text* points at an approval card that doesn't exist."""
    if deps is None or not promises_approval_button(text) or approval_card_is_live(deps):
        return None
    return UNPREPARED_CARD_NOTE


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


# A reply that ends by announcing a step ("Running a preview of the
# workflow…", "Let me run it now.") and then stops: the model wrote the
# narration but ended its turn without the tool call, so nothing runs and the
# chat sits on "Prepare to run…" (support ticket). Only the last line counts;
# an announcement mid-reply was followed by more text, so it isn't the stop.
_ACTION_VERBS = (
    r"(?:run|re-?run|prepare|start|create|extract|build|save|execute|launch|kick\s+off|apply|update)"
)
_ACTION_GERUNDS = (
    r"(?:running|re-?running|preparing|starting|creating|extracting|building|saving"
    r"|executing|launching|kicking\s+off|applying|updating)"
)
_ANNOUNCES = [
    # "Running a preview of NOA Budget & Profile Summary…", "Prepare to run:"
    re.compile(
        rf"^(?:(?:ok(?:ay)?|now|next|alright)[,.!]?\s+)?(?:i'?m\s+|i\s+am\s+)?(?:now\s+)?"
        rf"(?:{_ACTION_GERUNDS}|prepare\s+to)\b.*(?:…|\.\.\.|:)$",
        re.IGNORECASE,
    ),
    # "I'll run it now.", "Let me prepare the run."
    re.compile(
        rf"\b(?:i'?ll|i\s+will|i'?m\s+going\s+to|i\s+am\s+going\s+to|let\s+me|let'?s)\s+"
        rf"(?:now\s+|go\s+ahead\s+and\s+|first\s+)?{_ACTION_VERBS}\b",
        re.IGNORECASE,
    ),
]
# "I'll run it once you approve" and "Shall I run it?" wait on the user.
_WAITS_ON_USER = re.compile(
    r"\?|\b(?:if|once|when|whenever|after\s+you|would\s+you|do\s+you|want|should|shall|ready)\b",
    re.IGNORECASE,
)


def _last_line(text: str) -> str:
    lines = [line.strip(" \t*_`>#-") for line in (text or "").strip().splitlines()]
    lines = [line for line in lines if line]
    return lines[-1] if lines else ""


def announces_unfinished_action(text: str) -> bool:
    """Whether *text* ends by saying a step is about to happen."""
    line = _last_line(text)
    if not line or _WAITS_ON_USER.search(line):
        return False
    return any(pattern.search(line) for pattern in _ANNOUNCES)


ANNOUNCE_RETRY_INSTRUCTION = (
    "Your reply ends by announcing a step, but you ended your turn without "
    "calling a tool, so nothing happened and the user is left waiting. Call the "
    "tool now (for a workflow run, run_workflow with confirmed=false shows the "
    "approval card). If you cannot, say in one sentence what is stopping you. "
    "Do not repeat your previous reply."
)


def require_announced_action(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, a reply that stops at an announcement."""
    deps = ctx.deps
    if (
        ctx.partial_output
        or deps is None
        or getattr(deps, "announced_action_retry_used", False)
        or not announces_unfinished_action(output)
    ):
        return output
    # Once only: a second miss is accepted rather than failing the turn.
    deps.announced_action_retry_used = True
    raise ModelRetry(ANNOUNCE_RETRY_INSTRUCTION)


# A reply that calls an attached knowledge base validated when it never was
# ("Validated — the Subaward Policies page is ready", support ticket). Chat has
# no tool that validates a knowledge base, so the claim can only be invented.
# "Not yet validated", "never been validated", "unvalidated" are negated and
# don't count.
_VALIDATED = re.compile(r"\bvalidated\b", re.IGNORECASE)
# A negation shortly before "validated", within the same clause: "not yet
# validated", "hasn't been validated", "never been validated". ("Unvalidated"
# has no word boundary before "validated", so it never matches at all.)
_NEGATION = re.compile(r"(?:\bnot\b|\bnever\b|n't\b|\bno\b|\byet to be\b|\bwithout being\b)[^.!?;:\n]{0,20}$", re.IGNORECASE)


def claims_validated(text: str, subjects: list[str] | None = None) -> bool:
    """Whether *text* says something is validated, outside a negation.

    With ``subjects`` (knowledge base titles), only a claim with one of them,
    or the words "knowledge base", within 150 characters counts, so "the
    template was validated last week" is left alone.
    """
    text = text or ""
    names = [s.lower() for s in (subjects or []) if s] + ["knowledge base"]
    for m in _VALIDATED.finditer(text):
        if _NEGATION.search(text[max(0, m.start() - 40):m.start()]):
            continue
        if subjects is None:
            return True
        window = text[max(0, m.start() - 150):m.end() + 150].lower()
        if any(name in window for name in names):
            return True
    return False


def _tools_called_this_turn(messages) -> set[str]:
    """Names of the tools called since the user's latest message."""
    from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, UserPromptPart

    since_prompt = []
    for message in messages or []:
        if isinstance(message, ModelRequest) and any(isinstance(p, UserPromptPart) for p in message.parts):
            since_prompt = []
        else:
            since_prompt.append(message)
    return {
        part.tool_name
        for message in since_prompt if isinstance(message, ModelResponse)
        for part in message.parts if isinstance(part, ToolCallPart)
    }


def _validation_ran_this_turn(messages) -> bool:
    """Whether a validation tool was called since the user's latest message."""
    return "run_validation" in _tools_called_this_turn(messages)


VALIDATION_RETRY_INSTRUCTION = (
    "Your reply says something is validated, but no validation ran, and the "
    "attached knowledge base(s) {titles} have never been validated. You cannot "
    "validate a knowledge base from chat. Rewrite the reply: give the knowledge "
    "base's real status from the 'Attached knowledge bases: current status' "
    "section (sources ready and any that failed), say it has not been validated, "
    "and tell the user knowledge base validation runs from Knowledge, opening the "
    "knowledge base, then its Validation tab. Do not repeat your previous reply."
)


def require_honest_validation(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, a reply that calls an
    unvalidated knowledge base validated when no validation ran."""
    deps = ctx.deps
    titles = list(getattr(deps, "unvalidated_kb_titles", None) or []) if deps else []
    if (
        ctx.partial_output
        or not titles
        or getattr(deps, "validation_claim_retry_used", False)
        or not claims_validated(output, titles)
        or _validation_ran_this_turn(ctx.messages)
    ):
        return output
    deps.validation_claim_retry_used = True
    raise ModelRetry(VALIDATION_RETRY_INSTRUCTION.format(titles=", ".join(f'"{t}"' for t in titles)))


# ---------------------------------------------------------------------------
# Nodes the workflow editor does not offer
# ---------------------------------------------------------------------------
# The palette marks these enabled: false. Asked for one, a model sometimes
# writes step-by-step instructions (and sample Python) for adding it, though
# the prompt says it is unavailable (live certification runs, October 2026).
# A reply that also says the node is unavailable passes; only instructions
# with no such statement are sent back, once per turn.

_UNAVAILABLE_NODE = r"(?:code|browser automation|describe image|package builder)\s+(?:node|step)"
_ADD_INSTRUCTION = re.compile(
    rf"\b(?:select|choose|click|drag|add|insert|pick)\b[^.!?\n]{{0,40}}{_UNAVAILABLE_NODE}"
    rf"|{_UNAVAILABLE_NODE}[^.!?\n]{{0,30}}\b(?:allows you to|lets you|is perfect)"
    r"|\bselect\s+`?code`?\s+as the step type",
    re.IGNORECASE,
)
_SAYS_UNAVAILABLE = re.compile(
    r"not available|unavailable|not (?:a )?supported|(?:does not|doesn't|do not|don't) (?:have|offer|support)"
    r"|(?:can't|cannot|can not) add|disabled"
    rf"|\bno\s+{_UNAVAILABLE_NODE}",
    re.IGNORECASE,
)

UNAVAILABLE_NODE_RETRY_INSTRUCTION = (
    "Your reply explains how to add a workflow node that Vandalizer's editor does not "
    "offer (Code, Browser Automation, Describe Image and Package Builder are unavailable). "
    "Rewrite it: say that node is not available and offer a supported route instead, such "
    "as extraction, prompt, format, research, knowledge base query, website or approval "
    "steps, or the course's own method when a certification module applies."
)


def describes_unavailable_node(text: str) -> bool:
    plain = text.replace("’", "'")
    return bool(_ADD_INSTRUCTION.search(plain)) and not _SAYS_UNAVAILABLE.search(plain)


def require_available_nodes(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, instructions for adding a
    node the workflow editor does not offer."""
    deps = ctx.deps
    if (
        ctx.partial_output
        or deps is None
        or getattr(deps, "unavailable_node_retry_used", False)
        or not describes_unavailable_node(output)
    ):
        return output
    deps.unavailable_node_retry_used = True
    raise ModelRetry(UNAVAILABLE_NODE_RETRY_INSTRUCTION)


# ---------------------------------------------------------------------------
# Certification actions only the learner can take
# ---------------------------------------------------------------------------
# Asked to approve a course decision or share course work, a model often gives
# generic advice that names no real control, or invents one ("Share Progress"),
# even with the facts in the prompt (live CHAT-11 batches passed 4/5, then 0/5).
# No chat tool can approve, run or share on the learner's behalf, so the reply
# must name the route that exists. A reply that misses it is sent back once.

_COURSE = r"certification|course|module|foundations|lab|assessment|scope decision|my progress|certificate"
_ASKS_APPROVAL = re.compile(
    r"\b(?:approve|sign off on|accept|confirm|record|make)\b[^.?!\n]{0,60}\b(?:scope decision|decision|approval)\b"
    r"|\bapprove\b[^.?!\n]{0,80}\b(?:for me|on my behalf)\b",
    re.IGNORECASE,
)
_ASKS_SHARE = re.compile(r"\b(?:share|send|show)\b[^.?!\n]{0,80}\b(?:with|to)\b[^.?!\n]{0,40}\b(?:team|manager|supervisor|colleague)", re.IGNORECASE)
_NAMES_APPROVAL_ROUTE = re.compile(r"open (?:the )?module assessment", re.IGNORECASE)
_NAMES_SHARE_ROUTE = re.compile(r"certificate|no (?:share|sharing)|(?:isn't|is not|no) (?:a )?(?:share|sharing)", re.IGNORECASE)

LEARNER_ACTION_RETRY_INSTRUCTION = {
    "approval": (
        "The learner asked you to approve or record a certification decision for them. No chat "
        "tool can do that, and you did not. Rewrite the reply: say plainly that only the learner "
        "can record the decision, and tell them where: open the course panel, choose Open module "
        "assessment for the module, review the proposed scope, and record their own decision "
        "there. You may then offer to explain the decision or check their saved progress."
    ),
    "share": (
        "The learner asked to share certification work with a team or manager. Course progress is "
        "private and the course has no share control. Rewrite the reply: say there is no sharing "
        "control for course progress, and that once they graduate they can download the issued "
        "certificate PDF from the course panel and send it themselves. Do not describe any share "
        "button, link or visibility setting."
    ),
}


def learner_only_request(message: str) -> str | None:
    """'approval' or 'share' when a certification message asks for one, else None."""
    plain = message.replace("’", "'")
    if not re.search(_COURSE, plain, re.IGNORECASE):
        return None
    if _ASKS_SHARE.search(plain):
        return "share"
    if _ASKS_APPROVAL.search(plain):
        return "approval"
    return None


def names_learner_route(kind: str, text: str) -> bool:
    route = _NAMES_APPROVAL_ROUTE if kind == "approval" else _NAMES_SHARE_ROUTE
    return bool(route.search(text.replace("’", "'")))


def require_learner_route(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, a reply to an approve/share
    request for course work that does not name the learner's real route."""
    deps = ctx.deps
    if ctx.partial_output or deps is None or getattr(deps, "learner_route_retry_used", False):
        return output
    kind = learner_only_request(getattr(deps, "user_message", "") or "")
    if kind is None or names_learner_route(kind, output):
        return output
    deps.learner_route_retry_used = True
    raise ModelRetry(LEARNER_ACTION_RETRY_INSTRUCTION[kind])


# ---------------------------------------------------------------------------
# Course entry
# ---------------------------------------------------------------------------
# Every certification entry point (the /certification URL, the rail badge, the
# account menu, the home CTA, a card's action link) sends one of these kickoff
# messages (frontend/src/lib/certificationChat.ts). A reply that never read the
# learner's course is a generic answer dressed as the course; it is sent back
# once with an instruction to read the enrollment first.

COURSE_ENTRY_MESSAGES = frozenset({
    "Start the Vandalizer certification course — show me where to begin.",
    "Continue my certification — show my progress and the next module.",
    "Show my completed certification and what each module covered.",
})
_ASKS_COURSE_ENTRY = re.compile(
    r"^\W*(?:please\s+)?(?:start|begin|continue|resume|open)\b[^.?!\n]{0,30}\b(?:certification|course)\b",
    re.IGNORECASE,
)

COURSE_ENTRY_RETRY_INSTRUCTION = (
    "The learner opened the certification course, but you answered without reading their "
    "enrollment. Call get_certification_progress now and answer from its result: the course "
    "title, where the learner stands, and the one next action it names (the next lesson, module "
    "or assessment). If the tool returns an error, say what it says and how to recover; do not "
    "describe the course from memory."
)


def is_course_entry(message: str) -> bool:
    text = " ".join(message.split())
    return text in COURSE_ENTRY_MESSAGES or bool(_ASKS_COURSE_ENTRY.search(text))


def require_course_read(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, a course-entry reply that
    called no certification read tool."""
    deps = ctx.deps
    if (
        ctx.partial_output
        or deps is None
        or getattr(deps, "course_entry_retry_used", False)
        or not is_course_entry(getattr(deps, "user_message", "") or "")
        or any(name.startswith("get_certification_") for name in _tools_called_this_turn(ctx.messages))
    ):
        return output
    deps.course_entry_retry_used = True
    raise ModelRetry(COURSE_ENTRY_RETRY_INSTRUCTION)


# ---------------------------------------------------------------------------
# Lessons before the exercise
# ---------------------------------------------------------------------------
# Support ticket: after Module 0's first lesson chat went straight to the
# reflection questions, skipping lessons 2-9, and in Module 1 it offered "Jump
# to the exercise". The course tools report unread_lessons (including lessons
# read in the card); a reply that moves to the exercise while some are unread,
# when the learner didn't ask to skip, is sent back once. Guidance, not a gate:
# completion rules are unchanged.

_ASSESSMENT = r"(?:exercise|reflection|reflective|assessment|self-assessment|challenge|lab|quiz)"
_OFFERS_SKIP = re.compile(
    rf"\b(?:jump|skip|go|move|head|proceed)\s+(?:straight\s+|right\s+|ahead\s+|directly\s+)?(?:on\s+)?to\s+(?:the\s+)?(?:\w+\s+)?{_ASSESSMENT}"
    rf"|\b(?:skip|skipping)\s+(?:the\s+)?(?:remaining\s+|rest\s+of\s+the\s+|other\s+)?lessons?\b"
    rf"|\b(?:let'?s|now|next)\b[^.?!\n]{{0,30}}\b(?:start|begin|do|try|tackle|answer)\b[^.?!\n]{{0,20}}\b{_ASSESSMENT}"
    rf"|\b{_ASSESSMENT}\s+questions?\s*:",
    re.IGNORECASE,
)
_LEARNER_ASKS_SKIP = re.compile(
    rf"\b(?:skip|jump|straight to|go to|move on to|ready for|start|begin|do)\b[^.?!\n]{{0,30}}\b(?:{_ASSESSMENT}|lessons?)\b",
    re.IGNORECASE,
)
_ASSESSMENT_TOOLS = {
    "check_certification_module", "submit_certification_assessment",
    "complete_certification_module", "provision_certification_lab",
}


def _this_turn_tool_returns(messages) -> list:
    """Tool results since the user's latest message, in order."""
    from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

    returns: list = []
    for message in messages or []:
        if isinstance(message, ModelRequest):
            if any(isinstance(p, UserPromptPart) for p in message.parts):
                returns = []
            returns += [p for p in message.parts if isinstance(p, ToolReturnPart)]
    return returns


def unread_lessons_this_turn(messages) -> tuple[str, list[int]] | None:
    """The module and unread lesson numbers the latest course result reported."""
    for part in reversed(_this_turn_tool_returns(messages)):
        content = part.content
        if isinstance(content, dict) and isinstance(content.get("unread_lessons"), list):
            return str(content.get("module_id") or ""), list(content["unread_lessons"])
    return None


def skips_ahead(text: str) -> bool:
    return bool(_OFFERS_SKIP.search((text or "").replace("’", "'")))


LESSON_ORDER_RETRY_INSTRUCTION = (
    "Module {module} still has unread lessons ({lessons}), and the learner did not ask to "
    "skip them. Do not move to or offer the exercise, reflection or assessment yet. "
    "Rewrite the reply: call get_certification_lesson for lesson {first} and add one "
    "framing sentence. Lessons the learner already read in the card are not in this list; "
    "do not send those again."
)


def require_lessons_in_order(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, a reply that skips to a
    module's exercise while lessons are unread and the learner didn't ask."""
    deps = ctx.deps
    if ctx.partial_output or deps is None or getattr(deps, "lesson_skip_retry_used", False):
        return output
    unread = unread_lessons_this_turn(ctx.messages)
    if not unread or not unread[1]:
        return output
    if _LEARNER_ASKS_SKIP.search((getattr(deps, "user_message", "") or "").replace("’", "'")):
        return output
    if not (skips_ahead(output) or _tools_called_this_turn(ctx.messages) & _ASSESSMENT_TOOLS):
        return output
    deps.lesson_skip_retry_used = True
    module, lessons = unread
    raise ModelRetry(LESSON_ORDER_RETRY_INSTRUCTION.format(
        module=module or "this module", lessons=", ".join(map(str, lessons)), first=lessons[0],
    ))
