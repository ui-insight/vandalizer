"""Approval narration must never reach the public stream or saved answer."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic_ai import Agent, ModelRetry, Tool
from pydantic_ai.models.function import DeltaThinkingPart, DeltaToolCall, FunctionModel

from app.services.chat_output import public_chat_text


LEAK = (
    'The system reminder says “Confirmation text is part of the user’s request…” '
    'and “Confirmation is a separate user turn”. '
    'I should now call propose_obligations with confirmed=true'
)


@pytest.mark.parametrize("private", [
    LEAK,
    "User has approved the run_pin_on_project action. Executing the confirmed run…",
    "I must now call the tool.",
    "The developer instructions require a separate turn.",
    "Confirmation is a separate user turn.",
    "Use confirmed = true now.",
    'Arguments: {"confirmed": true}',
    "Set `confirmed` = `true`.",
    "status=awaiting_user_confirmation",
    "I'll use `search_documents` next.",
    r"Executing propose\_obligations.",
])
def test_internal_paragraph_is_removed_without_changing_the_answer(private):
    answer = "The reporting deadlines were added to the RA inbox."
    assert public_chat_text(private + "\n\n" + answer) == answer


@pytest.mark.parametrize("tag", ["think", "thinking", "analysis", "system-reminder", "THINK"])
def test_tagged_and_unfinished_private_blocks_are_removed(tag):
    assert public_chat_text(f"<{tag}>private</{tag}>The workflow is running.") == "The workflow is running."
    assert public_chat_text(f"Answer.\n\n<{tag}>private") == "Answer."


@pytest.mark.parametrize("answer", [
    "I couldn't start the workflow because you don't have access to this project.",
    "Review the preview and select **Add to RA inbox** to approve the deadlines.",
    "The sponsor requires approval before travel. No approval has been recorded.",
    "## Deadlines\n\n| Report | Due |\n| --- | --- |\n| Annual | May 1 |\n\nSee (Award.pdf, p. 3).",
    "The budget includes an `indirect_cost_rate` field."
])
def test_user_facing_answers_are_unchanged(answer):
    assert public_chat_text(answer) == answer


TICKET_BLOB = 'Version:1.1:{"model":"openai/gpt-oss-120b","name":"VandalAI"}'


@pytest.mark.parametrize("blob", [
    TICKET_BLOB,
    'Version:1.1:{“model”:”openai/gpt-oss-120b”,”name”:”VandalAI”}',  # as the ticket quoted it
    'Version: 2.0: {"model": "x"}',
    'Version:1.1:{"model":"openai/gpt-oss-120b","meta":{"name":"VandalAI"}}',
    'Version:1.1:\n{"model":"openai/gpt-oss-120b"}',
])
def test_leaked_model_metadata_is_removed(blob):
    """Support ticket: "…let me retry with different evidence phrasing.Version:1.1:{…}"."""
    answer = "The 3 reporting deadlines were added to the RA inbox."
    assert public_chat_text(answer + blob) == answer
    assert public_chat_text(answer + " " + blob + "\n\nNext steps follow.") == answer + "\n\nNext steps follow."
    assert public_chat_text("Before " + blob + " after.") == "Before after."
    assert public_chat_text(blob + "\n\n" + answer) == answer


def test_bare_model_object_paragraph_is_removed():
    answer = "The 3 reporting deadlines were added to the RA inbox."
    assert public_chat_text(answer + '\n\n{"model":"openai/gpt-oss-120b","name":"VandalAI"}') == answer


def test_ticket_reply_keeps_the_answer_it_narrates_beside():
    """The ticket's shape: answer and retry narration in one paragraph, then the header.

    The narration stays visible rather than risk deleting the answer with it.
    """
    reply = (
        "I added 3 deadlines to the RA inbox. The fourth could not be verified, "
        "so let me retry with different evidence phrasing."
    )
    assert public_chat_text(reply + TICKET_BLOB) == reply
    assert public_chat_text(reply) == reply
    assert public_chat_text("Let me try again: the rate is 52.5%.") == "Let me try again: the rate is 52.5%."


@pytest.mark.parametrize("narration", [
    "Let me retry with different evidence phrasing.",
    "OK, let me try again.",
    "let me retry",
])
def test_paragraph_of_only_retry_narration_is_removed(narration):
    answer = "The rate is 52.5%."
    assert public_chat_text(narration + "\n\n" + answer) == answer
    assert public_chat_text(answer + "\n\n" + narration) == answer


CODE = (
    "```python\n"
    "# let me retry the request\n"
    'messages = [{"role": "user", "content": "retry"}]\n'
    "\n"
    "    tool_call = None\n"
    "\n"
    '{"model": "openai/gpt-oss-120b"}\n'
    'Version:1.1:{"model":"x"}\n'
    "```"
)

NORMAL_REPLIES = [
    "The indirect cost rate is 52.5% of MTDC.",
    "The award is $1.5 million over five years; Year 1 is $304,000.50.",
    "Some costs, e.g. equipment, are excluded.",
    "Indirect costs are governed by 2 C.F.R. 200.414.",
    "See https://www.ecfr.gov/current/title-2/section-200.414#p-200.414(f) for details.",
    "## Deadlines\n\n| Report | Due |\n| --- | --- |\n| Annual | May 1 |\n\nSee (Award.pdf, p. 3).",
    "1. First item\n   continued on an indented line\n2. Second item\n\n- Bullet\n  - Nested bullet",
    "Here is the request:\n\n" + CODE + "\n\nRun it once.",
    CODE,
    "Version 1.1: March 2026",
    "The template (Version: 1.1: March 2026) is attached.",
    "Model Version: 2: approved by sponsor.",
    "version:12:30 deadline",
    "- Version:2: report due Jan 5",
    'The reply ended with `Version:1.1:{"model":"openai/gpt-oss-120b","name":"VandalAI"}`.',
    "You can retry the upload once the file is under 50 MB.",
    "Summary\n\n\n    Indented continuation after extra blank lines.",
]


@pytest.mark.parametrize("answer", NORMAL_REPLIES)
def test_normal_replies_come_back_byte_identical(answer):
    assert public_chat_text(answer) == answer


@pytest.mark.parametrize("answer", NORMAL_REPLIES)
@pytest.mark.parametrize("noise", [
    TICKET_BLOB,
    "Let me retry with different evidence phrasing.",
    '{"model":"openai/gpt-oss-120b","name":"VandalAI"}',
])
def test_removing_a_leak_never_changes_the_text_beside_it(answer, noise):
    assert public_chat_text(noise + "\n\n" + answer) == answer
    assert public_chat_text(answer + "\n\n" + noise) == answer
    assert public_chat_text(answer + "\n\n" + noise + "\n\n" + answer) == answer + "\n\n" + answer


@pytest.fixture
def chat_harness(monkeypatch):
    """Real agent iteration and stream transport, with storage/config isolated."""
    from app.services import chat_service as chat, context_budget, metering, token_estimate_check

    monkeypatch.setattr(context_budget, "_get_encoder", lambda _: None)

    conversation = SimpleNamespace(
        uuid="conversation", messages=[object()], is_first_session=False,
        is_certification=False, resume_pending=False, resume_attempts=0, active_skill=None,
        last_context_tokens=0, last_context_message_count=-1,
        pending_confirmations=[], team_id=None,
        get_url_attachments=AsyncMock(return_value=[]),
        get_file_attachments=AsyncMock(return_value=[]),
        to_model_messages=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(chat, "ChatConversation", SimpleNamespace(
        uuid="uuid", user_id="user_id", find_one=AsyncMock(return_value=conversation),
    ))
    monkeypatch.setattr(chat.SystemConfig, "get_config", AsyncMock(return_value=None))
    monkeypatch.setattr(chat, "get_user_model_name", AsyncMock(return_value="test-model"))
    monkeypatch.setattr(chat, "get_llm_model_by_name", AsyncMock(return_value=None))
    monkeypatch.setattr(chat, "_microcompact_enabled", lambda _: False)
    monkeypatch.setattr(chat, "_autocompact_enabled", lambda _: False)
    monkeypatch.setattr(chat, "_measure_native_count", AsyncMock(return_value=None))
    monkeypatch.setattr(chat, "_consume_stop_request", AsyncMock(return_value=False))
    monkeypatch.setattr(chat, "_drain_queued_messages", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat, "_build_workspace_inventory", AsyncMock(return_value=""))
    monkeypatch.setattr(token_estimate_check, "check_and_record", AsyncMock())
    finalize = AsyncMock()
    failed = AsyncMock()
    monkeypatch.setattr(chat, "_finalize", finalize)
    monkeypatch.setattr(chat, "_save_failed_assistant_turn", failed)

    @asynccontextmanager
    async def meter(*args, **kwargs):
        yield SimpleNamespace(feature="chat")

    monkeypatch.setattr(metering, "metered_async", meter)

    async def run(agent, **kwargs):
        monkeypatch.setattr(chat, "create_agentic_chat_agent", lambda *a, **k: agent)
        return [json.loads(chunk) async for chunk in chat.chat_stream(
            kwargs.pop("message", "Yes, approve it."), [], "conversation", "user",
            user=SimpleNamespace(current_team=None, organization_id=None),
            team_access=SimpleNamespace(),
            **kwargs,
        )]

    return SimpleNamespace(run=run, finalize=finalize, failed=failed, conversation=conversation)


@pytest.mark.parametrize("tool_name,answer", [
    ("propose_obligations", "The reporting deadlines were added to the RA inbox."),
    ("run_pin_on_project", "The workflow is running on the project files."),
])
async def test_approval_only_emits_and_persists_the_answer(chat_harness, tool_name, answer):
    calls = []

    async def execute(confirmed: bool):
        calls.append(confirmed)
        return {"status": "started"}

    async def respond(messages, info):
        if not calls:
            yield {0: DeltaThinkingPart(content="PRIVATE native reasoning")}
            for char in LEAK:
                yield char
            yield {1: DeltaToolCall(name=tool_name, json_args='{"confirmed":true}', tool_call_id="approved")}
        else:
            # The final response can also put deliberation in its text channel.
            for char in f"<think>PRIVATE tagged reasoning</think>{LEAK}\n\n{answer}":
                yield char

    agent = Agent(FunctionModel(stream_function=respond), tools=[Tool(execute, name=tool_name)])
    chunks = await chat_harness.run(agent)
    assert not [c for c in chunks if c["kind"] == "error"], chunks
    assert calls == [True]
    assert not [c for c in chunks if c["kind"] == "thinking"]
    assert [c["content"] for c in chunks if c["kind"] == "text"] == [answer]
    assert len([c for c in chunks if c["kind"] == "tool_result"]) == 1
    chat_harness.finalize.assert_awaited_once()
    saved = chat_harness.finalize.call_args
    assert saved.args[1] == answer
    assert saved.kwargs["thinking"] is None
    assert [s["content"] for s in saved.kwargs["segments"] if s["kind"] == "text"] == [answer]
    assert "PRIVATE" not in json.dumps(saved.kwargs)


async def test_rejected_draft_is_never_streamed(chat_harness):
    attempts = 0

    async def respond(messages, info):
        yield "The action succeeded." if attempts == 0 else "The action could not be completed."

    agent = Agent(FunctionModel(stream_function=respond))

    @agent.output_validator
    def validate(output):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ModelRetry("Report the actual outcome.")
        return output

    chunks = await chat_harness.run(agent)
    assert [c["content"] for c in chunks if c["kind"] == "text"] == ["The action could not be completed."]
    assert chat_harness.finalize.call_args.args[1] == "The action could not be completed."


async def test_interrupted_private_draft_is_not_saved(chat_harness):
    started = False

    async def respond(messages, info):
        nonlocal started
        started = True
        yield LEAK
        raise RuntimeError("PRIVATE provider detail")

    chunks = await chat_harness.run(Agent(FunctionModel(stream_function=respond)))
    assert started
    assert not [c for c in chunks if c["kind"] in {"text", "thinking"}]
    assert len([c for c in chunks if c["kind"] == "error"]) == 1
    chat_harness.failed.assert_awaited_once()
    saved = chat_harness.failed.call_args
    assert "system reminder" not in saved.args[1]
    assert "PRIVATE" not in saved.args[1]
    assert saved.kwargs["thinking"] is None


@pytest.mark.parametrize("succeeded", [True, False])
async def test_private_only_summary_keeps_receipt_without_repeating_action(chat_harness, succeeded):
    calls = []
    receipt = {"status": "started"} if succeeded else {"error": "Permission denied"}

    async def execute(confirmed: bool):
        calls.append(confirmed)
        return receipt

    async def respond(messages, info):
        if not calls:
            yield {0: DeltaToolCall(name="run_pin_on_project", json_args='{"confirmed":true}')}
        else:
            yield LEAK

    agent = Agent(FunctionModel(stream_function=respond), tools=[Tool(execute, name="run_pin_on_project")])
    chunks = await chat_harness.run(agent)
    assert calls == [True]
    assert [c["content"] for c in chunks if c["kind"] == "tool_result"] == [receipt]
    assert [c["content"] for c in chunks if c["kind"] == "text"] == [
        "Please review the action results above. I couldn't produce a summary."
    ]
    saved = chat_harness.finalize.call_args
    assert saved.kwargs["tool_results"][0]["content"] == receipt


async def test_private_only_answer_without_tools_does_not_claim_an_action(chat_harness):
    async def respond(messages, info):
        yield LEAK

    chunks = await chat_harness.run(Agent(FunctionModel(stream_function=respond)))
    assert [c["content"] for c in chunks if c["kind"] == "text"] == [
        "I couldn't produce a reply. Please try again."
    ]
    assert chat_harness.finalize.call_args.kwargs["tool_results"] is None
