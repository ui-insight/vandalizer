"""A tool call sent back for a retry is shown as failed, with the reason.

Support ticket: "Run the QA Subaward Quick Check workflow on the attached
subaward" showed a first "Running workflow" card as "Completed · Started",
though no run started; chat then listed workflows and tried again. The
model passed the workflow's name as its id, Beanie's id validation raised,
and pydantic-ai turned that into a retry prompt, which was streamed as if it
were the tool's result.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, Tool
from pydantic_ai.models.function import DeltaToolCall, FunctionModel

from app.services import chat_tools
from tests.test_chat_output import chat_harness as chat_harness


class _Id(BaseModel):
    id: int


def _agent(tool, args='{"workflow_id":"QA Subaward Quick Check"}'):
    calls = []

    async def respond(messages, info):
        if not calls:
            calls.append(1)
            yield {0: DeltaToolCall(name="run_workflow", json_args=args)}
        else:
            yield "I couldn't start it."

    return Agent(FunctionModel(stream_function=respond), tools=[Tool(tool, name="run_workflow")])


async def _results(chat_harness, agent):
    chunks = await chat_harness.run(agent, message="Run the QA Subaward Quick Check workflow.")
    return [c["content"] for c in chunks if c["kind"] == "tool_result"]


async def test_a_validation_error_inside_the_tool_streams_as_an_error(chat_harness):
    async def run_workflow(workflow_id: str):
        _Id.model_validate({"id": workflow_id})  # what Beanie's Workflow.get does with a name
        return {"status": "started"}

    [content] = await _results(chat_harness, _agent(run_workflow))
    assert isinstance(content, dict)
    assert content["error"].startswith("Invalid request — id:")
    # The saved reply carries the same failed result, so a reload shows it too.
    saved = chat_harness.finalize.call_args.kwargs["tool_results"]
    assert "error" in saved[0]["content"]


async def test_a_model_retry_streams_its_message_as_the_error(chat_harness):
    async def run_workflow(workflow_id: str):
        raise ModelRetry("Workflow 'QA Subaward Quick Check' not found; call list_workflows.")

    [content] = await _results(chat_harness, _agent(run_workflow))
    assert "not found; call list_workflows" in content["error"]


async def test_arguments_that_fail_validation_name_the_field(chat_harness):
    async def run_workflow(workflow_id: str, confirmed: bool):
        return {"status": "started"}

    [content] = await _results(chat_harness, _agent(run_workflow, args='{"workflow_id": 5}'))
    assert "Invalid request" in content["error"] and "confirmed" in content["error"]


async def test_a_successful_result_is_unchanged(chat_harness):
    async def run_workflow(workflow_id: str):
        return {"status": "started", "activity_id": "a1"}

    assert await _results(chat_harness, _agent(run_workflow)) == [{"status": "started", "activity_id": "a1"}]


async def test_run_workflow_given_a_name_says_not_found_and_how_to_fix_it(monkeypatch):
    monkeypatch.setattr(chat_tools, "_resolve_requested_model", AsyncMock(return_value=(None, None)))
    context = SimpleNamespace(deps=SimpleNamespace(context_document_uuids=["doc-1"], team_id=None, user_id="u"))
    out = await chat_tools.run_workflow(context, workflow_id="QA Subaward Quick Check", confirmed=True)
    assert "not found" in out["error"] and "list_workflows" in out["hint"]
