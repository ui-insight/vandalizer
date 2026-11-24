"""Every chat tool has a friendly card title.

Support ticket: chat's page-template lookup titled its activity card "find
page templates", the tool's code name: the card falls back to the name when
``TOOL_META`` in frontend/src/components/chat/toolActivity.ts has no entry.
"""

import re
from pathlib import Path

import pytest

from app.services.chat_tools import TOOLS

TOOL_ACTIVITY = Path(__file__).resolve().parents[2] / "frontend/src/components/chat/toolActivity.ts"


def _labelled() -> set[str]:
    source = TOOL_ACTIVITY.read_text()
    block = source[source.index("export const TOOL_META"):]
    block = block[: block.index("\n}\n")]
    return set(re.findall(r"^\s+([a-z_][a-z0-9_]*):\s*\{\s*label:", block, re.M))


@pytest.mark.skipif(not TOOL_ACTIVITY.exists(), reason="frontend source not present")
def test_every_chat_tool_has_a_card_label():
    missing = sorted(t.__name__ for t in TOOLS if t.__name__ not in _labelled())
    assert missing == [], f"Add a TOOL_META label in toolActivity.ts for: {missing}"


@pytest.mark.skipif(not TOOL_ACTIVITY.exists(), reason="frontend source not present")
def test_page_template_tools_have_friendly_labels():
    source = TOOL_ACTIVITY.read_text()
    assert "find_page_templates:   { label: 'Finding page templates'" in source
    assert "get_page_template:     { label: 'Reading page template'" in source
