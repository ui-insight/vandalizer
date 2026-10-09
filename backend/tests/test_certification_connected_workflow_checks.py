"""Execution credit evidence is one actual chain, not unrelated activity."""
from copy import deepcopy
import json

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.connected_workflow_checks import check_connected_execution, compare_connected_runs
from app.services.certification_versions.connected_workflow_runtime import execute_approved_chain
from app.services.certification_versions.outcomes import OutcomeContract
from tests.test_certification_connected_workflow_plan import DRAFT, RUNTIME
from tests.test_certification_connected_workflow_runtime import approved_run, providers


def completed_run(monkeypatch, *, original=False, second=False, empty=False, mutate_snapshot=None):
    identity = {'snapshot_id': 'e' * 32, 'run_id': 'f' * 32, 'decision_id': 'a' * 32} if second else {}
    case, run = approved_run(original=original, mutate_snapshot=mutate_snapshot, **identity)
    _, _, formatter = providers(monkeypatch)
    formatter.side_effect = lambda model, instructions, context, **kwargs: ('provider prompt', '' if empty else 'Rendered: ' + json.dumps(context))
    events = []
    output = execute_approved_chain(run, case, RUNTIME, checkpoint=lambda event, digest: events.append({
        'receipt': event, 'receipt_sha256': digest}), should_stop=lambda: False)
    run['state'] = 'completed'
    run['stage_events'] = events
    run['result'] = {key: value for key, value in output.items() if key != 'stage_receipts'} | {
        'stage_event_count': 6, 'stage_events_sha256': encode(events)[1],
        'stage_receipt_sha256s': [item['receipt_sha256'] for item in output['stage_receipts']]}
    return case, run


def contract():
    return OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())


@pytest.mark.parametrize('original,empty,expected', [(False, False, True), (True, False, False), (False, True, False)])
def test_one_chain_is_checked_independently_of_source_accuracy_or_learner_credit(monkeypatch, original, empty, expected):
    case, run = completed_run(monkeypatch, original=original, empty=empty)
    result = check_connected_execution(contract(), case, run)
    assert result['passed'] is expected
    assert result['credit_awarded'] is result['module_completion_eligible'] is False
    assert result['run_id'] == run['run_id'] and result['result_sha256'] == encode(run['result'])[1]


@pytest.mark.parametrize('change', ['state', 'source', 'artifact', 'approval', 'case', 'context', 'stage_run', 'final_output',
    'terminal_stages', 'other_stage_receipt', 'input_snapshot'])
def test_mixed_or_corrupt_run_evidence_is_not_a_grade(monkeypatch, change):
    case, run = completed_run(monkeypatch)
    if change == 'state':
        run['state'] = 'failed'
    elif change == 'source':
        run['plan']['input_snapshot']['documents'][0]['source_sha256'] = 'f' * 64
    elif change == 'artifact':
        run['plan']['input_snapshot']['artifact_sha256'] = 'f' * 64
    elif change == 'approval':
        run['authorization']['decision']['submission']['choice'] = 'hold'
    elif change == 'case':
        run['plan']['case_sha256'] = 'f' * 64
    elif change == 'context':
        run['stage_events'][4]['receipt']['consumed_context']['value'] = 'Unrelated historical analysis'
    elif change == 'stage_run':
        run['stage_events'][1]['receipt']['run_id'] = '0' * 32
    elif change == 'final_output':
        run['result']['final_output'] = 'Unrelated historical result'
    elif change == 'terminal_stages':
        run['result']['stage_receipt_sha256s'] = []
    elif change == 'other_stage_receipt':
        run['stage_events'][3] = deepcopy(run['stage_events'][1])
    else:
        run['plan']['input_snapshot_sha256'] = 'f' * 64
    with pytest.raises(CourseCatalogError):
        check_connected_execution(contract(), case, run)


def test_changed_outcome_requires_a_reviewed_checker(monkeypatch):
    case, run = completed_run(monkeypatch)
    design = contract().model_dump(mode='json')
    next(outcome for module in design['modules'] for outcome in module['outcomes']
         if outcome['id'] == 'multi_step.connected_execution')['statement'] += ' Changed requirement.'
    with pytest.raises(CourseCatalogError, match='matching verified checker'):
        check_connected_execution(OutcomeContract.model_validate(design), case, run)


def test_comparison_reports_actual_revision_context_and_output_changes(monkeypatch):
    case, original = completed_run(monkeypatch, original=True)
    _, corrected = completed_run(monkeypatch, second=True)
    comparison = compare_connected_runs(case, original, corrected)
    assert comparison['configuration_changed'] is True
    assert comparison['original_formatter_rereads_source'] is True
    assert comparison['corrected_formatter_receives_reasoning'] is True
    assert comparison['original_final_output'] != comparison['corrected_final_output']
    assert comparison['original_result_sha256'] == encode(original['result'])[1]
    assert comparison['corrected_result_sha256'] == encode(corrected['result'])[1]


def test_comparison_cannot_count_the_same_execution_twice(monkeypatch):
    case, run = completed_run(monkeypatch)
    with pytest.raises(CourseCatalogError, match='two owned revisions'):
        compare_connected_runs(case, run, run)


def test_two_real_identical_configurations_are_visible_as_no_repair(monkeypatch):
    case, original = completed_run(monkeypatch)
    _, corrected = completed_run(monkeypatch, second=True)
    comparison = compare_connected_runs(case, original, corrected)
    assert comparison['configuration_changed'] is False
    assert comparison['original_formatter_rereads_source'] is False


@pytest.mark.parametrize('change', ['actor', 'workflow', 'source', 'ingestion'])
def test_comparison_rejects_two_individually_valid_but_unrelated_runs(monkeypatch, change):
    import hashlib
    case, original = completed_run(monkeypatch, original=True)

    def alter(snapshot):
        if change == 'actor':
            snapshot['user_id'] = snapshot['artifact']['workflow']['user_id'] = 'another-learner'
        elif change == 'workflow':
            snapshot['artifact_id'] = snapshot['artifact']['workflow']['id'] = 'f' * 24
        elif change == 'source':
            snapshot['documents'][0]['document_id'] = 'f' * 32
        else:
            snapshot['documents'][0]['text'] = 'Different ingested text from the same assigned bytes.'
            snapshot['documents'][0]['text_sha256'] = hashlib.sha256(snapshot['documents'][0]['text'].encode()).hexdigest()

    _, corrected = completed_run(monkeypatch, second=True, mutate_snapshot=alter)
    assert check_connected_execution(contract(), case, corrected)['passed'] is True
    with pytest.raises(CourseCatalogError, match='two owned revisions'):
        compare_connected_runs(case, original, corrected)
