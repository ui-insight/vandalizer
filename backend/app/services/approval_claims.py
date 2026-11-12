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
from collections.abc import Sequence
from pydantic_ai.messages import ModelMessage, ToolReturnPart


import re
from typing import TYPE_CHECKING

from pydantic_ai import ModelRetry, RunContext

from app.services.chat_tools import _APPROVE_BUTTON_LABELS, approve_button_label

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
    r"(?:run|re-?run|prepare|start|create|extract|build|save|execute|launch|kick\s+off|apply|update|verify)"
)
_ACTION_GERUNDS = (
    r"(?:running|re-?running|preparing|starting|creating|extracting|building|saving"
    r"|executing|launching|kicking\s+off|applying|updating|verifying)"
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


def _tools_called_this_turn(messages: Sequence[ModelMessage] | None) -> set[str]:
    """Names of the tools called since the user's latest message."""
    from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, UserPromptPart

    since_prompt: list[ModelMessage] = []
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


def _validation_ran_this_turn(messages: Sequence[ModelMessage] | None) -> bool:
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
# The module the learner chose
# ---------------------------------------------------------------------------
# Support ticket: a learner who had completed Modules 1-4 said "I want to start
# certification from beginning", was offered two options, and replied "from 1
# AI Literacy". Chat repeated the options, then opened Extraction Engine
# (Module 5), said it could not skip backward, and pasted that lesson as plain
# text with no card; AI Literacy opened on the fifth message. Every lesson of
# a completed module is read, and "never re-send read lessons" left no way to
# review one. A reply to a learner who picks a module must open that module's
# lesson card; otherwise it is sent back once.

_CHOOSES = re.compile(
    r"\b(?:from|start|starting|begin|beginning|restart|re-?start|review|re-?teach|redo|re-?do|repeat|"
    r"go\s+back|back\s+to|open|teach|take\s+me|study|learn|pick|choose|want|let'?s|please)\b",
    re.IGNORECASE,
)
_COURSE_WORDS = re.compile(r"\b(?:certification|course|module|lesson)s?\b", re.IGNORECASE)
_MODULE_NUMBER = re.compile(r"\bmodule\s+(\d{1,2})\b", re.IGNORECASE)
_LESSON_NUMBER = re.compile(r"\blesson\s+(\d{1,2})\b", re.IGNORECASE)
# Asking for the module's exercise or standing is not asking to open a lesson.
_NOT_A_LESSON = re.compile(
    r"\b(?:exercise|reflection|assessment|self-assessment|challenge|lab|quiz|check|progress|xp|"
    r"complete|completion|certificate|credit|score|stars?)\b",
    re.IGNORECASE,
)


def _course_modules(messages: Sequence[ModelMessage] | None) -> list[tuple[str, str]]:
    """(module_id, title) in course order: from this conversation's latest
    progress read (the learner's own enrollment), else the original course."""
    for message in reversed(list(messages or [])):
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart) and part.tool_name == "get_certification_progress":
                content = part.content
                rows = content.get("modules") if isinstance(content, dict) else None
                if isinstance(rows, list) and rows:
                    return [(str(r["module_id"]), str(r.get("title") or r["module_id"]))
                            for r in rows if isinstance(r, dict) and r.get("module_id")]
    from app.services import certification_service as cert_svc

    return [(mid, cert_svc.MODULE_TITLES.get(mid, mid)) for mid in cert_svc.MODULE_ORDER]


def _in_course_conversation(message: str, messages: Sequence[ModelMessage] | None) -> bool:
    """Module titles are ordinary words ("Foundations", "Workflow Design"), so
    only a conversation already about the course counts."""
    from pydantic_ai.messages import ToolCallPart

    if _COURSE_WORDS.search(message):
        return True
    return any(
        isinstance(part, ToolCallPart) and "certification" in part.tool_name
        for m in messages or [] for part in getattr(m, "parts", [])
    )


