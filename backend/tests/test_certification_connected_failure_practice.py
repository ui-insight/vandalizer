"""The disclosed rehearsal retains actual work and cannot imply model success."""
from copy import deepcopy

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.connected_failure_practice import (
    approval_question, ControlledTrainingStop, PRACTICE_CONSENT, stopped_stage_result,
)
from app.services.certification_versions.connected_workflow_checkpoints import decode_checkpoints
from app.services.certification_versions.connected_workflow_runtime import execute_approved_chain
from app.services.certification_versions.enrollments import EnrollmentConflict
from tests.test_certification_connected_workflow_runtime import approved_run, providers
from tests.test_certification_connected_workflow_plan import RUNTIME
from tests.test_certification_connected_workflow_checkpoints import raw_log


def rehearsal(monkeypatch, sink=None):
    case, run = approved_run(failure_practice=True)
    mocks = providers(monkeypatch)
    events = []

    def checkpoint(receipt, digest):
        if sink:
            sink(receipt)
        events.append({'receipt': receipt, 'receipt_sha256': digest})

    with pytest.raises(ControlledTrainingStop):
        execute_approved_chain(run, case, RUNTIME, checkpoint=checkpoint, should_stop=lambda: False)
    return case, run, mocks, events


def test_training_rejection_preserves_actual_successful_extraction_and_exact_failed_boundary(monkeypatch):
    case, run, (extract, reason, formatter), events = rehearsal(monkeypatch)
    assert extract.call_count == 1 and reason.call_count == formatter.call_count == 0
    assert len(events) == 4
    assert events[1]['receipt']['result']['output'] == {'Amount': '$185,000'}
    assert events[2]['receipt']['consumed_context']['value'] == {'Amount': '$185,000'}
    assert events[3]['receipt']['result'] == stopped_stage_result()
    assert decode_checkpoints(raw_log(events), run) == events
    assert case.controlled_failure_practice.notice in run['authorization']['decision']['prompt']['prompt']


@pytest.mark.parametrize('change', ['pretend_provider_called', 'invent_output', 'success', 'wrong_stage', 'remove_marker'])
def test_training_checkpoint_cannot_be_rehashed_into_a_different_actual_result(monkeypatch, change):
    _, run, _, events = rehearsal(monkeypatch)
    event = events[-1]['receipt']
    if change == 'pretend_provider_called':
        event['result']['provider_dispatched'] = True
    elif change == 'invent_output':
        event['result']['output'] = 'Invented model output'
    elif change == 'success':
        event['status'] = 'completed'
        event['result'].pop('error')
    elif change == 'wrong_stage':
        event['stage_index'] = 2
    else:
        event['result'].pop('training_stop')
    events[-1]['receipt_sha256'] = encode(event)[1]
    with pytest.raises(CourseCatalogError):
        decode_checkpoints(raw_log(events), run)


def test_saved_rejection_is_required_before_the_worker_claims_a_controlled_stop(monkeypatch):
    def lost_sink(receipt):
        if receipt['kind'] == 'stage_completed' and receipt['stage_index'] == 1:
            raise EnrollmentConflict('The rejection could not be saved')
    with pytest.raises(EnrollmentConflict, match='could not be saved'):
        rehearsal(monkeypatch, lost_sink)


def test_older_case_does_not_silently_gain_a_training_rejection():
    case, _ = approved_run()
    original = deepcopy(case.public_definition())
    original.pop('controlled_failure_practice')
    assert approval_question(original, 'prepare_connected_workflow_plan') == original['questions'][0]
    with pytest.raises(EnrollmentConflict, match='original course'):
        approval_question(original, PRACTICE_CONSENT)
