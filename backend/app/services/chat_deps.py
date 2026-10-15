"""Dependency dataclass for agentic chat tools."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from app.models.user import User
from app.services.access_control import TeamAccessContext

if TYPE_CHECKING:
    from app.models.chat import ChatConversation


@dataclass
class AgenticChatDeps:
    """Dependencies injected into agentic chat tools via pydantic-ai RunContext.

    Constructed once per chat request in the router, then passed through
    ``agent.iter(… deps=deps)`` so every tool call receives the same
    pre-authorised context.
    """

    user: User
    user_id: str
    team_id: Optional[str]
    team_access: TeamAccessContext
    organization_id: Optional[str]
    system_config_doc: dict
    model_name: str
    context_document_uuids: list[str] = field(default_factory=list)
    active_kb_uuid: Optional[str] = None
    # The project the user is chatting "inside", if any. Project tools
    # (run_pin_on_project, list_project_documents, pin/unpin, set_status) resolve
    # the project from here. Existing tools ignore it — they range the whole
    # workspace regardless, by design.
    active_project_uuid: Optional[str] = None

    # Sidecar for quality metadata — tools write here keyed by tool_call_id,
    # and the streaming layer pops entries when emitting tool_result events.
    # This keeps quality signals out of the LLM context entirely.
    quality_annotations: dict[str, dict] = field(default_factory=dict)

    # Sidecar for KB citations — search_knowledge_base writes Citation-shaped
    # dicts here keyed by tool_call_id; the streaming layer pops them, emits a
    # 'sources' chunk, and persists them on the assistant message. Same
    # rationale as quality_annotations: citation plumbing (chunk ids, scores)
    # stays out of the LLM context.
    citation_annotations: dict[str, list[dict]] = field(default_factory=dict)

    # The live conversation for this turn + a monotonic turn marker
    # (len(messages) captured at turn start). Write tools read/write
    # ``conversation.pending_confirmations`` and compare against ``turn_marker``
    # to enforce the preview→confirm handshake across a real user turn, so a
    # prompt-injected document or KB snippet cannot drive a mutation by passing
    # confirmed=true within a single turn. See chat_tools._confirm_gate.
    conversation: Optional["ChatConversation"] = None
    turn_marker: int = 0

    # Live task plan for this turn (uplift plan Phase 8). update_plan writes
    # the full validated list here; the streaming layer emits it as a
    # 'plan_update' chunk and _finalize persists it on the conversation so a
    # follow-up turn resumes the same checklist. None = no plan this turn.
    plan_state: Optional[list[dict]] = None

    # Mid-run message queue hand-off (uplift plan Phase 10). chat_stream
    # drains the conversation's queued messages before each model request
    # and stages them here; the agent's history processor
    # (llm_service._inject_queued_user_parts) folds them into the outgoing
    # request as user parts and clears the list.
    queued_user_parts: list[str] = field(default_factory=list)

    # Set once the reply was sent back for pointing at an approval button no
    # tool prepared (approval_claims.require_approval_card), so a second miss
    # is accepted instead of failing the turn.
    approval_card_retry_used: bool = False

    # The same once-only flag for a reply that ends by announcing a step it
    # never took (approval_claims.require_announced_action).
    announced_action_retry_used: bool = False

    # Attached knowledge bases that have never been validated, and the
    # once-only flag for sending back a reply that calls one validated
    # (approval_claims.require_honest_validation).
    unvalidated_kb_titles: list[str] = field(default_factory=list)
    validation_claim_retry_used: bool = False

    # Set once require_available_nodes has sent back a reply describing an
    # unavailable workflow node, so the retry happens at most once per turn.
    unavailable_node_retry_used: bool = False

    # The user's own words this turn, without the reminder and document blocks
    # chat_service wraps around them; and the once-only flag for
    # approval_claims.require_learner_route.
    user_message: str = ""
    learner_route_retry_used: bool = False
    # Once-only flag for approval_claims.require_course_read.
    course_entry_retry_used: bool = False
    # Once-only flag for approval_claims.require_lessons_in_order.
    lesson_skip_retry_used: bool = False
    # Once-only flag for approval_claims.require_lesson_not_restated.
    lesson_restated_retry_used: bool = False
