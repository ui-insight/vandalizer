"""The "earlier_steps" input source: a step reads every step before it.

Support ticket: chat built Extract → Summarize → Compliance check → Format, and
the memo came back as "{{FAIN Award Number}}", "{{Grand Total Award Amount}}",
… because the Format step read only the compliance check's text.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflow_engine import (
    DocumentNode,
    FormatNode,
    Node,
    WorkflowEngine,
    _build_combined_context,
    _resolve_input_sources,
)

EXTRACTED = {"FAIN Award Number": "G26AC00033", "Grand Total Award Amount": "$330,000.00"}


class _Fixed(Node):
    """A step whose output is fixed, standing in for an extraction or model step."""

    def __init__(self, name, output):
        super().__init__(name)
        self.output = output

    def process(self, inputs):
        return {"output": self.output, "input": inputs.get("output"), "step_name": self.name}


def _memo_chain(format_sources):
    engine = WorkflowEngine()
    nodes = [
        DocumentNode({"doc_uuids": ["noa-1"]}),
        _Fixed("Extract NOA fields", [EXTRACTED]),
        _Fixed("Summarize", "A three-year USGS cooperative agreement."),
        _Fixed("Compliance check", "F&A certification is required."),
        FormatNode({"format_template": "NOA Summary – {{FAIN Award Number}}", "input_sources": format_sources}),
    ]
    for node in nodes:
        engine.add_node(node)
    for a, b in zip(nodes, nodes[1:]):
        engine.connect(a, b)
    return engine


def _format_input(engine, **execute_kwargs) -> str:
    seen = {}

    def fake_format(model, prompt, text, **kwargs):
        seen["text"] = text
        return prompt, "memo"

    with patch("app.services.workflow_engine.format_model", side_effect=fake_format):
        engine.execute(**execute_kwargs)
    return seen["text"]


def test_a_format_step_reading_earlier_steps_sees_the_extraction():
    text = _format_input(_memo_chain(["earlier_steps"]))
    assert "G26AC00033" in text and "$330,000.00" in text
    assert "A three-year USGS cooperative agreement." in text
    assert "F&A certification is required." in text
    # Each section is labeled with its step; the trigger's document ids are not content.
    assert "=== Step: Extract NOA fields ===" in text
    assert "=== Step: Compliance check ===" in text
    assert "noa-1" not in text


def test_step_input_still_means_only_the_previous_step():
    text = _format_input(_memo_chain(["step_input"]))
    assert text == "F&A certification is required."


def test_a_resumed_pass_gets_the_steps_it_skipped():
    # Resuming at the format step (index 4): the earlier steps come from the
    # saved run, as the approval and retry resumes replay them.
    text = _format_input(
        _memo_chain(["earlier_steps"]),
        start_index=4,
        initial_output={"output": "F&A certification is required."},
        prior_steps=[
            {"name": "Extract NOA fields", "output": [EXTRACTED]},
            {"name": "Summarize", "output": "A three-year USGS cooperative agreement."},
            {"name": "Compliance check", "output": "F&A certification is required."},
        ],
    )
    assert "G26AC00033" in text
    assert "A three-year USGS cooperative agreement." in text


def test_outside_a_run_the_step_input_stands_in():
    # The editor's "test this step" has sample input but no earlier steps.
    assert _build_combined_context({}, {"output": "sample"}, ["earlier_steps"]) == "sample"


def test_step_input_alongside_earlier_steps_is_not_read_twice():
    assert _resolve_input_sources({"input_sources": ["step_input", "earlier_steps"]}) == ["earlier_steps"]


@pytest.mark.asyncio
async def test_chat_wires_a_later_format_step_to_every_earlier_step():
    from app.services.chat_tools import create_workflow
    from tests.test_chat_tools import _make_context

    fake_wf = MagicMock()
    fake_wf.id = "wf-noa"
    steps = [
        {"name": "Extract NOA", "type": "extraction", "extractions": ["FAIN Award Number"]},
        {"name": "Summarize", "type": "summarize"},
        {"name": "Memo", "type": "format", "format_template": "NOA Summary – {{FAIN Award Number}}"},
    ]
    with patch("app.services.workflow_service.create_workflow", new_callable=AsyncMock, return_value=fake_wf), \
         patch("app.services.workflow_service.add_step", new_callable=AsyncMock, return_value={"id": "s1"}), \
         patch("app.services.workflow_service.add_task", new_callable=AsyncMock, return_value={"id": "t1"}) as add_task:
        await create_workflow(_make_context(), "NOA Budget & Profile Summary", steps, confirmed=True)

    sources = [c.kwargs["data"]["input_sources"] for c in add_task.await_args_list]
    assert sources == [["workflow_documents"], ["step_input"], ["earlier_steps"]]
