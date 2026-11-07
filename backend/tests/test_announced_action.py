"""A reply that ends by announcing a step it never took is sent back."""

from types import SimpleNamespace

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.services.approval_claims import announces_unfinished_action, require_announced_action

# The support ticket: chat stopped on this line and no run was ever started.
TICKET_REPLY = (
    "I updated the summary step so it uses the extracted values.\n\n"
    "Running a preview of **NOA Budget & Profile Summary (Data)** on the open document…"
)


@pytest.mark.parametrize("text", [
    TICKET_REPLY,
    "Prepare to run…",
    "Okay, running it now...",
    "Now creating the workflow:",
    "The extraction is set up.\n\nI'll run it now.",
    "Let me prepare the run.",
    "I'm going to start the extraction.",
])
def test_recognizes_a_reply_that_stops_at_an_announcement(text):
    assert announces_unfinished_action(text)


@pytest.mark.parametrize("text", [
    "Shall I run it on the open document?",
    "I'll run it once you approve the card above.",
    "Let me know if you want me to run it.",
    "Running a preview first is a good idea.\n\nThe workflow finished: 12 of 14 fields found.",
    "The workflow is running; results will appear in the panel.",
    "I can create the workflow if you'd like.",
    "",
])
def test_ignores_finished_replies_and_offers(text):
    assert not announces_unfinished_action(text)


def _deps():
    return SimpleNamespace(announced_action_retry_used=False)


def _agent(tool_calls: list[str]):
    """An agent whose model first stops at the ticket's line; on retry it calls the tool."""
    async def model(messages, info: AgentInfo):
        last = messages[-1].parts
        if any(isinstance(p, RetryPromptPart) for p in last):
            yield {0: DeltaToolCall(name="run_workflow", json_args='{"name": "NOA"}')}
        elif any(isinstance(p, ToolReturnPart) for p in last):
            yield "The run is ready for your approval."
        else:
            yield TICKET_REPLY

    agent = Agent(FunctionModel(stream_function=model), deps_type=SimpleNamespace)

    @agent.tool
    def run_workflow(ctx: RunContext[SimpleNamespace], name: str) -> dict:
        tool_calls.append(name)
        return {"needs_confirmation": True}

    agent.output_validator(require_announced_action)
    return agent


async def _run(agent, deps):
    """Drive the agent the way chat_stream does: agent.iter with streamed nodes."""
    async with agent.iter("Fix it and re-run", deps=deps) as run:
        async for node in run:
            if Agent.is_model_request_node(node) or Agent.is_call_tools_node(node):
                async with node.stream(run.ctx) as stream:
                    async for _ in stream:
                        pass
    return run.result.output


@pytest.mark.asyncio
async def test_an_announcement_without_a_tool_call_makes_the_model_call_it():
    calls: list[str] = []
    output = await _run(_agent(calls), _deps())
    assert calls == ["NOA"]
    assert output == "The run is ready for your approval."


@pytest.mark.asyncio
async def test_a_second_miss_is_accepted_rather_than_failing_the_turn():
    async def stubborn(messages, info: AgentInfo):
        yield TICKET_REPLY

    agent = Agent(FunctionModel(stream_function=stubborn), deps_type=SimpleNamespace)
    agent.output_validator(require_announced_action)
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
        deps = SimpleNamespace(
            conversation=SimpleNamespace(pending_confirmations=[]),
            turn_marker=0,
            approval_card_retry_used=False,
            announced_action_retry_used=False,
            queued_user_parts=[],
        )
        await _run(agent, deps)
    finally:
        llm_service._agentic_chat_agent_cache.clear()
    assert len(requests) == 2
    assert "RetryPromptPart" in requests[1]
