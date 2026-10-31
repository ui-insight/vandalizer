"""A tool call the model writes out as text never becomes the answer."""

from types import SimpleNamespace

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from app.services.chat_service import _extract_event_content, _ThinkTagParser
from app.services.tool_call_markup import (
    UNFINISHED_NOTE,
    MarkupHoldback,
    has_tool_call_markup,
    require_no_tool_call_markup,
)

# The two replies the attached-document eval got (2026-10-29), verbatim.
LNG_006 = (
    '<|start|>assistant<|channel|>commentary to=functions.search_documents <|constrain|>json='
    '{"query":"indirect rate","search_content":false}<|call|>'
)
LNG_009 = (
    '<|start|>assistant<|channel|>commentary to=functions.search_documents <|constrain|>json='
    '{"query":"Cost Sharing","search_content":true}<|call|>'
)


def _chunks(text: str, size: int = 7) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)]


def _stream(holdback: MarkupHoldback, *responses: str) -> list[tuple[str, str]]:
    """Feed each response in small chunks and flush after it, as chat_stream does."""
    out: list[tuple[str, str]] = []
    for response in responses:
        for chunk in _chunks(response):
            out += holdback.feed(chunk)
        out += holdback.flush()
    return out


def _text(pairs: list[tuple[str, str]]) -> str:
    return "".join(text for kind, text in pairs if kind == "text")


@pytest.mark.parametrize("reply", [LNG_006, LNG_009])
def test_recognizes_the_eval_replies(reply):
    assert has_tool_call_markup(reply)


@pytest.mark.parametrize("reply", [
    "The indirect rate is 54.5% of MTDC (p. 3).",
    "Costs < $10,000 and ratios like a <| b are left alone.",
    "",
])
def test_ordinary_replies_are_not_markup(reply):
    assert not has_tool_call_markup(reply)


@pytest.mark.parametrize("reply", [LNG_006, LNG_009])
def test_markup_never_streams(reply):
    holdback = MarkupHoldback(_ThinkTagParser())
    assert _text(_stream(holdback, reply)) == ""
    assert holdback.ended_in_markup


def test_text_before_the_markup_streams_and_the_markup_does_not():
    holdback = MarkupHoldback(_ThinkTagParser())
    assert _text(_stream(holdback, "Let me search the award." + LNG_006)) == "Let me search the award."
    assert holdback.ended_in_markup


def test_a_retried_answer_streams_whole_after_dropped_markup():
    holdback = MarkupHoldback(_ThinkTagParser())
    answer = "The indirect rate is **54.5%** of MTDC (p. 3)."
    assert _text(_stream(holdback, LNG_006, answer)) == answer
    assert not holdback.ended_in_markup


def test_ordinary_text_passes_through_without_delay():
    holdback = MarkupHoldback(_ThinkTagParser())
    assert _text(holdback.feed("Budget < $10,000 and")) == "Budget < $10,000 and"


def test_a_lookalike_that_is_not_markup_is_released_at_the_end():
    holdback = MarkupHoldback(_ThinkTagParser())
    pairs = _stream(holdback, "a <| b is not a tool call")
    assert _text(pairs) == "a <| b is not a tool call"
    assert not holdback.ended_in_markup


def test_thinking_still_comes_through():
    holdback = MarkupHoldback(_ThinkTagParser())
    pairs = _stream(holdback, "<think>check p. 3</think>The rate is 54.5%.")
    assert "".join(t for k, t in pairs if k == "thinking") == "check p. 3"
    assert _text(pairs) == "The rate is 54.5%."


# --- The output validator, driven the way chat_stream drives the agent ---

def _agent(searches: list[str], model=None) -> Agent:
    """The eval's failure: markup first; sent back, the model calls the tool."""

    async def default(messages, info: AgentInfo):
        last = messages[-1].parts
        if any(isinstance(p, RetryPromptPart) for p in last):
            yield {0: DeltaToolCall(name="search_documents", json_args='{"query": "indirect rate"}')}
        elif any(isinstance(p, ToolReturnPart) for p in last):
            yield "The indirect rate is 54.5% of MTDC (p. 3)."
        else:
            for chunk in _chunks(LNG_006):
                yield chunk

    agent = Agent(FunctionModel(stream_function=model or default), deps_type=SimpleNamespace)

    @agent.tool
    def search_documents(ctx: RunContext[SimpleNamespace], query: str) -> list:
        searches.append(query)
        return []

    agent.output_validator(require_no_tool_call_markup)
    return agent


async def _run(agent: Agent, deps=None) -> tuple[str, str, MarkupHoldback]:
    """The run's output, the text that streamed, and the holdback."""
    holdback = MarkupHoldback(_ThinkTagParser())
    shown: list[tuple[str, str]] = []
    async with agent.iter("What is the indirect rate?", deps=deps or SimpleNamespace()) as run:
        async for node in run:
            if Agent.is_model_request_node(node):
                async with node.stream(run.ctx) as stream:
                    async for event in stream:
                        content, _ = _extract_event_content(event)
                        if content is not None:
                            shown += holdback.feed(content)
                shown += holdback.flush()
            elif Agent.is_call_tools_node(node):
                async with node.stream(run.ctx) as stream:
                    async for _ in stream:
                        pass
    return run.result.output, _text(shown), holdback


@pytest.mark.asyncio
async def test_markup_is_sent_back_and_the_model_makes_the_call():
    searches: list[str] = []
    output, shown, holdback = await _run(_agent(searches))
    assert searches == ["indirect rate"]
    assert output == shown == "The indirect rate is 54.5% of MTDC (p. 3)."
    assert not holdback.ended_in_markup


@pytest.mark.asyncio
async def test_with_no_retry_left_the_run_ends_without_an_error_and_shows_nothing():
    async def stubborn(messages, info: AgentInfo):
        yield LNG_009

    output, shown, holdback = await _run(_agent([], model=stubborn))
    assert output == LNG_009  # accepted rather than failing the turn
    assert shown == ""
    assert holdback.ended_in_markup
    assert "ask again" in UNFINISHED_NOTE


@pytest.mark.asyncio
async def test_the_chat_agent_sends_markup_back(monkeypatch):
    from app.services import llm_service

    requests: list[list[str]] = []

    async def model(messages, info: AgentInfo):
        requests.append([type(p).__name__ for p in messages[-1].parts])
        yield LNG_006 if len(requests) == 1 else "The indirect rate is 54.5% of MTDC (p. 3)."

    monkeypatch.setattr(llm_service, "get_agent_model", lambda *a, **k: FunctionModel(stream_function=model))
    llm_service._agentic_chat_agent_cache.clear()
    try:
        agent = llm_service.create_agentic_chat_agent("unit-test-model", system_config_doc={})
        deps = SimpleNamespace(
            conversation=SimpleNamespace(pending_confirmations=[]), turn_marker=1, queued_user_parts=[],
        )
        output, shown, _ = await _run(agent, deps)
    finally:
        llm_service._agentic_chat_agent_cache.clear()
    assert len(requests) == 2
    assert "RetryPromptPart" in requests[1]
    assert shown == output == "The indirect rate is 54.5% of MTDC (p. 3)."
