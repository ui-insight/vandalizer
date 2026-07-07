"""Tests for shared Celery task utilities in app.tasks.__init__."""

import asyncio

import pytest

from app.tasks import run_task_async


def test_run_task_async_returns_result():
    """run_task_async runs a coroutine to completion and returns its value."""

    async def _work():
        return 21 * 2

    assert run_task_async(_work()) == 42


def test_run_task_async_clears_closed_loop_for_next_run_sync():
    """Regression: after run_task_async, a later pydantic-ai-style run_sync must
    not inherit the closed loop and crash with "Event loop is closed".

    run_task_async creates a loop, sets it current, then closes it. If it does
    not also clear the thread's current loop, ``asyncio.get_event_loop()``
    returns the closed loop and any subsequent ``run_sync`` blows up. Here we
    emulate pydantic-ai's ``get_event_loop`` (get_event_loop, else new loop).
    """

    async def _noop():
        return None

    run_task_async(_noop())

    # Emulate pydantic_ai._utils.get_event_loop()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    assert not loop.is_closed(), "run_task_async left a closed loop as current"

    # And the loop is actually usable, as run_sync would need.
    assert loop.run_until_complete(_noop()) is None
    loop.close()
    asyncio.set_event_loop(None)


def test_run_task_async_propagates_exceptions():
    """Task errors surface to the caller rather than being swallowed."""

    async def _boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        run_task_async(_boom())
