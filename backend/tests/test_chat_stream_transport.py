import asyncio
from contextvars import ContextVar
import json

import pytest

from app.services.chat_stream_transport import with_heartbeats
from app.services.chat_service import _ToolPreparationProgress, chat_stream
from pydantic_ai.messages import PartStartEvent, PartDeltaEvent, ToolCallPart, ToolCallPartDelta, TextPart


@pytest.mark.asyncio
async def test_heartbeat_keeps_silent_page_generation_alive_without_canceling_it():
    release = asyncio.Event()
    closed = asyncio.Event()
    scope = ContextVar('stream_scope', default=None)
    async def source():
        token = scope.set('one producer')
        try:
            yield 'preparing\n'
            await release.wait()
            assert scope.get() == 'one producer'
            yield 'preview\n'
        finally:
            scope.reset(token)
            closed.set()
    stream = with_heartbeats(source(), interval=0.005)
    assert await anext(stream) == 'preparing\n'
    for _ in range(3):
        assert json.loads(await anext(stream))['kind'] == 'heartbeat'
        assert not closed.is_set()
    release.set()
    assert await anext(stream) == 'preview\n'
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert closed.is_set()


@pytest.mark.asyncio
async def test_disconnecting_closes_the_original_stream():
    closed = asyncio.Event()
    async def source():
        try:
            yield 'start'
            await asyncio.Event().wait()
        finally:
            closed.set()
    stream = with_heartbeats(source(), interval=0.005)
    assert await anext(stream) == 'start'
    await anext(stream)
    await stream.aclose()
    assert closed.is_set()


@pytest.mark.asyncio
async def test_source_failure_is_propagated_not_hidden_by_heartbeats():
    async def source():
        yield 'start'
        raise ValueError('upstream failed')
    stream = with_heartbeats(source(), interval=0.005)
    assert await anext(stream) == 'start'
    with pytest.raises(ValueError, match='upstream failed'):
        await anext(stream)


def test_page_preparation_is_announced_before_arguments_finish_without_exposing_html():
    progress = _ToolPreparationProgress()
    chunk = progress.feed(PartStartEvent(index=0, part=ToolCallPart(tool_name='create_html_artifact', tool_call_id='page-1', args='{"html":"<html>')))
    event = json.loads(chunk)
    assert event['activity'] == {'phase': 'tool_preparing', 'content': '', 'tool_name': 'create_html_artifact', 'tool_call_id': 'page-1'}
    for _ in range(100):
        assert progress.feed(PartDeltaEvent(index=0, delta=ToolCallPartDelta(args_delta='private draft contents'))) is None
    assert progress.feed(PartStartEvent(index=1, part=TextPart(content='answer'))) is None
    assert 'private' not in chunk and 'html>' not in chunk
    second = progress.feed(PartStartEvent(index=2, part=ToolCallPart(tool_name='search_documents', tool_call_id='read-1', args={})))
    assert json.loads(second)['activity']['tool_name'] == 'search_documents'


@pytest.mark.asyncio
async def test_chat_emits_context_progress_before_waiting_on_model_configuration():
    stream = chat_stream('Build a page', [], 'conversation', 'user')
    assert json.loads(await anext(stream))['activity']['phase'] == 'context'
    await stream.aclose()


@pytest.mark.asyncio
async def test_independent_source_cancellation_does_not_heartbeat_forever():
    async def source():
        yield 'start'
        raise asyncio.CancelledError()
    stream = with_heartbeats(source(), interval=0.005)
    assert await anext(stream) == 'start'
    with pytest.raises(asyncio.CancelledError):
        await anext(stream)
