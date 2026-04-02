"""Tests for app.utils.code_sandbox_runner — sandboxed code execution."""

import multiprocessing

from app.utils.code_sandbox_runner import execute_sandboxed_code, run_sandboxed_code


class TestRunSandboxedCode:
    """Test the legacy multiprocessing-based entry point."""

    def test_success(self):
        q: multiprocessing.Queue = multiprocessing.Queue()
        run_sandboxed_code("result = len(data)", [1, 2, 3], q)
        msg = q.get(timeout=5)
        assert msg == {"result": 3}

    def test_error(self):
        q: multiprocessing.Queue = multiprocessing.Queue()
        run_sandboxed_code("x = 1/0", None, q)
        msg = q.get(timeout=5)
        assert "error" in msg

    def test_result_not_set(self):
        q: multiprocessing.Queue = multiprocessing.Queue()
        run_sandboxed_code("x = 42", None, q)
        msg = q.get(timeout=5)
        assert "result" in msg
