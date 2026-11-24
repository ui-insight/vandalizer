"""Phase 10 of the agentic-chat harness uplift: the mid-run message queue.

The load-bearing property: a message staged on deps.queued_user_parts during
the run is delivered to the model on its NEXT request (via the
_inject_queued_user_parts history processor), and the persisted queued_user
segment replays byte-identically in the same position."""

import types

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.models.chat import ChatMessage, ChatRole, wrap_queued_user_message
from app.services.llm_service import _inject_queued_user_parts


class _Deps:
    def __init__(self):
        self.queued_user_parts: list[str] = []


class TestMidRunInjection:
    async def test_staged_message_reaches_the_next_request(self):
        """Replicates chat_stream's pattern: observe nodes via agent.iter,
        stage a queued message when the model is mid-tool-loop, and assert
        the SECOND request carries it as a wrapped user part."""
        requests: list[list[str]] = []

        def model_fn(messages, info: AgentInfo):
            requests.append([
                f"{type(p).__name__}:{str(getattr(p, 'content', ''))[:60]}"
                for m in messages
                for p in m.parts
            ])
            if len(requests) == 1:
                return ModelResponse(parts=[
                    ToolCallPart(tool_name="lookup", args={}, tool_call_id="tc1")
                ])
            return ModelResponse(parts=[TextPart(content="done")])

        agent = Agent(
            FunctionModel(model_fn),
            deps_type=_Deps,
            history_processors=[_inject_queued_user_parts],
        )

        @agent.tool
        async def lookup(ctx: RunContext[_Deps]) -> str:
            return "found"

        deps = _Deps()
        seen_request_nodes = 0
        async with agent.iter("original ask", deps=deps) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    seen_request_nodes += 1
                    if seen_request_nodes == 2:
                        # The user typed while the tool ran; chat_stream
                        # drains and stages exactly like this.
                        deps.queued_user_parts.append("also check FY25")

        assert len(requests) == 2
        expected = wrap_queued_user_message("also check FY25")
        assert any(expected[:40] in part for part in requests[1])
        assert deps.queued_user_parts == []  # consumed by the processor

    async def test_processor_is_a_noop_without_staged_messages(self):
        messages = [types.SimpleNamespace(parts=[])]
        ctx = types.SimpleNamespace(deps=_Deps())
        assert await _inject_queued_user_parts(ctx, messages) is messages

    async def test_processor_tolerates_foreign_deps(self):
        # The non-agentic agent never registers this processor, but be
        # defensive about deps without the attribute anyway.
        ctx = types.SimpleNamespace(deps=object())
        messages = [types.SimpleNamespace(parts=[])]
        assert await _inject_queued_user_parts(ctx, messages) is messages


class TestQueuedUserReplay:
    def test_segment_replays_in_position_with_identical_wrapping(self):
        msg = ChatMessage.model_construct(
            role=ChatRole.ASSISTANT,
            message="done",
            segments=[
                {"kind": "tool_call", "call": {
                    "tool_name": "lookup", "tool_call_id": "tc1", "args": {},
                }},
                {"kind": "tool_result", "result": {
                    "tool_name": "lookup", "tool_call_id": "tc1", "content": "found",
                }},
                {"kind": "queued_user", "content": "also check FY25"},
                {"kind": "text", "content": "done"},
            ],
        )
        replay = msg.to_model_messages()
        # Expect: response(tool_call), request(tool_return + queued user), response(text)
        request = replay[1]
        kinds = [type(p).__name__ for p in request.parts]
        assert kinds == ["ToolReturnPart", "UserPromptPart"]
        user_part = request.parts[1]
        assert isinstance(user_part, UserPromptPart)
        assert user_part.content == wrap_queued_user_message("also check FY25")
        assert isinstance(request.parts[0], ToolReturnPart)


def _fake_conversation_cls(conv):
    """Stand-in for the Beanie ChatConversation class: uninitialized models
    can't build `ChatConversation.uuid ==` expressions, so the comparable
    fields just swallow the comparison and find_one returns the fixture."""

    class _Field:
        def __eq__(self, other):
            return other

    class _FakeConversation:
        uuid = _Field()
        user_id = _Field()

        @staticmethod
        async def find_one(*args, **kwargs):
            return conv

    return _FakeConversation


class TestQueueEndpointValidation:
    async def test_rejects_empty_message(self, monkeypatch):
        from fastapi import HTTPException

        from app.models.chat import ChatConversation
        from app.routers import chat as chat_router

        conv = ChatConversation.model_construct(
            uuid="c1", title="t", user_id="u1", queued_messages=[],
        )
        monkeypatch.setattr(
            chat_router, "ChatConversation", _fake_conversation_cls(conv)
        )
        body = types.SimpleNamespace(conversation_uuid="c1", message="   ")
        user = types.SimpleNamespace(user_id="u1")
        try:
            await chat_router.queue_message(body, user)
            raise AssertionError("expected 400")
        except HTTPException as e:
            assert e.status_code == 400

    async def test_rejects_full_queue(self, monkeypatch):
        from fastapi import HTTPException

        from app.models.chat import ChatConversation
        from app.routers import chat as chat_router

        conv = ChatConversation.model_construct(
            uuid="c1", title="t", user_id="u1",
            queued_messages=[{"text": f"m{i}"} for i in range(10)],
        )
        monkeypatch.setattr(
            chat_router, "ChatConversation", _fake_conversation_cls(conv)
        )
        body = types.SimpleNamespace(conversation_uuid="c1", message="hello")
        user = types.SimpleNamespace(user_id="u1")
        try:
            await chat_router.queue_message(body, user)
            raise AssertionError("expected 409")
        except HTTPException as e:
            assert e.status_code == 409