def chosen_module(message: str, modules: list[tuple[str, str]]) -> tuple[str, str, int, int | None] | None:
    """(module_id, title, number, lesson) when *message* picks one module to
    open ("from 1 AI Literacy", "review module 2"), else None.

    A module is picked by its title or "module N" (numbered from 1 in course
    order); a title wins over a number. A bare number is not a module: "1" in
    reply to a list of options means the first option.
    """
    text = " ".join((message or "").replace("’", "'").split())
    if not text or len(text) > 200 or not modules or _NOT_A_LESSON.search(text):
        return None
    lowered = text.lower()
    by_title = [i for i, (_mid, title) in enumerate(modules)
                if re.search(rf"(?<!\w){re.escape(title.lower())}(?!\w)", lowered)]
    if len(by_title) > 1:
        return None
    index: int | None = by_title[0] if by_title else None
    if index is None:
        number = _MODULE_NUMBER.search(text)
        if number and 1 <= int(number.group(1)) <= len(modules):
            index = int(number.group(1)) - 1
    if index is None:
        return None
    # "What does Foundations cover?" names a module without choosing it.
    if not _CHOOSES.search(text) and ("?" in text or len(text.split()) > 4):
        return None
    lesson = _LESSON_NUMBER.search(text)
    module_id, title = modules[index]
    return module_id, title, index + 1, int(lesson.group(1)) if lesson else None


def _lessons_opened_this_turn(messages: Sequence[ModelMessage] | None) -> set[str]:
    """module_ids of get_certification_lesson calls since the user's latest message."""
    from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, UserPromptPart

    opened: set[str] = set()
    for message in messages or []:
        if isinstance(message, ModelRequest) and any(isinstance(p, UserPromptPart) for p in message.parts):
            opened = set()
        elif isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == "get_certification_lesson":
                    try:
                        args = part.args_as_dict()
                    except Exception:
                        continue
                    if args.get("module_id"):
                        opened.add(str(args["module_id"]))
    return opened


CHOSEN_MODULE_RETRY_INSTRUCTION = (
    "The learner chose Module {number}, {title} (module_id \"{module_id}\"). Open it now: call "
    "get_certification_lesson with module_id \"{module_id}\" and lesson_number {lesson}, and add one "
    "framing sentence. A completed module can always be reviewed from any lesson; reviewing it "
    "changes no credit. Do not ask again which module, do not open a different module, and do "
    "not write the lesson's content yourself: the lesson card shows it."
)


