"""Automatic assessment chooses a stable system judge, never a chat preference."""
import pytest
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.practical_assessment import assessment_model


@pytest.mark.parametrize(('settings', 'expected'), [
    ({'validation_judge_model': 'judge', 'default_model': 'default'}, 'judge'),
    ({'default_model': 'default'}, 'default'),
    ({}, 'first'),
])
def test_assessment_model_uses_configured_judge_then_application_default(settings, expected):
    assert assessment_model({'available_models': [{'name': 'first'}, {'name': 'default'}, {'name': 'judge'}], **settings}) == expected


@pytest.mark.parametrize('settings', [
    {'available_models': []},
    {'available_models': [{'name': 'first'}], 'validation_judge_model': 'missing'},
    {'available_models': [{'name': 'first'}], 'default_model': 'missing'},
    {'available_models': [{'name': 'judge'}, {'name': 'judge'}], 'validation_judge_model': 'judge'},
])
def test_assessment_model_rejects_missing_or_ambiguous_explicit_selection(settings):
    with pytest.raises(CourseCatalogError, match='unavailable'):
        assessment_model(settings)
