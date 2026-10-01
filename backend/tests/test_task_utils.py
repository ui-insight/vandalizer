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


def test_run_task_async_cancels_work_the_task_left_running(caplog):
    """Sentry 7613426710: an agent run still in flight when the task's
    coroutine returned was destroyed by loop.close() ("Task was destroyed but
    it is pending! … CombinedCapability.wrap_run()"). It is now cancelled and
    drained — its cleanup runs — and named in a warning."""
    import logging

    cleaned_up = []

    async def _straggler():
        try:
            await asyncio.sleep(30)
        finally:
            cleaned_up.append(True)

    async def _work():
        asyncio.get_running_loop().create_task(_straggler())
        await asyncio.sleep(0)
        return "done"

    with caplog.at_level(logging.WARNING, logger="app.tasks"):
        assert run_task_async(_work()) == "done"

    assert cleaned_up == [True]
    assert any("_straggler" in r.getMessage() for r in caplog.records)


def test_run_task_async_finalizes_async_generators():
    """pydantic-ai's agent.iter is an async generator; left suspended, its
    cleanup (which releases the run's wrap task) must still run."""
    finalized = []

    async def _gen():
        try:
            yield 1
            yield 2
        finally:
            finalized.append(True)

    async def _work():
        agen = _gen()
        await agen.__anext__()  # suspended mid-iteration, never closed
        _work.agen = agen  # keep it alive past the coroutine
        return "done"

    assert run_task_async(_work()) == "done"
    assert finalized == [True]


def test_run_task_async_still_raises_the_tasks_error_with_leftovers():
    async def _straggler():
        await asyncio.sleep(30)

    async def _boom():
        asyncio.get_running_loop().create_task(_straggler())
        await asyncio.sleep(0)
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        run_task_async(_boom())
