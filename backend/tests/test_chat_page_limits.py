"""Large Pages stop with a recoverable message, before tools or model retries."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import IncompleteToolCall, UnexpectedModelBehavior
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.services import artifacts, chat_artifact_tools
from app.services.approval_claims import require_announced_action, require_approval_card
from app.services.chat_service import _classify_stream_error
from app.services.page_authoring import declares_page_too_large, requests_page
from tests import test_chat_output

chat_harness = test_chat_output.chat_harness


REQUEST = "Make a page summarizing this whole spreadsheet with a static table of every row. No scripts."
MESSAGE = artifacts.PAGE_TOO_LARGE_MESSAGE


def assert_size_failure(chunks, harness):
    assert [c["content"] for c in chunks if c["kind"] == "error"] == [MESSAGE]
    assert not [c for c in chunks if c["kind"] == "text"]
    harness.failed.assert_awaited_once()
    assert MESSAGE in harness.failed.call_args.args[1]
    harness.finalize.assert_not_awaited()


@pytest.mark.parametrize("disconnect_after_limit", [False, True])
@pytest.mark.parametrize("delta", [
    {"content": "I will verify every displayed value before asking you to save."},
    {"reasoning_content": "PRIVATE reasoning consumed the output allowance"},
    {"tool_calls": [{"index": 0, "id": "page", "type": "function", "function": {
        "name": "create_html_artifact", "arguments": '{"html":"<table>',
    }}]},
    {"tool_calls": [{"index": 0, "id": "page", "type": "function", "function": {
        "name": "create_html_artifact", "arguments": '{"html":"<table>incomplete</table>"}',
    }}]},
])
async def test_openai_compatible_output_cap_before_and_during_page_tool(chat_harness, delta, disconnect_after_limit):
    """Exercise actual provider SSE parsing, not just a hand-made ModelResponse."""
    requests = []
    execute = AsyncMock(return_value={"preview_id": "must-not-exist"})

    class InterruptedStream(httpx.AsyncByteStream):
        def __init__(self, body):
            self.body = body

        async def __aiter__(self):
            yield self.body.encode()
            raise httpx.RemoteProtocolError("peer closed connection after output limit")

    def serve(request):
        requests.append(request)
        chunks = [
            {"id": "test", "object": "chat.completion.chunk", "created": 1, "model": "kimi-k3",
             "choices": [{"index": 0, "delta": change, "finish_reason": finish}]}
            for change, finish in [(delta, None), ({}, "length")]
        ]
        body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
        if disconnect_after_limit:
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=InterruptedStream(body))
        body += "data: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    async def create_html_artifact(html: str):
        return await execute(html)

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        model = OpenAIChatModel("kimi-k3", provider=OpenAIProvider(
            api_key="test", base_url="https://model.test/v1", http_client=client,
        ))
        chunks = await chat_harness.run(Agent(model, tools=[create_html_artifact]), message=REQUEST)

    assert_size_failure(chunks, chat_harness)
    execute.assert_not_awaited()
    assert len(requests) == 1


@pytest.mark.parametrize("exc", [
    IncompleteToolCall("private provider details"),
    ExceptionGroup("tool tasks", [artifacts.PageTooLargeError("private details")]),
    ExceptionGroup("outer", [ExceptionGroup("inner", [IncompleteToolCall("private details")])]),
    UnexpectedModelBehavior("Model token limit (8192) exceeded before any response was generated. Private details."),
])
def test_wrapped_size_failures_have_the_same_public_message(exc):
    assert _classify_stream_error(exc, preparing_page=True) == ("warning", MESSAGE)


def test_cause_wrapped_size_failure():
    error = RuntimeError("SDK wrapper")
    error.__cause__ = IncompleteToolCall("private details")
    assert _classify_stream_error(error, preparing_page=True) == ("warning", MESSAGE)


@pytest.mark.parametrize("exc", [
    ValueError("unrelated bug"),
    UnexpectedModelBehavior("Exceeded maximum retries for tool arguments"),
    ExceptionGroup("mixed", [IncompleteToolCall("size"), ValueError("unrelated bug")]),
])
def test_page_request_does_not_hide_unrelated_failures(exc):
    assert _classify_stream_error(exc, preparing_page=True)[0] == "error"


@pytest.mark.parametrize("with_tool", [False, True])
async def test_size_refusal_stops_before_a_default_preview_or_validator_retry(chat_harness, with_tool):
    calls = []
    requests = []

    async def create_html_artifact(html: str):
        calls.append(html)
        return {"preview_id": "must-not-exist"}

    async def respond(messages, info):
        requests.append(messages)
        yield (
            "The Page is too large to create in full.\n\n"
            "Choose fewer rows or split it into Pages.\n\n"
            "I'm preparing the Page preview with all six sheets using the default interpretation…"
        )
        if with_tool:
            yield {0: DeltaToolCall(name="create_html_artifact", json_args='{"html":"<p>All sheets</p>"}')}

    agent = Agent(FunctionModel(stream_function=respond), tools=[create_html_artifact])
    agent.output_validator(require_approval_card)
    agent.output_validator(require_announced_action)
    chunks = await chat_harness.run(agent, message=REQUEST)
    assert_size_failure(chunks, chat_harness)
    assert calls == []
    assert len(requests) == 1


@pytest.mark.parametrize("html", ["é" * 140000, "x" * (artifacts.MAX_HTML_BYTES - 1)])
async def test_server_page_limit_ends_turn_without_model_regeneration(chat_harness, monkeypatch, html):
    requests = []
    prepare = AsyncMock()

    async def validate(fn, *args):
        # Run real sanitization (including its rendered-size check) before storage.
        artifacts.clean_html(args[3], args[2])
        await prepare()
        raise AssertionError("Oversized page reached persistence")

    monkeypatch.setattr(chat_artifact_tools, "_call", validate)

    async def respond(messages, info):
        requests.append(messages)
        yield {0: DeltaToolCall(name="create_html_artifact", json_args=json.dumps({
            "title": "Every row", "html": html,
        }))}

    agent = Agent(FunctionModel(stream_function=respond), tools=[chat_artifact_tools.create_html_artifact])
    chunks = await chat_harness.run(agent, message=REQUEST)
    assert_size_failure(chunks, chat_harness)
    assert len(requests) == 1
    prepare.assert_not_awaited()


async def test_small_page_still_reaches_preview(chat_harness):
    calls = []

    async def create_html_artifact(html: str):
        calls.append(html)
        return {"preview_id": "small", "needs_confirmation": True}

    async def respond(messages, info):
        if not calls:
            yield {0: DeltaToolCall(name="create_html_artifact", json_args='{"html":"<table><tr><td>1</td></tr></table>"}')}
        else:
            yield "The Page preview is ready for review."

    chunks = await chat_harness.run(Agent(FunctionModel(stream_function=respond), tools=[create_html_artifact]), message=REQUEST)
    assert not [c for c in chunks if c["kind"] == "error"]
    assert len(calls) == 1
    assert [c["content"]["preview_id"] for c in chunks if c["kind"] == "tool_result"] == ["small"]
    chat_harness.finalize.assert_awaited_once()


async def test_verification_promise_cannot_leave_user_waiting(chat_harness):
    requests = []

    async def respond(messages, info):
        requests.append(messages)
        yield "I will verify every displayed value before asking you to save."

    agent = Agent(FunctionModel(stream_function=respond))
    agent.output_validator(require_announced_action)
    chunks = await chat_harness.run(agent, message=REQUEST)
    assert len(requests) == 2
    answer = "".join(c["content"] for c in chunks if c["kind"] == "text")
    assert "couldn't finish preparing the Page preview" in answer
    assert "No further work is running" in answer
    assert "fewer rows or tabs" in chat_harness.finalize.call_args.args[1]


async def test_discussing_size_limits_is_not_a_failed_page_request(chat_harness):
    answer = "The Page is too large to create in full. This is what that error means."

    async def respond(messages, info):
        yield answer

    chunks = await chat_harness.run(Agent(FunctionModel(stream_function=respond)), message="Explain the size error.")
    assert not [c for c in chunks if c["kind"] == "error"]
    assert chat_harness.finalize.call_args.args[1] == answer


@pytest.mark.parametrize("text", [
    "The Page is too large to create in full.",
    "**This page is too large**; try fewer rows.",
    "The requested Page would be too big. Which tabs should I include?",
])
def test_affirmative_size_refusal(text):
    assert declares_page_too_large(text)


@pytest.mark.parametrize("text", [
    "If the page is too large, try fewer rows.",
    "The Page is not too large.",
    "The Page was too large, so I prepared the smaller scope you selected.",
    "A web page is too large for the browser.",
    "The source says: 'This page is too large'.",
])
def test_size_refusal_does_not_match_conditions_or_negations(text):
    assert not declares_page_too_large(text)


def test_page_request_detected_without_a_tool_name():
    assert requests_page(REQUEST)
    assert requests_page("Create a Page from the attached spreadsheet now.")
    assert not requests_page("Summarize page 6 of the document.")
    assert not requests_page("Create a summary of page 3 with the dates.")
    assert not requests_page("Make a table of the deadlines on pages 4-6.")
