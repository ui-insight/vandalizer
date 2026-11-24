import copy
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.certification_versions.cohort_inventory import InventoryChanged, PROJECTIONS, classify, inventory


def fixture():
    data = {kind: [] for kind in PROJECTIONS}
    data['progress'] = [{'_id': 'p', 'user_id': 'learner', 'modules': [], 'total_xp': 0}]
    return data


def enrolled(data, *, certified=False):
    data['progress'][0].update(enrollment_id='e', course_version='course-1', certified=certified)
    data['enrollments'] = [{'uuid': 'e', 'user_id': 'learner', 'progress_id': 'p', 'course_version': 'course-1', 'provenance': 'new_enrollment', 'state': 'completed' if certified else 'active'}]
    data['selections'] = [{'user_id': 'learner', 'active_enrollment_id': 'e', 'in_flight_writes': 0}]
    return data


@pytest.mark.parametrize('selected,pending,credit', [(False, False, 0), (True, True, 0), (True, False, 0), (False, False, 10)])
def test_prepared_courses_are_separate_from_started_work_and_pending_confirmation(selected, pending, credit):
    data = enrolled(fixture())
    data['progress'].append({'_id': 'prepared-progress', 'user_id': 'learner', 'enrollment_id': 'prepared',
        'course_version': 'course-2', 'modules': [], 'total_xp': credit})
    data['enrollments'].append({'uuid': 'prepared', 'user_id': 'learner', 'progress_id': 'prepared-progress',
        'course_version': 'course-2', 'provenance': 'explicit_upgrade', 'state': 'prepared'})
    if selected:
        data['selections'][0].update(active_enrollment_id='prepared', has_pending_transition=pending)
    report = classify(data)
    assert report['flags_distinct_users']['has_prepared_course'] == 1
    assert report['cohorts']['inconsistent'] == int(bool(credit) or (selected and not pending))
    assert report['flags_distinct_users'].get('selection_confirmation_pending', 0) == int(pending)
    assert 'unknown_enrollment_state' not in report['flags_distinct_users']


@pytest.mark.parametrize('changes,cohort,flag', [
    ({}, 'unstarted_record', 'unknown_historical_version'),
    ({'total_xp': 125}, 'active', 'unknown_historical_version'),
    ({'has_position': True}, 'active', 'unknown_historical_version'),
    ({'has_lab': True}, 'active', 'unknown_historical_version'),
    ({'modules': [{'attempts': 1}]}, 'active', 'unknown_historical_version'),
    ({'modules': [{'has_answers': True}]}, 'active', 'unfinished_answers'),
    ({'pending_credential': True}, 'active', 'pending_credential'),
    ({'certified': True}, 'completed', 'credential_needs_preservation'),
    ({'unlocked': True}, 'unstarted_record', 'prerequisite_override'),
    ({'invalid_modules': True}, 'inconsistent', 'invalid_module_records'),
    ({'modules': [{'invalid': True}]}, 'inconsistent', 'invalid_module_records'),
    ({'last_activity_date': 'not-a-date'}, 'inconsistent', 'invalid_activity_date'),
])
def test_cohorts_use_saved_evidence_without_inventing_achievement(changes, cohort, flag):
    data = fixture()
    data['progress'][0].update(changes)
    result = classify(data)
    assert result['cohorts'][cohort] == 1
    assert sum(result['cohorts'].values()) == 1
    assert result['flags_distinct_users'][flag] == 1
    assert result['migration_authorized'] is False


@pytest.mark.parametrize('damage,flag', [
    ('duplicate_legacy', 'duplicate_legacy_progress'),
    ('missing_progress', 'missing_or_unowned_progress'),
    ('foreign_selection', 'missing_or_unowned_selection'),
    ('missing_selection', 'missing_selection'),
    ('duplicate_selection', 'duplicate_selection'),
    ('identity_mismatch', 'progress_identity_mismatch'),
    ('shared_progress', 'shared_progress_record'),
    ('orphan_progress', 'orphan_versioned_progress'),
    ('write_marker', 'write_marker_mismatch'),
    ('completed_state', 'completion_state_mismatch'),
])
def test_inconsistent_records_are_counted_without_choosing_or_repairing_them(damage, flag):
    data = enrolled(fixture())
    if damage == 'duplicate_legacy':
        data['progress'] = [dict(data['progress'][0], _id=str(i), enrollment_id=None) for i in range(2)]
    elif damage == 'missing_progress':
        data['enrollments'][0]['progress_id'] = 'missing'
    elif damage == 'foreign_selection':
        data['selections'][0]['active_enrollment_id'] = 'someone-else'
    elif damage == 'missing_selection':
        data['selections'] = []
    elif damage == 'duplicate_selection':
        data['selections'] *= 2
    elif damage == 'identity_mismatch':
        data['progress'][0]['course_version'] = 'wrong'
    elif damage == 'shared_progress':
        data['enrollments'].append(dict(data['enrollments'][0], uuid='other'))
    elif damage == 'orphan_progress':
        data['progress'].append(dict(data['progress'][0], _id='unbound'))
    elif damage == 'write_marker':
        data['selections'][0]['has_write'] = True
    elif damage == 'completed_state':
        data['enrollments'][0]['state'] = 'completed'
    before = copy.deepcopy(data)
    report = classify(data)
    assert report['cohorts']['inconsistent'] == 1
    assert report['flags_distinct_users'][flag] == 1
    assert data == before


