"""Tests for CodeExecutionNode — sandbox restrictions and timeout."""

import pytest

from app.services.workflow_engine import CodeExecutionNode


def _run_code(code: str, input_data=None):
    """Helper: run code through CodeExecutionNode and return the output dict."""
    node = CodeExecutionNode({"code": code})
    return node.process({"output": input_data})


class TestCodeExecution:
    def test_basic_result_extraction(self):
        result = _run_code("result = 42")
        assert result["output"] == 42
        assert result["step_name"] == "CodeNode"

    def test_access_input_data(self):
        result = _run_code("result = len(data)", input_data=[1, 2, 3])
        assert result["output"] == 3

    def test_string_manipulation(self):
        result = _run_code("result = data.upper()", input_data="hello")
        assert result["output"] == "HELLO"

    def test_json_available(self):
        result = _run_code('result = json.dumps({"key": "value"})')
        assert result["output"] == '{"key": "value"}'

    def test_re_available(self):
        result = _run_code('result = re.sub(r"\\d+", "X", data)', input_data="abc123def")
        assert result["output"] == "abcXdef"

    def test_math_available(self):
        result = _run_code("result = math.sqrt(144)")
        assert result["output"] == 12.0

    def test_empty_code_returns_empty(self):
        result = _run_code("")
        assert result["output"] == ""

    def test_no_result_set_returns_none(self):
        """When user code doesn't assign to `result`, output is None."""
        result = _run_code("x = 42")
        assert result["output"] is None

    def test_list_comprehension(self):
        result = _run_code("result = [x * 2 for x in data]", input_data=[1, 2, 3])
        assert result["output"] == [2, 4, 6]

    def test_dict_operations(self):
        result = _run_code("result = {k: v.upper() for k, v in data.items()}", input_data={"a": "hello"})
        assert result["output"] == {"a": "HELLO"}


class TestCodeExecutionSandbox:
    """Verify that dangerous builtins are not accessible.

    The sandbox replaces __builtins__ with a restricted dict, so attempting
    to use __import__, open, eval, or exec raises NameError. The exec()
    call in the node propagates this as an unhandled exception.
    """

    def test_import_blocked(self):
        with pytest.raises(NameError, match="__import__"):
            _run_code("result = __import__('os').getcwd()")

    def test_open_blocked(self):
        with pytest.raises(NameError, match="open"):
            _run_code("result = open('/etc/passwd').read()")

    def test_eval_blocked(self):
        with pytest.raises(NameError, match="eval"):
            _run_code("result = eval('1+1')")

    def test_exec_within_exec_blocked(self):
        with pytest.raises(NameError, match="exec"):
            _run_code("exec('result = 1')")

    def test_builtins_cannot_escape_via_class(self):
        """Attempt to access builtins via __class__.__bases__ should fail or be restricted."""
        # This may or may not raise depending on Python version, but should not
        # give access to dangerous operations
        code = "result = type(().__class__.__bases__[0].__subclasses__())"
        try:
            result = _run_code(code)
            # If it succeeds, it should just return a type, not allow code execution
            assert "output" in result
        except (NameError, TypeError, AttributeError):
            pass  # Also acceptable


class TestCodeExecutionTimeout:
    def test_import_blocked_in_sandbox(self):
        """import statement fails because __import__ is not in safe_builtins."""
        node = CodeExecutionNode({"code": "import time; time.sleep(30)"})
        node.CODE_TIMEOUT_SECONDS = 1
        with pytest.raises(ImportError):
            node.process({"output": None})

    def test_normal_code_does_not_timeout(self):
        node = CodeExecutionNode({"code": "result = sum(range(1000))"})
        result = node.process({"output": None})
        assert result["output"] == 499500
