"""Approval-card button labels are plain words, and the preview carries them.

Support ticket: approving a paused workflow from chat, the reply said "Click
Approve approve workflow step to proceed", and rejecting showed a button
labelled "Approve reject workflow step". The backend's label table had no
entry for either tool, so it fell back to "Approve <tool name>".
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import chat_tools

SERVICES = Path(chat_tools.__file__).parent


def _gated_tool_names() -> set[str]:
    """Every tool_name passed to _confirm_gate anywhere in the services."""
    names: set[str] = set()
    for path in SERVICES.glob("*.py"):
        source = path.read_text()
        for call in re.finditer(r"_confirm_gate\((.*?)\n\s*\)", source, re.DOTALL):
            names.update(re.findall(r'tool_name="([a-z_]+)"', call.group(1)))
    return names


def test_every_gated_tool_has_a_plain_label():
    names = _gated_tool_names()
    assert {"approve_workflow_step", "reject_workflow_step", "run_workflow"} <= names
    missing = sorted(n for n in names if n not in chat_tools._APPROVE_BUTTON_LABELS)
    assert missing == [], f"add approval labels for {missing}"
    for name in names:
        label = chat_tools.approve_button_label(name)
        assert "_" not in label, (name, label)
        assert label != f"Approve {name.replace('_', ' ')}", (name, label)


def test_workflow_review_labels():
    assert chat_tools.approve_button_label("approve_workflow_step") == "Approve and continue"
    assert chat_tools.approve_button_label("reject_workflow_step") == "Reject run"


class _Conversation:
    pending_confirmations: list = []

    async def save(self):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,label", [
    ("approve_workflow_step", "Approve and continue"),
    ("reject_workflow_step", "Reject run"),
])
async def test_preview_names_the_button_the_card_shows(tool_name, label):
    context = SimpleNamespace(deps=SimpleNamespace(conversation=_Conversation(), turn_marker=3))
    out = await chat_tools._confirm_gate(
        context, tool_name=tool_name, key={"approval": "a1"}, confirmed=False,
        preview={"action": tool_name, "preview": "Paused step", "needs_confirmation": True},
    )
    assert out is not None
    assert out["approval_label"] == label
    assert f'"{label}"' in out["assistant_instruction"]
    assert "Approve approve" not in out["assistant_instruction"]
    assert "Approve reject" not in out["assistant_instruction"]
