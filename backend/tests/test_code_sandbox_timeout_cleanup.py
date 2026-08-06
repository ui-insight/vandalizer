"""A sandbox timeout must actually stop the runaway, not just report one.

The pre-existing timeout tests assert only that ``{"timed_out": True}`` comes
back — which the original, leaking implementation also did. They therefore
cannot distinguish a stopped thread from an abandoned one, which is how a
version-dependent fix passed CI on one Python and leaked on another.

These tests assert the observable that matters: after the call returns, nothing
is still running.
"""

import os
import threading
import time

from app.utils.code_sandbox_runner import execute_sandboxed_code


def _cpu_seconds() -> float:
    t = os.times()
    return t.user + t.system


def test_single_line_runaway_leaves_no_live_thread():
    """`while True: pass` on ONE line is the case that breaks line-event tracing.

    On CPython 3.11 a loop back-edge emits no new `line` event when the line
    number doesn't change, so a per-line deadline check fires exactly once and
    the thread runs forever.
    """
    before = threading.active_count()

    result = execute_sandboxed_code("while True: pass", {}, timeout=1)
    assert result == {"timed_out": True}

    # Give the runner a moment to unwind before judging it.
    deadline = time.monotonic() + 5.0
    while threading.active_count() > before and time.monotonic() < deadline:
        time.sleep(0.05)

    assert threading.active_count() == before, (
        "sandbox timeout left a thread running; it will spin for the life of "
        "the process and starve everything else of the GIL"
    )


def test_multi_line_runaway_leaves_no_live_thread():
    """The same guarantee for the multi-line form, which traces differently."""
    before = threading.active_count()

    result = execute_sandboxed_code("while True:\n    pass", {}, timeout=1)
    assert result == {"timed_out": True}

    deadline = time.monotonic() + 5.0
    while threading.active_count() > before and time.monotonic() < deadline:
        time.sleep(0.05)

    assert threading.active_count() == before


def test_process_is_idle_after_a_timeout():
    """Thread count alone can be fooled; assert no CPU is being burned either."""
    execute_sandboxed_code("while True: pass", {}, timeout=1)

    time.sleep(0.2)  # let any unwinding settle
    start = _cpu_seconds()
    time.sleep(1.0)
    burned = _cpu_seconds() - start

    assert burned < 0.25, (
        f"process burned {burned:.2f}s of CPU while idle after a sandbox "
        "timeout — something is still spinning"
    )


def test_normal_code_still_returns_its_result():
    """The stopping mechanism must not disturb ordinary execution."""
    result = execute_sandboxed_code("result = sum(range(1000))", {}, timeout=10)
    assert result == {"result": 499500}


def test_runtime_error_is_still_reported():
    result = execute_sandboxed_code("result = 1 / 0", {}, timeout=10)
    assert "error" in result
    assert "division by zero" in result["error"]