def test_saved_history_and_selected_cohort_are_separate():
    data = enrolled(fixture())
    data['progress'].append({'_id': 'history', 'user_id': 'learner', 'certified': True, 'modules': []})
    data['enrollments'].append({'uuid': 'old', 'user_id': 'learner', 'progress_id': 'history', 'course_version': 'old-course', 'provenance': 'legacy_version_unknown', 'state': 'completed'})
    data['credentials'].append({'user_id': 'learner', 'enrollment_id': 'old'})
    data['attempts'].append({'user_id': 'learner', 'enrollment_id': 'old', 'state': 'applied'})
    report = classify(data)
    assert report['cohorts']['unstarted_record'] == 1
    assert report['flags_distinct_users']['has_completed_history'] == 1
    assert 'credential_needs_preservation' not in report['flags_distinct_users']
    assert report['selected_course_counts'] == {'course-1': 1}


def test_work_and_activity_report_redacts_identity_and_counts_users_once():
    data = enrolled(fixture())
    data['progress'][0]['last_activity_date'] = '2026-10-05'
    data['lab_executions'] = [{'user_id': 'learner', 'enrollment_id': 'e', 'state': state} for state in ('executing', 'uncertain')]
    data['review_attempts'] = [{'user_id': 'learner', 'enrollment_id': 'e', 'state': 'unavailable'}]
    data['progress'].append({'_id': 'private-record', 'user_id': None})
    result = classify(data)
    assert result['flags_distinct_users']['unresolved_lab_executions'] == 1
    assert result['flags_distinct_users']['unresolved_review_attempts'] == 1
    assert result['record_counts']['lab_executions'] == 2
    assert result['records_with_missing_owner'] == {'progress': 1}
    assert result['last_activity']['latest'] == '2026-10-05'
    assert 'learner' not in json.dumps({k: v for k, v in result.items() if k not in ('record_counts', 'limits')})
    assert 'private-record' not in json.dumps(result)


@pytest.mark.asyncio
async def test_changed_read_produces_no_report():
    first = fixture()
    second = copy.deepcopy(first)
    second['progress'][0]['total_xp'] = 125
    with patch('app.services.certification_versions.cohort_inventory.read_metadata', AsyncMock(side_effect=[first, second])):
        with pytest.raises(InventoryChanged):
            await inventory(object())


@pytest.mark.asyncio
async def test_matching_reads_are_not_claimed_as_transaction_snapshot():
    with patch('app.services.certification_versions.cohort_inventory.read_metadata', AsyncMock(return_value=fixture())):
        report = await inventory(object())
    assert len(report['metadata_sha256']) == 64
    assert report['consistency'] == 'equal_metadata_in_two_reads_not_a_transactional_snapshot'


@pytest.mark.parametrize('changes', [{'total_xp': -1}, {'total_xp': '125'}, {'certified': 'yes'}, {'unlocked': 1}])
def test_invalid_saved_values_are_not_treated_as_unstarted(changes):
    data = fixture()
    data['progress'][0].update(changes)
    report = classify(data)
    assert report['cohorts']['inconsistent'] == 1
    assert report['flags_distinct_users']['invalid_progress_values'] == 1


def test_in_flight_initial_work_is_active_even_before_progress_is_saved():
    data = enrolled(fixture())
    data['selections'][0].update(in_flight_writes=1, has_write=True)
    report = classify(data)
    assert report['cohorts']['active'] == 1
    assert report['flags_distinct_users']['write_in_flight'] == 1


@pytest.mark.parametrize('kind', ['attempts', 'lab_executions', 'review_attempts', 'recoveries'])
def test_unknown_work_state_is_visible_as_inconsistent(kind):
    data = enrolled(fixture())
    data[kind].append({'user_id': 'learner', 'enrollment_id': 'e', 'state': 'unknown'})
    report = classify(data)
    assert report['cohorts']['inconsistent'] == 1
    assert report['flags_distinct_users']['unknown_' + kind + '_state'] == 1


@pytest.mark.parametrize('kind', ['process_submissions', 'workflow_design_submissions'])
def test_process_designs_are_inventory_metadata_not_transferred_competence(kind):
    data = enrolled(fixture())
    data[kind] = [{'user_id': 'learner', 'enrollment_id': 'e'}]
    result = classify(data)
    assert result['flags_distinct_users']['saved_' + kind] == 1
    assert result['migration_authorized'] is False
    assert set(PROJECTIONS[kind]) == {'_id', 'user_id', 'enrollment_id'}
    data[kind][0]['enrollment_id'] = 'unowned-course'
    assert classify(data)['flags_distinct_users']['orphan_or_unowned_' + kind] == 1
