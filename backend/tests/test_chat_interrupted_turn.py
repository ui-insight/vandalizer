"""A turn that ends early keeps what it finished.

Support ticket: a four-document extraction batch was stopped after two. The
stopped turn was saved as text only, so after a reload the extraction cards
and plan checklist were gone, the turn read "connection closed" and its
activity "Failed". On "continue" the model, whose history now showed it
reporting PI/budget values with no tool calls, reported "$25,000" and
"$250,000.00" for the two documents it never ran.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart


def _call(cid, doc):
    return {"tool_name": "run_extraction", "tool_call_id": cid, "args": {"document": doc}}


def _result(cid, budget):
    return {
        "tool_name": "run_extraction", "tool_call_id": cid,
        "content": {"PI Name": "Dr. Rivera", "Total Budget": budget}, "quality": None,
    }


# Two documents finished, the third was still running when Stop was pressed.
CALLS = [_call("c1", "nih-r01.pdf"), _call("c2", "subaward.pdf"), _call("c3", "usda.pdf")]
RESULTS = [_result("c1", "1250000"), _result("c2", "310,500.00")]
SEGMENTS = [
    {"kind": "tool_call", "call": CALLS[0]},
    {"kind": "tool_result", "result": RESULTS[0]},
    {"kind": "text", "content": "<think>next</think>nih-r01.pdf: PI Dr. Rivera, $1,250,000."},
    {"kind": "tool_call", "call": CALLS[1]},
    {"kind": "tool_result", "result": RESULTS[1]},
    {"kind": "text", "content": "subaward.pdf: PI Dr. Rivera, $310,500.00."},
    {"kind": "tool_call", "call": CALLS[2]},
]
PLAN = [
    {"content": "nih-r01.pdf", "active_form": "", "status": "completed"},
    {"content": "subaward.pdf", "active_form": "", "status": "completed"},
    {"content": "usda.pdf", "active_form": "", "status": "in_progress"},
    {"content": "jaggaer.pdf", "active_form": "", "status": "pending"},
]


class TestCompletedToolWork:
    def test_keeps_finished_calls_and_drops_the_one_still_running(self):
        from app.services.chat_service import _completed_tool_work

        work = _completed_tool_work(CALLS, RESULTS, SEGMENTS)
        assert [c["tool_call_id"] for c in work["tool_calls"]] == ["c1", "c2"]
        assert work["tool_results"] == RESULTS
        kinds = [s["kind"] for s in work["segments"]]
        assert kinds == ["tool_call", "tool_result", "text", "tool_call", "tool_result", "text"]
        assert "<think>" not in work["segments"][2]["content"]

    def test_nothing_finished_saves_no_tool_work(self):
        from app.services.chat_service import _completed_tool_work

        work = _completed_tool_work([CALLS[2]], [], [{"kind": "tool_call", "call": CALLS[2]}])
        assert work == {"tool_calls": None, "tool_results": None, "segments": None}


def _conversation():
    conv = MagicMock()
    conv.id = "conv-id"
    conv.add_message = AsyncMock()
    conv.save = AsyncMock()
    conv.active_plan = None
    return conv


def _activity():
    ev = MagicMock()
    ev.save = AsyncMock()
    return ev


async def _save_stopped(conv, ev, interruption):
    from app.services.chat_service import (
        _build_interrupted_body, _completed_tool_work, _save_failed_assistant_turn,
    )

    reason = "stopped by the user" if interruption == "stopped" else "connection closed before completion"
    with (
        patch("app.services.chat_service.ActivityEvent.get", new=AsyncMock(return_value=ev)),
        patch("app.services.chat_service.ChatConversation.get", new=AsyncMock(return_value=MagicMock(messages=[1, 2]))),
    ):
        await _save_failed_assistant_turn(
            conv,
            _build_interrupted_body(["nih-r01.pdf: PI Dr. Rivera, $1,250,000."], reason),
            "activity-1",
            reason,
            interruption=interruption,
            plan_state=PLAN,
            citations=None,
            **_completed_tool_work(CALLS, RESULTS, SEGMENTS),
        )


class TestSaveStoppedTurn:
    @pytest.mark.asyncio
    async def test_stop_keeps_cards_and_plan_and_is_canceled_not_failed(self):
        conv, ev = _conversation(), _activity()
        await _save_stopped(conv, ev, "stopped")

        _, kwargs = conv.add_message.await_args
        assert kwargs["interruption"] == "stopped"
        assert [r["tool_call_id"] for r in kwargs["tool_results"]] == ["c1", "c2"]
        assert kwargs["segments"][-1] == {"kind": "text", "content": "_(response interrupted — stopped by the user)_"}
        assert conv.active_plan == PLAN
        conv.save.assert_awaited()
        assert ev.status == "canceled"
        assert ev.error == "stopped by the user"

    @pytest.mark.asyncio
    async def test_dropped_connection_is_still_a_failure(self):
        conv, ev = _conversation(), _activity()
        await _save_stopped(conv, ev, "connection")

        _, kwargs = conv.add_message.await_args
        assert kwargs["interruption"] == "connection"
        assert ev.status == "failed"

    @pytest.mark.asyncio
    async def test_saved_turn_replays_as_real_tool_calls(self):
        """The next turn's model sees the extraction calls it made, so it has
        a pattern to follow for the remaining documents, not bare values."""
        from app.models.chat import ChatMessage, ChatRole

        conv, ev = _conversation(), _activity()
        await _save_stopped(conv, ev, "stopped")
        args, kwargs = conv.add_message.await_args
        msg = ChatMessage.model_construct(
            role=ChatRole.ASSISTANT, message=args[1],
            tool_calls=kwargs["tool_calls"], tool_results=kwargs["tool_results"],
            segments=kwargs["segments"], interruption=kwargs["interruption"],
        )
        replay = msg.to_model_messages()
        calls = [p.tool_call_id for m in replay if isinstance(m, ModelResponse) for p in m.parts if isinstance(p, ToolCallPart)]
        returns = [p.tool_call_id for m in replay if isinstance(m, ModelRequest) for p in m.parts if isinstance(p, ToolReturnPart)]
        assert calls == returns == ["c1", "c2"]
        assert msg.to_dict()["interruption"] == "stopped"


class TestCancelledStream:
    """The save must survive the way Starlette actually cancels a stream.

    Retest of the ticket: after Stop and a reload the whole reply was gone,
    and "continue" re-ran the batch from document 1. Starlette cancels a
    streaming response through an anyio cancel scope, where every await is
    cancelled again: reading the stop flag finished, the save never started.
    """

    async def _disconnect_mid_stream(self, consume, save):
        import asyncio

        from starlette.responses import StreamingResponse

        from app.services.chat_service import _save_cancelled_turn

        async def stream():
            try:
                yield "nih-r01.pdf: PI Dr. Rivera, $1,250,000."
                await asyncio.sleep(10)
                yield "unreachable"
            except asyncio.CancelledError:
                await _save_cancelled_turn(
                    conv, ["nih-r01.pdf: PI Dr. Rivera, $1,250,000."], [], "activity-1",
                    thinking=None, thinking_duration=None,
                    completed_work={**_completed_tool_work(CALLS, RESULTS, SEGMENTS), "plan_state": PLAN},
                )
                raise

        from app.services.chat_service import _completed_tool_work

        conv = _conversation()
        sent = asyncio.Event()

        async def send(message):
            if message.get("body"):
                sent.set()

        async def receive():
            await sent.wait()
            return {"type": "http.disconnect"}

        scope = {"type": "http", "asgi": {"spec_version": "2.3"}}
        with (
            patch("app.services.chat_service._consume_stop_request", new=consume),
            patch("app.services.chat_service._save_failed_assistant_turn", new=save),
        ):
            await asyncio.wait_for(StreamingResponse(stream())(scope, receive, send), 5)

    @pytest.mark.asyncio
    async def test_stopped_turn_is_saved_with_its_work_when_starlette_cancels(self):
        import asyncio

        async def consume(_conv):
            await asyncio.sleep(0)  # a real database round trip
            return True

        save = AsyncMock()
        await self._disconnect_mid_stream(consume, save)

        save.assert_awaited_once()
        args, kwargs = save.await_args
        assert kwargs["interruption"] == "stopped"
        assert args[3] == "stopped by the user"
        assert [r["tool_call_id"] for r in kwargs["tool_results"]] == ["c1", "c2"]
        assert kwargs["plan_state"] == PLAN

    @pytest.mark.asyncio
    async def test_save_error_is_logged_and_the_cancel_still_propagates(self):
        save = AsyncMock(side_effect=RuntimeError("mongo down"))
        await self._disconnect_mid_stream(AsyncMock(return_value=False), save)
        assert save.await_args.kwargs["interruption"] == "connection"


class TestStopRequest:
    @pytest.mark.asyncio
    async def test_consumes_flag_from_the_database(self):
        from app.services.chat_service import _consume_stop_request

        conv = MagicMock(id="conv-id", stop_requested=True)
        coll = MagicMock(find_one_and_update=AsyncMock(return_value={"_id": "conv-id"}))
        with patch("app.services.chat_service.ChatConversation.get_motor_collection", return_value=coll):
            assert await _consume_stop_request(conv) is True
        filt, update = coll.find_one_and_update.await_args.args
        assert filt == {"_id": "conv-id", "stop_requested": True}
        assert update == {"$set": {"stop_requested": False}}
        assert conv.stop_requested is False

    @pytest.mark.asyncio
    async def test_no_flag_means_not_stopped(self):
        from app.services.chat_service import _consume_stop_request

        coll = MagicMock(find_one_and_update=AsyncMock(return_value=None))
        with patch("app.services.chat_service.ChatConversation.get_motor_collection", return_value=coll):
            assert await _consume_stop_request(MagicMock(id="x")) is False


class TestFiguresAgainstToolResults:
    def _sources(self, history):
        from app.services.chat_service import _replayed_tool_outputs
        from app.services.kb_answer_grounding import bare_amounts_as_money

        return "\n".join(bare_amounts_as_money(t) for t in _replayed_tool_outputs(history))

    def _history(self):
        return [
            ModelResponse(parts=[ToolCallPart(tool_name="run_extraction", args={}, tool_call_id="c1")]),
            ModelRequest(parts=[ToolReturnPart(
                tool_name="run_extraction", tool_call_id="c1",
                content={"PI Name": "Dr. Rivera", "Total Budget": "1250000"},
            )]),
            ModelRequest(parts=[ToolReturnPart(
                tool_name="run_extraction", tool_call_id="c2",
                content=json.dumps({"Total Budget": "310,500.00"}),
            )]),
        ]

    def test_invented_budgets_for_unrun_documents_are_flagged(self):
        from app.services.kb_answer_grounding import unsupported_figures

        answer = (
            "Continuing — item 3. usda.pdf: Total Budget: $25,000. "
            "jaggaer.pdf: Total Budget: $250,000.00. All four are done."
        )
        assert unsupported_figures(answer, self._sources(self._history())) == ["$25,000", "$250,000.00"]

    def test_extracted_values_reported_with_formatting_are_not_flagged(self):
        from app.services.kb_answer_grounding import unsupported_figures

        answer = "nih-r01.pdf: $1,250,000. subaward.pdf: $310,500."
        assert unsupported_figures(answer, self._sources(self._history())) == []


@pytest.mark.asyncio
async def test_stop_route_sets_the_flag_for_the_callers_conversation(client):
    from tests.test_chat_routes import _auth, _make_user

    cookies, headers = _auth()
    coll = MagicMock(update_one=AsyncMock(return_value=MagicMock(matched_count=1)))
    with (
        patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
        patch("app.dependencies.User") as MockUser,
        patch("app.routers.chat.ChatConversation.get_motor_collection", return_value=coll),
    ):
        MockUser.find_one = AsyncMock(return_value=_make_user())
        resp = await client.post(
            "/api/chat/stop", json={"conversation_uuid": "conv-1"},
            cookies=cookies, headers=headers,
        )
    assert resp.status_code == 200
    coll.update_one.assert_awaited_once_with(
        {"uuid": "conv-1", "user_id": "testuser"}, {"$set": {"stop_requested": True}},
    )
