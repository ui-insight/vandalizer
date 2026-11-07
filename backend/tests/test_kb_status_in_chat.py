"""Chat reports a knowledge base's real state and never invents "Validated".

Support ticket: asked to "Validate the Subaward Policies knowledge base", chat
replied "Validated — four sources indexed" with no tool call. The KB had never
been validated and its FDP forms page had failed (HTTP 403, 0 chunks).
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import RetryPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.services.approval_claims import claims_validated, require_honest_validation
from app.services.chat_service import (
    _build_kb_status_block,
    _build_manifest_block,
    _kb_status_entries,
    _manifest_status_note,
)

TICKET_REPLY = (
    "Validated — the Subaward Policies page is ready. Four sources indexed:\n"
    "- 2 CFR 200.332\n- FDP subaward forms page\n- Both sample subawards"
)
FDP = {"name": "FDP subaward forms", "status": "error", "error": "HTTP 403 Forbidden: the website refused access"}


# --- what chat is told ----------------------------------------------------------


def test_a_failed_source_is_not_called_still_indexing():
    assert _manifest_status_note(FDP) == " (failed to index: HTTP 403 Forbidden: the website refused access — not searchable)"
    assert _manifest_status_note({"status": "processing"}) == " (still indexing)"
    assert _manifest_status_note({"status": "skipped"}) == " (skipped — not searchable)"
    assert _manifest_status_note({"status": "ready"}) == ""
    block = _build_manifest_block([{"name": "2 CFR 200.332", "status": "ready"}, FDP])
    assert "FDP subaward forms (failed to index" in block
    assert "FDP subaward forms (still indexing)" not in block


def test_the_status_block_gives_ready_failed_and_never_validated():
    block = _build_kb_status_block([{
        "title": "Subaward Policies", "total": 4, "ready": 3,
        "failed": [("FDP subaward forms", "HTTP 403")], "validated_at": None,
    }])
    assert "**Subaward Policies**: 3 of 4 sources ready; 1 not searchable: FDP subaward forms (HTTP 403). Never validated." in block
    assert "Validation tab" in block
    assert "run_validation is for extraction templates only" in block


def test_the_status_block_gives_the_last_validation_date():
    block = _build_kb_status_block([{
        "title": "QA Smoke", "total": 3, "ready": 3, "failed": [],
        "validated_at": datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc),
    }])
    assert "**QA Smoke**: 3 of 3 sources ready. Last validated 2026-10-01." in block


@pytest.mark.asyncio
async def test_status_entries_use_the_kb_counts_and_the_cards_validation_answer():
    kb = SimpleNamespace(uuid="kb-1", title="Subaward Policies", total_sources=4, sources_ready=3)
    manifests = {"kb-1": [{"name": "2 CFR 200.332", "status": "ready"}, FDP]}
    query = SimpleNamespace(to_list=AsyncMock(return_value=[kb]))
    with patch("app.models.knowledge.KnowledgeBase.find", return_value=query), \
         patch("app.routers.knowledge._latest_runs_by_kb", new=AsyncMock(return_value={})):
        entries = await _kb_status_entries([("kb-1", "Subaward Policies")], manifests)
    assert entries == [{
        "title": "Subaward Policies", "total": 4, "ready": 3,
        "failed": [("FDP subaward forms", "HTTP 403 Forbidden: the website refused access")],
        "validated_at": None,
    }]


# --- the reply check --------------------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    (TICKET_REPLY, True),
    ("The Subaward Policies knowledge base is validated and ready.", True),
    ("Subaward Policies has not been validated yet.", False),
    ("This knowledge base has never been validated.", False),
    ("Its sources are unvalidated.", False),
    # About something else: an extraction template validated earlier.
    ("Your NSF budget template was validated last week with a score of 91.", False),
])
def test_claims_validated_about_the_knowledge_base(text, expected):
    assert claims_validated(text, ["Subaward Policies"]) is expected


def _deps(titles=("Subaward Policies",)):
    return SimpleNamespace(unvalidated_kb_titles=list(titles), validation_claim_retry_used=False)


def _agent(replies: list[str], validate_first: bool = False):
    async def model(messages, info: AgentInfo):
        last = messages[-1].parts
        if validate_first and not any(type(p).__name__ == "ToolReturnPart" for m in messages for p in m.parts):
            yield {0: DeltaToolCall(name="run_validation", json_args='{"extraction_set_uuid": "ss"}')}
            return
        retried = any(isinstance(p, RetryPromptPart) for p in last)
        yield replies[1] if retried and len(replies) > 1 else replies[0]

    agent = Agent(FunctionModel(stream_function=model), deps_type=SimpleNamespace)

    @agent.tool
    def run_validation(ctx: RunContext[SimpleNamespace], extraction_set_uuid: str) -> dict:
        return {"score": 91}

    agent.output_validator(require_honest_validation)
    return agent


async def _run(agent, deps):
    async with agent.iter("Validate the Subaward Policies knowledge base", deps=deps) as run:
        async for node in run:
            if Agent.is_model_request_node(node) or Agent.is_call_tools_node(node):
                async with node.stream(run.ctx) as stream:
                    async for _ in stream:
                        pass
    return run.result.output


HONEST = "Subaward Policies hasn't been validated. 3 of 4 sources are ready; open its Validation tab to run one."


@pytest.mark.asyncio
async def test_an_invented_validated_is_sent_back():
    assert await _run(_agent([TICKET_REPLY, HONEST]), _deps()) == HONEST


@pytest.mark.asyncio
async def test_a_validated_knowledge_base_is_left_alone():
    assert await _run(_agent([TICKET_REPLY, HONEST]), _deps(titles=())) == TICKET_REPLY


@pytest.mark.asyncio
async def test_a_validation_that_ran_this_turn_is_left_alone():
    reply = "Validated: the Subaward Policies extraction scored 91."
    assert await _run(_agent([reply, HONEST], validate_first=True), _deps()) == reply


@pytest.mark.asyncio
async def test_a_second_miss_is_accepted():
    assert await _run(_agent([TICKET_REPLY]), _deps()) == TICKET_REPLY


@pytest.mark.asyncio
async def test_the_chat_agent_sends_such_a_reply_back(monkeypatch):
    from app.services import llm_service

    requests: list[list[str]] = []

    async def model(messages, info: AgentInfo):
        requests.append([type(p).__name__ for p in messages[-1].parts])
        yield TICKET_REPLY

    monkeypatch.setattr(llm_service, "get_agent_model", lambda *a, **k: FunctionModel(stream_function=model))
    llm_service._agentic_chat_agent_cache.clear()
    try:
        agent = llm_service.create_agentic_chat_agent("unit-test-model", system_config_doc={})
        deps = SimpleNamespace(
            conversation=SimpleNamespace(pending_confirmations=[]), turn_marker=0,
            approval_card_retry_used=False, announced_action_retry_used=False,
            queued_user_parts=[], **vars(_deps()),
        )
        await _run(agent, deps)
    finally:
        llm_service._agentic_chat_agent_cache.clear()
    assert len(requests) == 2
    assert "RetryPromptPart" in requests[1]


@pytest.mark.asyncio
async def test_the_manifest_carries_a_failed_sources_reason():
    from app.services import knowledge_service

    sources = [
        SimpleNamespace(uuid="s1", custom_name=None, source_type="url", url_title="FDP subaward forms",
                        url="https://thefdp.org/forms", document_uuid=None, status="error",
                        error_message="HTTP 403 Forbidden"),
        SimpleNamespace(uuid="s2", custom_name="2 CFR 200.332", source_type="url", url_title=None,
                        url="https://ecfr.gov", document_uuid=None, status="ready", error_message=None),
    ]
    with patch.object(knowledge_service, "get_kb_sources", new=AsyncMock(return_value=sources)), \
         patch.object(knowledge_service, "resolve_document_titles", new=AsyncMock(return_value={})):
        manifest = await knowledge_service.get_kb_manifest("kb-1")
    assert manifest[0]["error"] == "HTTP 403 Forbidden"
    assert manifest[1]["error"] == ""


@pytest.mark.asyncio
async def test_the_manifest_carries_a_held_pages_reason():
    # #1025: a held page waits on the user; its reason is why it wasn't added.
    from app.services import knowledge_service

    reason = "This page has text hidden from readers that addresses an AI system."
    sources = [
        SimpleNamespace(uuid="s1", custom_name=None, source_type="url", url_title="FCOI FAQ",
                        url="https://example.edu/fcoi", document_uuid=None, status="held",
                        error_message=reason, chunk_count=0),
    ]
    with patch.object(knowledge_service, "get_kb_sources", new=AsyncMock(return_value=sources)), \
         patch.object(knowledge_service, "resolve_document_titles", new=AsyncMock(return_value={})):
        manifest = await knowledge_service.get_kb_manifest("kb-1")
    assert manifest[0]["status"] == "held"
    assert manifest[0]["error"] == reason
