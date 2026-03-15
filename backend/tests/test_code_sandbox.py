"""Tests for AST-based code sandbox validation."""

import pytest

from app.utils.code_sandbox import validate_sandbox_code


class TestValidateSandboxCode:
    def test_allows_safe_code(self):
        validate_sandbox_code("result = len([1, 2, 3])")

    def test_allows_loops_and_comprehensions(self):
        validate_sandbox_code("result = [x * 2 for x in range(10)]")

    def test_allows_json_usage(self):
        validate_sandbox_code('result = json.dumps({"a": 1})')

    def test_allows_regex(self):
        validate_sandbox_code('result = re.sub(r"\\d+", "X", data)')

    def test_blocks_import(self):
        with pytest.raises(ValueError, match="Import statements"):
            validate_sandbox_code("import os")

    def test_blocks_from_import(self):
        with pytest.raises(ValueError, match="Import statements"):
            validate_sandbox_code("from os import system")

    def test_blocks_dunder_import(self):
        with pytest.raises(ValueError, match="Forbidden name"):
            validate_sandbox_code("__import__('os')")

    def test_blocks_eval(self):
        with pytest.raises(ValueError, match="Forbidden name"):
            validate_sandbox_code("eval('1+1')")

    def test_blocks_exec(self):
        with pytest.raises(ValueError, match="Forbidden name"):
            validate_sandbox_code("exec('x = 1')")

    def test_blocks_getattr(self):
        with pytest.raises(ValueError, match="Forbidden name"):
            validate_sandbox_code("getattr(str, 'mro')")

    def test_blocks_globals(self):
        with pytest.raises(ValueError, match="Forbidden name"):
            validate_sandbox_code("globals()")

    def test_blocks_subclasses_attr(self):
        with pytest.raises(ValueError, match="Forbidden attribute"):
            validate_sandbox_code("x = ().__class__.__subclasses__()")

    def test_blocks_bases_attr(self):
        with pytest.raises(ValueError, match="Forbidden attribute"):
            validate_sandbox_code("x = str.__bases__")

    def test_blocks_mro_attr(self):
        with pytest.raises(ValueError, match="Forbidden attribute"):
            validate_sandbox_code("x = str.__mro__")

    def test_blocks_class_attr(self):
        with pytest.raises(ValueError, match="Forbidden attribute"):
            validate_sandbox_code("x = ''.__class__")

    def test_blocks_globals_attr(self):
        with pytest.raises(ValueError, match="Forbidden attribute"):
            validate_sandbox_code("x = func.__globals__")

    def test_blocks_builtins_attr(self):
        with pytest.raises(ValueError, match="Forbidden attribute"):
            validate_sandbox_code("x = func.__builtins__")

    def test_blocks_code_attr(self):
        with pytest.raises(ValueError, match="Forbidden attribute"):
            validate_sandbox_code("x = func.__code__")

    def test_syntax_error_raised(self):
        with pytest.raises(SyntaxError):
            validate_sandbox_code("def def def")

    def test_blocks_compile(self):
        with pytest.raises(ValueError, match="Forbidden name"):
            validate_sandbox_code("compile('x=1', '<str>', 'exec')")

    def test_blocks_breakpoint(self):
        with pytest.raises(ValueError, match="Forbidden name"):
            validate_sandbox_code("breakpoint()")
