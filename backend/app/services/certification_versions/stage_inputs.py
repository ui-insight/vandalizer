"""What the workflow engine hands a lab stage, rebuilt for receipts and their checks.

A stage that reads "All Earlier Steps" receives every earlier stage's output as
well as the previous one. Runtimes record the context from these inputs and
checkpoint validation rebuilds them from saved receipts, so a recorded context
always matches what the provider actually consumed.
"""

from collections.abc import Collection, Mapping, Sequence

STAGE_SOURCES = {'step_input', 'workflow_documents', 'select_document', 'earlier_steps'}


def reads_previous_stage(sources: Collection[str]) -> bool:
    """Earlier steps include the previous stage, so either source connects it."""
    return 'step_input' in sources or 'earlier_steps' in sources


def stage_inputs(upstream: dict, sources: Collection[str], history: Sequence[Mapping]) -> dict:
    from app.services.workflow_engine import EARLIER_STEPS_KEY
    if 'earlier_steps' not in sources:
        return upstream
    return {**upstream, EARLIER_STEPS_KEY: [dict(item) for item in history]}


def history_entry(name: str, output: object) -> dict:
    """The engine's record of one finished stage: its name and output value."""
    return {'name': name, 'output': output.get('output') if isinstance(output, dict) else None}


def saved_history(plan: dict, results: Sequence[dict]) -> list[dict]:
    """The engine's earlier-steps list, rebuilt from the plan and saved stage results."""
    return [history_entry('Document', {'output': [plan['source_document_id']]})] + [
        history_entry(plan['engine_steps'][index + 1]['name'], result) for index, result in enumerate(results)]
