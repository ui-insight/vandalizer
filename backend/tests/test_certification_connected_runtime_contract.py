"""The assigned repair must exercise the product's actual input semantics."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from app.services import workflow_engine


@pytest.mark.parametrize('step_sources,task_sources,override,expected_source', [
    (['workflow_documents'], ['workflow_documents'], False, 'source'),
    (['step_input'], ['step_input'], False, 'reasoning'),
    (['workflow_documents'], ['step_input'], False, 'source'),
    (['workflow_documents'], ['step_input'], True, 'reasoning'),
])
def test_formatter_repair_uses_real_step_precedence_and_captured_context(monkeypatch, step_sources, task_sources, override, expected_source):
    source_text = 'Synthetic assigned subaward. Financial and technical reports have distinct terms.'
    reasoning = 'Internal analysis: preserve the separate source terms; institutional comparison remains unresolved.'
    extraction = Mock(return_value={'raw': [{'Reporting terms': 'distinct'}], 'formatted': 'Distinct reporting terms'})
    reason = Mock(return_value=reasoning)
    formatter = Mock(return_value=('Synthetic formatting prompt', 'Synthetic final internal draft'))
    monkeypatch.setattr(workflow_engine, 'data_extraction_model', extraction)
    monkeypatch.setattr(workflow_engine, 'llm_chat_model', reason)
    monkeypatch.setattr(workflow_engine, 'format_model', formatter)
    stages = [
        {'name': 'Document', 'data': {'doc_uuids': ['assigned-source']}, 'tasks': []},
        {'name': 'Extract terms', 'data': {'input_sources': ['workflow_documents']}, 'tasks': [
            {'name': 'Extraction', 'data': {'extractions': ['Reporting terms'], 'doc_texts': [source_text]}}]},
        {'name': 'Reason over terms', 'data': {'input_sources': ['step_input']}, 'tasks': [
            {'name': 'Prompt', 'data': {'prompt': 'Keep facts separate from interpretation.', 'doc_texts': [source_text]}}]},
        {'name': 'Format internal draft', 'data': {'input_sources': step_sources}, 'tasks': [
            {'name': 'Formatter', 'data': {'format_template': 'Preserve the evidence and unresolved issues.',
                'input_sources': task_sources, 'override_step_input': override, 'doc_texts': [source_text]}}]},
    ]
    engine = workflow_engine.build_workflow_engine(deepcopy(stages), 'synthetic-model', user_id='synthetic-learner', system_config_doc={})
    updates = []
    final, receipts = engine.execute(workflow_result_updater=updates.append)
    assert final == 'Synthetic final internal draft'
    assert len(receipts) == 4
    assert extraction.call_count == reason.call_count == formatter.call_count == 1
    assert extraction.call_args.kwargs['doc_texts'] == [source_text]
    actual_context = formatter.call_args.args[2]
    assert actual_context == (source_text if expected_source == 'source' else reasoning)
    assert any('steps_output.Extract_terms' in update for update in updates)
    assert any('steps_output.Reason_over_terms' in update for update in updates)
    assert any('steps_output.Format_internal_draft' in update for update in updates)
