"""A reply that points at an approval button no tool prepared is sent back."""

from types import SimpleNamespace

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.services.approval_claims import (
    UNPREPARED_CARD_NOTE,
    approval_card_is_live,
    promises_approval_button,
    require_approval_card,
    unprepared_card_note,
)

# The support ticket's reply, verbatim apart from the workflow description.
TICKET_REPLY = (
    "I've prepared a new **“Multi-Agency Subaward Compliance Scan”** workflow.\n\n"
    "[Create workflow]—click the **Create workflow** button to confirm."
)


@pytest.mark.parametrize("text", [
    TICKET_REPLY,
    "Click **Run workflow** when you're ready.",
    "Press the Confirm button to proceed.",
    "Use the approval card below to create it.",
    "Hit “Approve create knowledge base” and I'll build it.",
    # Second support ticket (kimi-k3), verbatim.
    "I've prepared the workflow — review the card and use **Create workflow** if it looks right:",
    "Review the workflow card, then approve it.",
])
def test_recognizes_a_promised_approval_button(text):
    assert promises_approval_button(text)


@pytest.mark.parametrize("text", [
    "Go to Files → Upload button, then pick your PDF.",
    "In the Validate tab, click **Add Documents** and choose the award.",
    "The workflow was created. Open it from the Library.",
    "[Create workflow](https://example.org/docs) explains the editor.",
    "[ACTION:build-workflow]Build a workflow[/ACTION]",
    "Want me to create the workflow?",
    "See the run card below for the results.",
    "Use approved budget templates when you can.",
    "You can use the confirmation from the sponsor.",
])
def test_ignores_other_buttons_and_plain_offers(text):
    assert not promises_approval_button(text)


def _deps(*turns, marker=10):
    conversation = SimpleNamespace(pending_confirmations=[{"fp": f"f{t}", "turn": t} for t in turns])
    return SimpleNamespace(conversation=conversation, turn_marker=marker, approval_card_retry_used=False)


def test_a_card_from_this_turn_or_the_last_is_live():
    assert approval_card_is_live(_deps(10))
    assert approval_card_is_live(_deps(8))
    assert not approval_card_is_live(_deps(4))
    assert not approval_card_is_live(_deps())


def _agent(tool_calls: list[str]):
    """An agent whose model first writes the ticket's reply; on retry it calls the tool."""

    async def model(messages, info: AgentInfo):
        last = messages[-1].parts
        if any(isinstance(p, RetryPromptPart) for p in last):
            yield {0: DeltaToolCall(name="create_workflow", json_args='{"name": "Scan"}')}
        elif any(isinstance(p, ToolReturnPart) for p in last):
            yield "I've prepared the workflow for your approval."
        else:
            yield TICKET_REPLY

    agent = Agent(FunctionModel(stream_function=model), deps_type=SimpleNamespace)

    @agent.tool
    def create_workflow(ctx: RunContext[SimpleNamespace], name: str) -> dict:
        tool_calls.append(name)
        ctx.deps.conversation.pending_confirmations.append({"fp": "wf", "turn": ctx.deps.turn_marker})
        return {"needs_confirmation": True}

    agent.output_validator(require_approval_card)
    return agent


async def _run(agent, deps):
    """Drive the agent the way chat_stream does: agent.iter with streamed nodes."""
    async with agent.iter("Update this workflow", deps=deps) as run:
        async for node in run:
            if Agent.is_model_request_node(node) or Agent.is_call_tools_node(node):
                async with node.stream(run.ctx) as stream:
                    async for _ in stream:
                        pass
    return run.result.output


@pytest.mark.asyncio
async def test_a_promised_button_without_a_card_makes_the_model_call_the_tool():
    calls: list[str] = []
    output = await _run(_agent(calls), _deps())
    assert calls == ["Scan"]
    assert output == "I've prepared the workflow for your approval."


@pytest.mark.asyncio
async def test_a_live_card_is_left_alone():
    calls: list[str] = []
    output = await _run(_agent(calls), _deps(10))
    assert calls == []
    assert output == TICKET_REPLY


@pytest.mark.asyncio
async def test_a_second_miss_is_accepted_rather_than_failing_the_turn():
    async def stubborn(messages, info: AgentInfo):
        yield TICKET_REPLY

    agent = Agent(FunctionModel(stream_function=stubborn), deps_type=SimpleNamespace)
    agent.output_validator(require_approval_card)
    assert await _run(agent, _deps()) == TICKET_REPLY


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
        deps = _deps()
        deps.queued_user_parts = []
        await _run(agent, deps)
    finally:
        llm_service._agentic_chat_agent_cache.clear()
    assert len(requests) == 2
    assert "RetryPromptPart" in requests[1]


def test_a_reply_still_pointing_at_a_missing_card_gets_a_plain_note():
    reply = "I've prepared the workflow — review the card and use **Create workflow** if it looks right:"
    assert unprepared_card_note(reply, _deps()) == UNPREPARED_CARD_NOTE
    assert "nothing has been created" in UNPREPARED_CARD_NOTE


def test_no_note_when_the_card_exists_or_nothing_was_promised():
    reply = "Review the card and use **Create workflow** if it looks right."
    assert unprepared_card_note(reply, _deps(10)) is None
    assert unprepared_card_note("Want me to build that workflow?", _deps()) is None
    assert unprepared_card_note(reply, None) is None
