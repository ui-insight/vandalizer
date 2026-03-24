"""Lightweight sandbox runner for user code execution.

This module is intentionally kept free of heavy dependencies (no httpx,
BeautifulSoup, pydantic-ai, MongoDB drivers, etc.) to keep it fast to import.
"""

import datetime
import json
import math
import re
import threading


_SAFE_BUILTINS = {
    "json": json,
    "re": re,
    "math": math,
    "datetime": datetime,
    "str": str,
    "int": int,
    "float": float,
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


def execute_sandboxed_code(code: str, input_data, timeout: int = 10) -> dict:
    """Execute sandboxed code in a daemon thread with a timeout.

    Returns a dict with one of:
    - ``{"result": <value>}`` on success
    - ``{"error": <message>}`` on runtime error
    - ``{"timed_out": True}`` when the code exceeds the timeout
    """
    result_holder: dict = {}
    local_vars = {"data": input_data, "result": None}

    def _run():
        try:
            exec(code, {"__builtins__": _SAFE_BUILTINS}, local_vars)  # noqa: S102
        except Exception as exc:
            result_holder["error"] = str(exc)
            return
        result_holder["result"] = local_vars.get("result")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        return {"timed_out": True}

    return result_holder if result_holder else {"result": local_vars.get("result")}


def run_sandboxed_code(code: str, input_data, result_queue) -> None:
    """Legacy entry point for multiprocessing-based execution."""
    local_vars = {"data": input_data, "result": None}

    try:
        exec(code, {"__builtins__": _SAFE_BUILTINS}, local_vars)  # noqa: S102
    except Exception as exc:
        result_queue.put({"error": str(exc)})
        return

    try:
        result_queue.put({"result": local_vars.get("result", "")})
    except Exception:
        result_queue.put({"result": str(local_vars.get("result", ""))})
