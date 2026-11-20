"""Saved-operation metadata produces a plan, never activation or new credit."""
from copy import deepcopy

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.transition_disposition import GROUPS, preservation_plan


def inventory():
    return {**{kind: [] for kind, _, _ in GROUPS}, 'source': {'enrollment_id': 'original'}}


def test_every_saved_record_gets_an_explicit_original_course_disposition_without_mutation():
    preview = inventory()
    for kind, reference, _ in GROUPS:
        preview[kind] = [{reference: kind, 'module_id': 'module', **({'state': 'graded'} if kind == 'pending_assessments' else {'state': 'applied'} if kind == 'saved_completion_history' else
            {'state': 'completed'} if kind == 'saved_recovery_history' else
            {'state': 'completed'} if kind == 'saved_lab_runs' else {'state': 'evaluated'} if kind == 'saved_automatic_reviews' else {})}]
    before = deepcopy(preview)
    result = preservation_plan(preview, module_titles={'module': 'Original title'})
    assert preview == before
    assert len(result['entries']) == 10
    assert all(item['module_title'] == ('Course recovery' if item['kind'] == 'saved_recovery_history' else 'Original title') for item in result['entries'])
    assert result['source_enrollment_id'] == 'original' and result['read_only'] is True
    assert result['can_activate'] is result['credit_transferred'] is False
    assert result['reconciliation_required_count'] == 1
    assert result.pop('plan_sha256') == encode(result)[1]


@pytest.mark.parametrize('kind,state,action', [
    ('saved_completion_history', 'applied', 'retain_original_result'), ('saved_completion_history', 'rejected', 'retain_original_result'),
    ('saved_completion_history', 'failed', 'retain_original_result'), ('saved_recovery_history', 'started', 'reconcile_operation'),
    ('saved_recovery_history', 'completed', 'retain_original_result'),
    ('saved_lab_runs', 'executing', 'reconcile_operation'), ('saved_lab_runs', 'uncertain', 'reconcile_operation'),
    ('saved_lab_runs', 'prepared', 'retain_unexecuted_work'), ('saved_lab_runs', 'completed', 'retain_original_result'),
    ('saved_lab_runs', 'failed', 'retain_original_result'), ('saved_automatic_reviews', 'evaluating', 'reconcile_operation'),
    ('saved_automatic_reviews', 'prepared', 'retain_unassessed_work'), ('saved_automatic_reviews', 'evaluated', 'retain_original_result'),
    ('saved_automatic_reviews', 'unavailable', 'retain_original_result'), ('pending_assessments', 'evaluating', 'reconcile_operation'),
    ('pending_assessments', 'graded', 'reconcile_operation'),
])
def test_unresolved_execution_and_assessment_are_distinct_from_preserved_work(kind, state, action):
    preview = inventory()
    reference = next(reference for key, reference, _ in GROUPS if key == kind)
    preview[kind] = [{reference: 'record', 'module_id': 'module', 'state': state, 'private_body': 'Never expose'}]
    result = preservation_plan(preview, module_titles={})
    assert result['entries'][0]['proposed_action'] == action
    assert result['reconciliation_required_count'] == (1 if action == 'reconcile_operation' else 0)
    assert 'Never expose' not in str(result)


@pytest.mark.parametrize('kind', ['saved_lab_runs', 'saved_automatic_reviews', 'pending_assessments', 'saved_completion_history', 'saved_recovery_history'])
def test_unknown_operation_states_cannot_look_safe_for_preservation(kind):
    preview = inventory()
    reference = next(reference for key, reference, _ in GROUPS if key == kind)
    preview[kind] = [{reference: 'record', 'module_id': 'module', 'state': 'unknown'}]
    with pytest.raises(CourseCatalogError, match='reconciliation'):
        preservation_plan(preview, module_titles={})
