"""Stored stage evidence cannot substitute contexts or rewrite a predecessor."""
from copy import deepcopy

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.connected_workflow_checkpoints import decode_checkpoints
from app.services.certification_versions.connected_workflow_runtime import execute_approved_chain
from tests.test_certification_connected_workflow_runtime import approved_run, providers
from tests.test_certification_connected_workflow_plan import RUNTIME


def stored_events(monkeypatch):
    case, run = approved_run()
    providers(monkeypatch)
    events = []
    execute_approved_chain(run, case, RUNTIME, checkpoint=lambda receipt, digest: events.append({
        'receipt': receipt, 'receipt_sha256': digest}), should_stop=lambda: False)
    return run, events


def raw_log(events):
    serialized, digest = encode(events)
    return {'stage_events_json': serialized, 'stage_events_sha256': digest, 'stage_event_count': len(events)}


@pytest.mark.parametrize('length', range(7))
def test_read_preserves_each_durable_prefix_including_an_incomplete_stage(monkeypatch, length):
    run, events = stored_events(monkeypatch)
    assert decode_checkpoints(raw_log(events[:length]), run) == events[:length]


@pytest.mark.parametrize('change', ['source_context', 'upstream', 'previous', 'start_link', 'stage', 'result_type',
    'authorization', 'credit', 'run', 'kind', 'count', 'order', 'digest', 'prepared', 'incomplete_completed'])
def test_rehashed_checkpoint_log_cannot_change_evidence_bindings(monkeypatch, change):
    run, original = stored_events(monkeypatch)
    events = deepcopy(original)
    if change == 'source_context':
        events[0]['receipt']['consumed_context']['documents'][0]['text'] = 'Different source'
    elif change == 'upstream':
        events[2]['receipt']['upstream_result_sha256'] = 'f' * 64
    elif change == 'previous':
        events[2]['receipt']['previous_stage_receipt_sha256'] = 'f' * 64
    elif change == 'start_link':
        events[1]['receipt']['started_receipt_sha256'] = 'f' * 64
    elif change == 'stage':
        events[0]['receipt']['stage']['requested_model'] = 'unapproved-model'
    elif change == 'result_type':
        events[1]['receipt']['result']['step_name'] = 'APICall'
    elif change == 'authorization':
        events[0]['receipt']['authorization_sha256'] = 'f' * 64
    elif change == 'credit':
        events[0]['receipt']['credit_awarded'] = True
    elif change == 'run':
        events[0]['receipt']['run_id'] = 'f' * 32
    elif change == 'kind':
        events[0]['receipt']['kind'] = 'completed_run'
    elif change == 'order':
        events[0], events[1] = events[1], events[0]
    elif change == 'prepared':
        run['state'] = 'prepared'
    elif change == 'incomplete_completed':
        run['state'] = 'completed'
        events = events[:2]
    for item in events:
        item['receipt_sha256'] = encode(item['receipt'])[1]
    raw = raw_log(events)
    if change == 'count':
        raw['stage_event_count'] -= 1
    elif change == 'digest':
        raw['stage_events_sha256'] = 'f' * 64
    with pytest.raises(CourseCatalogError):
        decode_checkpoints(raw, run)


def test_completed_run_requires_all_six_checkpoints(monkeypatch):
    run, events = stored_events(monkeypatch)
    run['state'] = 'completed'
    assert decode_checkpoints(raw_log(events), run) == events
    with pytest.raises(CourseCatalogError):
        decode_checkpoints({}, run)
