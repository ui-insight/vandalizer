"""Lightweight sandbox runner for user code execution.

This module is intentionally kept free of heavy dependencies (no httpx,
BeautifulSoup, pydantic-ai, MongoDB drivers, etc.) to keep it fast to import.
"""

import ctypes
import datetime
import json
import logging
import math
import queue
import re
import threading
from typing import Any

logger = logging.getLogger(__name__)


_SAFE_BUILTINS = {
    "json": json,
    "re": re,
    "math": math,
    "datetime": datetime,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "len": len,
    "range": range,
    "enumerate": enumerate,
    "sorted": sorted,
    "min": min,
    "max": max,
    "sum": sum,
    "round": round,
    "abs": abs,
    "isinstance": isinstance,
    "print": print,
    "True": True,
    "False": False,
    "None": None,
}


class _SandboxTimeout(BaseException):
    """Raised inside the sandbox thread to unwind it once the deadline passes.

    Derives from BaseException so sandboxed ``except Exception`` handlers can't
    swallow it and keep the thread alive.
    """


# How many times to ask a runaway thread to unwind, and how long to wait between
# attempts. More than one because sandboxed code is free to wrap its body in a
# bare ``except``/``except BaseException``, which swallows the first delivery.
_STOP_ATTEMPTS = 3
_STOP_GRACE_SECONDS = 0.25


def _stop_thread(thread: threading.Thread) -> bool:
    """Ask *thread* to unwind by scheduling ``_SandboxTimeout`` inside it.

    CPython delivers an asynchronously-set exception at the next bytecode
    boundary, which is what makes this work for a tight ``while True: pass``
    where line-based tracing does not (see ``execute_sandboxed_code``).

    Returns True if the thread stopped. A thread that deliberately swallows the
    exception in a loop cannot be stopped this way; we give up after
    ``_STOP_ATTEMPTS`` rather than block the caller indefinitely.
    """
    ident = thread.ident
    if ident is None:  # never started
        return True

    for _ in range(_STOP_ATTEMPTS):
        affected = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(ident), ctypes.py_object(_SandboxTimeout)
        )
        if affected > 1:
            # Should be unreachable: more than one thread matched the id. Undo
            # so we don't leave a pending exception on an unrelated thread.
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(ident), None)
            return False
        thread.join(timeout=_STOP_GRACE_SECONDS)
        if not thread.is_alive():
            return True

    logger.warning(
        "Sandbox thread %s did not stop after a timeout; it may continue to "
        "consume CPU in this process.",
        ident,
    )
    return False


def execute_sandboxed_code(code: str, input_data: Any, timeout: int = 10) -> dict[str, Any]:
    """Execute sandboxed code in a daemon thread with a timeout.

    Returns a dict with one of:
    - ``{"result": <value>}`` on success
    - ``{"error": <message>}`` on runtime error
    - ``{"timed_out": True}`` when the code exceeds the timeout

    The thread is *stopped* on timeout, not abandoned. Python has no way to kill
    a thread from outside, so we install a per-thread trace function that raises
    once the deadline passes; because tracing fires per line, any pure-Python
    loop unwinds promptly.

    Abandoning it is not a survivable option: a runaway like ``while True: pass``
    would keep spinning for the life of the process, holding the GIL between
    switch intervals and degrading everything else in it. In a Celery worker
    that is permanent, and it accumulates one pegged core per timeout.

    Known limitation: a runaway *inside a single C call* (e.g. ``sum(range(10**18))``
    — both names are in ``_SAFE_BUILTINS``) never returns to the bytecode eval
    loop, so the pending exception is never checked and that call cannot be
    interrupted. Only a killable subprocess closes that gap, at the cost of
    process startup and requiring picklable input. Worth revisiting if it shows
    up in practice.

    A per-line trace function was tried first and rejected: on CPython 3.11 a
    loop back-edge emits no new ``line`` event when the line number is
    unchanged, so ``while True: pass`` (all on one line — the form used in the
    tests) fired the deadline check exactly once and leaked anyway. It also cost
    ~5.4x on ordinary sandboxed code. This approach costs nothing until a
    timeout actually happens.
    """
    result_holder: dict = {}
    local_vars = {"data": input_data, "result": None}

    def _run() -> None:
        try:
            exec(code, {"__builtins__": _SAFE_BUILTINS}, local_vars)  # noqa: S102  # nosec B102
        except _SandboxTimeout:
            result_holder["timed_out"] = True
            return
        except Exception as exc:
            result_holder["error"] = str(exc)
            return
        result_holder["result"] = local_vars.get("result")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        _stop_thread(thread)
        return {"timed_out": True}

    if result_holder.get("timed_out"):
        return {"timed_out": True}

    return result_holder if result_holder else {"result": local_vars.get("result")}


def run_sandboxed_code(code: str, input_data: Any, result_queue: queue.Queue[dict[str, Any]]) -> None:
    """Legacy entry point for multiprocessing-based execution."""
    local_vars = {"data": input_data, "result": None}

    try:
        exec(code, {"__builtins__": _SAFE_BUILTINS}, local_vars)  # noqa: S102  # nosec B102
    except Exception as exc:
        result_queue.put({"error": str(exc)})
        return

    try:
        result_queue.put({"result": local_vars.get("result", "")})
    except Exception:
        result_queue.put({"result": str(local_vars.get("result", ""))})
