"""AST-based validation for user-submitted code before exec()."""

import ast

FORBIDDEN_ATTRIBUTES = frozenset({
    "__subclasses__",
    "__bases__",
    "__mro__",
    "__class__",
    "__import__",
    "__globals__",
    "__code__",
    "__builtins__",
    "__qualname__",
    "__module__",
    "__dict__",
    "__init_subclass__",
    "__set_name__",
    "__reduce__",
    "__reduce_ex__",
    "__getattr__",
    "__setattr__",
    "__delattr__",
})

FORBIDDEN_NAMES = frozenset({
    "exec",
    "eval",
    "compile",
    "__import__",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "vars",
    "dir",
    "breakpoint",
    "exit",
    "quit",
    "memoryview",
    "bytearray",
    "classmethod",
    "staticmethod",
    "property",
    "super",
    "object",
    "__build_class__",
})


def validate_sandbox_code(code: str) -> None:
    """Parse *code* and reject patterns that could escape the sandbox.

    Raises ``ValueError`` with a description if forbidden patterns are found.
    Raises ``SyntaxError`` if the code cannot be parsed.
    """
    tree = ast.parse(code)

    for node in ast.walk(tree):
        # Block dangerous attribute access (e.g. x.__subclasses__)
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
            raise ValueError(f"Forbidden attribute access: {node.attr}")

        # Block dangerous bare names (e.g. eval(...))
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            raise ValueError(f"Forbidden name: {node.id}")

        # Block import statements entirely
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("Import statements are not allowed")
