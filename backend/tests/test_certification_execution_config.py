"""Assessed execution must honor the same applied settings as workspace runs."""
from copy import deepcopy

import pytest

from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.lab_execution import execution_plan


RUNTIME = {'available_models': [{'name': 'base-model'}, {'name': 'optimized-model'}],
           'extraction_config': {'mode': 'one_pass', 'model': 'base-model'}}


def snapshot(override):
    return {'artifact': {'domain': None,
                         'extraction_config': {'mode': 'one_pass', 'model': 'base-model', 'temperature': 0.4},
                         'extraction_config_override': override,
                         'fields': [{'searchphrase': 'PI Name'}]}}


@pytest.mark.parametrize('override,temperature', [(None, 0.4), ({}, 0.4), ({'temperature': 0.1}, 0.1)])
def test_assessed_plan_uses_applied_override_or_authored_fallback_without_mutating_saved_inputs(override, temperature):
    saved = snapshot(override)
    before = deepcopy(saved)
    plan = execution_plan(saved, deepcopy(RUNTIME))
    assert plan['effective_extraction_config']['temperature'] == temperature
    assert saved == before


def test_assessed_model_identity_follows_applied_settings():
    plan = execution_plan(snapshot({'mode': 'one_pass', 'model': 'optimized-model'}), deepcopy(RUNTIME))
    assert plan['model_info']['model'] == 'optimized-model'
    assert plan['model_names'] == ['optimized-model']


@pytest.mark.parametrize('override', [{'use_images': True}, {'mode': 'unsupported'}, {'model': 'unconfigured-model'}])
def test_unsupported_applied_settings_cannot_be_hidden_by_valid_base_settings(override):
    with pytest.raises(EnrollmentConflict):
        execution_plan(snapshot(override), deepcopy(RUNTIME))