def require_chosen_module(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, a reply to a learner who
    chose a module that doesn't open that module's lesson card."""
    deps = ctx.deps
    if ctx.partial_output or deps is None or getattr(deps, "chosen_module_retry_used", False):
        return output
    message = getattr(deps, "user_message", "") or ""
    if not _in_course_conversation(message, ctx.messages):
        return output
    choice = chosen_module(message, _course_modules(ctx.messages))
    if choice is None:
        return output
    module_id, title, number, lesson = choice
    if module_id in _lessons_opened_this_turn(ctx.messages):
        return output
    deps.chosen_module_retry_used = True
    raise ModelRetry(CHOSEN_MODULE_RETRY_INSTRUCTION.format(
        number=number, title=title, module_id=module_id, lesson=lesson or 1,
    ))


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


def _this_turn_tool_returns(messages: Sequence[ModelMessage] | None) -> list:
    """Tool results since the user's latest message, in order."""
    from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

    returns: list[ToolReturnPart] = []
    for message in messages or []:
        if isinstance(message, ModelRequest):
            if any(isinstance(p, UserPromptPart) for p in message.parts):
                returns = []
            returns += [p for p in message.parts if isinstance(p, ToolReturnPart)]
    return returns


def unread_lessons_this_turn(messages: Sequence[ModelMessage] | None) -> tuple[str, list[int]] | None:
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


# ---------------------------------------------------------------------------
# A lesson card's content restated under the card.
#
# Support ticket: under the "From one workflow to many" card, chat's summary
# said a project means "everything is indexed together and you can chat across
# the whole set", where the lesson says a project "does not itself … make every
# source ready for chat"; and that "a frequent, simple extraction may be worth a
# workflow", where it says "a frequent question may still need only a small
# extraction". The card already shows the lesson, and the prompt asks for one
# framing sentence, but a paraphrase is where meaning gets reversed, and the
# model wrote one anyway. A reply is sent back once when, right after a lesson
# card, it restates the lesson: it runs past a framing sentence or two, and
# several of its sentences each carry several of the lesson's own terms.
# ---------------------------------------------------------------------------

# A framing sentence and an invitation fit under this. Measured on 64 replies a
# separate model wrote under 8 real lesson cards: framings ran to 36 words and
# none was flagged at 30; 31 of 32 summaries were, the miss a one-sentence gist.
_FRAMING_WORDS = 30
# Sentences sharing this many of the lesson's terms are restating it.
_RESTATING_TERMS = 3
_RESTATING_SENTENCES = 2

_LEARNER_ASKS_ABOUT = re.compile(
    r"\?|\b(?:explain|summar|what does|what do|why|how does|how do|mean|clarify|in other words|tl;?dr)\w*",
    re.IGNORECASE,
)
_TERM = re.compile(r"[a-z][a-z'-]{3,}")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_COMMON = frozenset(
    """
    about after also because before being between both could does each even every
    from have here into just like make many more most much must need only other over
    same should some such than that their them then there these they this those
    through very want were what when where which while will with without would your
    lesson lessons card read reading next ready practice module first second third
    """.split()
)


def _terms(text: str) -> set[str]:
    out = set()
    for word in _TERM.findall((text or "").lower().replace("’", "'")):
        word = word.strip("'-")
        if len(word) >= 4 and word not in _COMMON:
            out.add(word[:6])  # a crude stem: "projects"/"project", "indexed"/"indexing"
    return out


def restates_lesson(reply: str, lesson_text: str) -> bool:
    """Whether *reply* restates *lesson_text* rather than framing it."""
    if len((reply or "").split()) <= _FRAMING_WORDS:
        return False
    lesson = _terms(lesson_text)
    restating = sum(
        1 for sentence in _SENTENCE_SPLIT.split(reply)
        if len(_terms(sentence) & lesson) >= _RESTATING_TERMS
    )
    return restating >= _RESTATING_SENTENCES


def lesson_shown_this_turn(messages: Sequence[ModelMessage] | None) -> str | None:
    """The text of the latest lesson card returned since the learner's message."""
    for part in reversed(_this_turn_tool_returns(messages)):
        if getattr(part, "tool_name", None) != "get_certification_lesson":
            continue
        content = part.content
        if isinstance(content, dict) and isinstance(content.get("content"), str):
            text = content["content"]
            if isinstance(text, str):
                return text
    return None


LESSON_RESTATED_RETRY_INSTRUCTION = (
    "The lesson card already shows this lesson to the learner. Do not summarize or "
    "restate it in your own words: a paraphrase can change what the lesson says. "
    "Rewrite the reply as one or two sentences that introduce the card and invite the "
    "learner to read it and try its practice. If you mention a point from the lesson, "
    "quote the lesson's own words."
)


def require_lesson_not_restated(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, a reply that restates the
    lesson card it sits under, unless the learner asked about the lesson."""
    deps = ctx.deps
    if ctx.partial_output or deps is None or getattr(deps, "lesson_restated_retry_used", False):
        return output
    lesson = lesson_shown_this_turn(ctx.messages)
    if not lesson:
        return output
    if _LEARNER_ASKS_ABOUT.search(getattr(deps, "user_message", "") or ""):
        return output
    if not restates_lesson(output, lesson):
        return output
    deps.lesson_restated_retry_used = True
    raise ModelRetry(LESSON_RESTATED_RETRY_INSTRUCTION)


# ---------------------------------------------------------------------------
# Done, while the approval cards are still waiting
# ---------------------------------------------------------------------------
# Support ticket: "All four steps are prepared … Award snapshot saved", with a
# green "All 4 steps completed", while Move files, Add to inbox and Save to
# folder were still waiting for approval and nothing had been saved. A reply
# that says something was saved, added, created or finished while this
# reply's cards wait is sent back once.

_DONE_CLAIMS = [
    re.compile(r"\ball\s+(?:\w+\s+)?(?:steps|tasks|parts|items)\s+(?:are\s+|were\s+|have\s+been\s+)?"
               r"(?:done|complete|completed|finished|prepared|set\s+up|in\s+place)\b", re.IGNORECASE),
    re.compile(r"\b(?:has|have|was|were)\s+(?:now\s+|successfully\s+)?(?:been\s+)?(?:saved|added|created|moved|set\s+up)\b", re.IGNORECASE),
    re.compile(r"\b(?:saved|added|created|moved)\s+(?:it\s+|them\s+)?(?:to|in|into)\s+(?:the\s+|your\s+)?(?:ra\s+)?"
               r"(?:inbox|folder|project|pages?)\b", re.IGNORECASE),
    # A heading-like line: "Award snapshot saved", "✅ Project created".
    re.compile(r"^[^\n.?!]{0,80}\b(?:saved|created|added)\s*[.!:]?\s*$", re.IGNORECASE | re.MULTILINE),
]
_HEDGED = re.compile(
    r"\b(?:once|after|when|until|if)\s+you\b|\bwait(?:s|ing)?\b|\bpending\b|\bapprov(?:e|al|ed)\b|\bconfirm"
    r"|\bnot\s+(?:yet\s+)?(?:been\s+)?(?:saved|added|created|moved|done)\b|\bwill\s+(?:be|save|add|create|move)\b|\bready\s+to\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?", re.MULTILINE)

COMPLETION_RETRY_INSTRUCTION = (
    "Your reply says work is saved, added, created or finished, but these approval cards from this "
    "reply are still waiting for the user: {cards}. Nothing they cover has happened yet. Rewrite the "
    "reply: say what is done, list what is waiting for their approval (by the card's button), and "
    "what will happen after they approve. Do not repeat your previous reply."
)


def claims_done(text: str) -> bool:
    """A sentence that reports a write as done, without saying it waits for approval."""
    for sentence in _SENTENCE.findall(text or ""):
        if _HEDGED.search(sentence):
            continue
        if any(p.search(sentence.strip()) for p in _DONE_CLAIMS):
            return True
    return False


def require_honest_completion(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, "done" while this turn's cards wait."""
    from app.services.chat_tools import _cards_waiting_this_turn

    deps = ctx.deps
    if ctx.partial_output or deps is None or getattr(deps, "completion_claim_retry_used", False):
        return output
    waiting = _cards_waiting_this_turn(deps)
    if not waiting or not claims_done(output):
        return output
    deps.completion_claim_retry_used = True
    labels = sorted({approve_button_label(tool) for tool in waiting})
    raise ModelRetry(COMPLETION_RETRY_INSTRUCTION.format(cards=", ".join(f"“{label}”" for label in labels)))


# An action the user approved this turn that the reply never carried out.
# Support ticket: a Create project card was approved, the model answered "The
# project was created and is ready" without calling the tool, no project
# existed, and the chat's own Activity log said "Approved, not run". The gate
# removes an action from the waiting list only when it actually executes, so
# an approved action still on the list at the end of the reply did not run.

UNRUN_RETRY_INSTRUCTION = (
    "The user approved {cards}, but you have not carried it out: you ended your reply without "
    "calling its tool, so nothing has been created, saved or changed. Call {tools} now with the "
    "same arguments as the preview and confirmed=true. If you cannot, say in one sentence that "
    "it has not been done and why. Never say it was done. Do not repeat your previous reply."
)
# No instruction to call the tool here. A typed message reaches this point
# without having been recognised as an approval (those arrive as a card
# decision), so telling the model to run {tools} would have it act on a
# thank-you, or on a question about something else.
UNRUN_CLAIM_RETRY_INSTRUCTION = (
    "Your reply says something was created, saved, added or finished, but {cards} is still "
    "waiting for approval and has not run. A thank-you, an acknowledgement of your last answer, "
    "or a question about something else is not an approval. Do not call {tools} in this reply. "
    "Say it has not been done yet and point to its card, where the user can approve it. Never "
    "say it was done. Do not repeat your previous reply."
)

# Words too general to tie a reply to one particular waiting action.
_GENERIC_ACTION_WORDS = frozenset({
    "approve", "create", "created", "save", "saved", "add", "added", "update", "updated",
    "delete", "deleted", "remove", "removed", "run", "send", "share", "new", "with", "from",
    "this", "that", "the", "and", "for",
})


def _names_action(text: str, entry: dict) -> bool:
    """Whether *text* is talking about this waiting action.

    A reply can report something as done that has nothing to do with the
    card: "Three files were added last week." while a Create project card
    waits. Only a reply that names what the card would act on (its label or
    its tool, minus the general verbs) is a claim about that card.
    """
    from app.services.chat_tools import approve_button_label

    label = str(entry.get("label") or approve_button_label(str(entry.get("tool") or "")))
    words = {w for w in re.findall(r"[a-z]+", f"{label} {entry.get('tool') or ''}".lower()) if len(w) >= 4}
    specific = words - _GENERIC_ACTION_WORDS
    lowered = (text or "").lower()
    return any(re.search(rf"\b{re.escape(word)}", lowered) for word in (specific or words))


def approved_but_not_run(deps: "AgenticChatDeps | None") -> list[dict]:
    """Waiting-list entries this turn was allowed to run and did not."""
    approved = getattr(deps, "approved_confirmations", None) if deps is not None else None
    if not approved:
        return []
    conversation = getattr(deps, "conversation", None)
    return [
        p for p in (getattr(conversation, "pending_confirmations", None) or [])
        if isinstance(p, dict) and p.get("fp") in approved
    ]


def _unrun_to_report(deps: "AgenticChatDeps | None", text: str) -> list[dict]:
    """The unrun actions *text* has to answer for.

    A card's button is an explicit approval, so the action not running is
    always wrong. A typed message may not have been an approval at all; it
    only counts when the reply goes on to say that action was done: a
    done-claim about something else (an answer to an unrelated question) is
    not about the card.
    """
    unrun = approved_but_not_run(deps)
    if not unrun:
        return []
    mode = getattr(deps, "approval_mode", "none")
    if mode == "card":
        return unrun
    if mode == "typed_single" and claims_done(text):
        return [entry for entry in unrun if _names_action(text, entry)]
    return []


def _card_names(entries: list[dict]) -> str:
    return ", ".join(f"“{p.get('label') or approve_button_label(str(p.get('tool') or ''))}”" for p in entries)


def require_approved_action_ran(ctx: RunContext["AgenticChatDeps"], output: str) -> str:
    """Output validator: send back, once per turn, a reply that skipped the approved action."""
    deps = ctx.deps
    if ctx.partial_output or deps is None or getattr(deps, "unrun_approval_retry_used", False):
        return output
    unrun = _unrun_to_report(deps, output)
    if not unrun:
        return output
    # Once only: a second miss is accepted, and the note below tells the user.
    deps.unrun_approval_retry_used = True
    template = UNRUN_RETRY_INSTRUCTION if getattr(deps, "approval_mode", "none") == "card" else UNRUN_CLAIM_RETRY_INSTRUCTION
    raise ModelRetry(template.format(
        cards=_card_names(unrun), tools=", ".join(sorted({str(p.get("tool") or "the tool") for p in unrun})),
    ))


def unrun_approval_note(text: str, deps: "AgenticChatDeps | None") -> str | None:
    """What to add when the final reply still leaves an approved action unrun.

    The streamed text can't be taken back, so the user is told plainly, and
    told the card is still there to approve.
    """
    unrun = _unrun_to_report(deps, text)
    if not unrun:
        return None
    one = len(unrun) == 1
    return (
        f"\n\n_Note: {_card_names(unrun)} did not run, so nothing was created or changed by "
        f"{'it' if one else 'them'}. {'Its card is' if one else 'Their cards are'} still waiting: "
        f"approve {'it' if one else 'each one'} again to carry {'it' if one else 'them'} out._"
    )
