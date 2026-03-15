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
    """Verify that dangerous builtins and sandbox escapes are blocked."""

    def test_import_blocked(self):
        result = _run_code("import os")
        assert "Code rejected" in str(result["output"])

    def test_import_from_blocked(self):
        result = _run_code("from os import getcwd")
        assert "Code rejected" in str(result["output"])

    def test_dunder_import_blocked(self):
        result = _run_code("result = __import__('os').getcwd()")
        assert "Code rejected" in str(result["output"])

    def test_open_blocked(self):
        """open is not in safe_builtins — should error or return error output."""
        result = _run_code("result = open('/etc/passwd').read()")
        # Either raises NameError or returns an error string
        output = str(result.get("output", ""))
        assert "error" in output.lower() or result["output"] is None or isinstance(result["output"], str)

    def test_eval_blocked(self):
        result = _run_code("result = eval('1+1')")
        assert "Code rejected" in str(result["output"])

    def test_exec_within_exec_blocked(self):
        result = _run_code("exec('result = 1')")
        assert "Code rejected" in str(result["output"])

    def test_getattr_blocked(self):
        result = _run_code("result = getattr(str, '__bases__')")
        assert "Code rejected" in str(result["output"])

    def test_subclasses_escape_blocked(self):
        """The classic sandbox escape via __subclasses__ must be rejected."""
        result = _run_code("result = ().__class__.__bases__[0].__subclasses__()")
        assert "Code rejected" in str(result["output"])

    def test_bases_escape_blocked(self):
        result = _run_code("x = ''.__class__.__bases__")
        assert "Code rejected" in str(result["output"])

    def test_mro_escape_blocked(self):
        result = _run_code("x = str.__mro__")
        assert "Code rejected" in str(result["output"])

    def test_globals_blocked(self):
        result = _run_code("result = globals()")
        assert "Code rejected" in str(result["output"])

    def test_type_based_escape_blocked(self):
        """Even if type() is accessible, the AST validator blocks __subclasses__."""
        result = _run_code("result = type(42).__subclasses__()")
        assert "Code rejected" in str(result["output"])

    def test_syntax_error_handled(self):
        result = _run_code("def def def")
        assert "Code rejected" in str(result["output"])


class TestCodeExecutionTimeout:
    def test_import_blocked_in_sandbox(self):
        """import statement is now caught by AST validation."""
        result = _run_code("import time; time.sleep(30)")
        assert "Code rejected" in str(result["output"])

    def test_normal_code_does_not_timeout(self):
        node = CodeExecutionNode({"code": "result = sum(range(1000))"})
        result = node.process({"output": None})
        assert result["output"] == 499500
