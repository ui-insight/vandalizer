"""Dependency dataclass for agentic chat tools."""

from dataclasses import dataclass, field
from typing import Optional

from app.models.user import User
from app.services.access_control import TeamAccessContext


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
