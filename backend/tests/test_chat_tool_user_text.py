"""Text a chat tool returns for the user must not name tools.

A tool result's "message" can appear on the chat card word for word, and an
approval card shows "preview" as is. Support ticket: users read "check
progress with get_optimization_run" and "Save … (498 chars)". Instructions
meant for the model go in another field, such as "next_step" or "hint".
"""

import ast
import pathlib
import re

from app.services import chat_tools

USER_FACING_KEYS = {"message", "preview"}
SOURCES = [
    pathlib.Path(chat_tools.__file__),
    pathlib.Path(chat_tools.__file__).with_name("chat_workflow_tools.py"),
]
TOOL_NAMES = {t.__name__ for t in chat_tools.TOOLS}


def _user_facing_strings(path: pathlib.Path):
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value in USER_FACING_KEYS:
                text = "".join(
                    n.value for n in ast.walk(value)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                )
                yield f"{path.name}:{node.lineno}", text


def test_user_facing_tool_text_names_no_tool():
    found = [
        (where, name)
        for where, text in (s for p in SOURCES for s in _user_facing_strings(p))
        for name in TOOL_NAMES
        if re.search(rf"\b{re.escape(name)}\b", text)
    ]
    assert found == []


def test_user_facing_tool_text_states_no_character_counts():
    found = [
        where
        for where, text in (s for p in SOURCES for s in _user_facing_strings(p))
        if re.search(r"\bchars\b", text)
    ]
    assert found == []
