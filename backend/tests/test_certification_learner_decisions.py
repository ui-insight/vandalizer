"""Prompt/schema boundaries, independent of the staged persistence tests."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.services.certification_versions.learner_decisions import DecisionPrompt, DecisionSubmission, ValueCheck
from app.services.certification_versions.outcomes import OutcomeContract

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'
PROMPTS = [DecisionPrompt.model_validate(item) for item in json.loads((DRAFT / 'foundations-decisions.json').read_text())]


def test_foundations_decision_prompts_cover_structured_outcomes_and_all_five_required_values():
    contract = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
    module = next(item for item in contract.modules if item.module_id == 'foundations')
    assert {item.outcome_id for item in PROMPTS} == {item.id for item in module.outcomes if item.method == 'structured_review'}
    assert PROMPTS[0].phase == 'before_execution'
    assert PROMPTS[1].phase == 'after_execution'
    assert set(PROMPTS[1].required_fields) == {'PI Name', 'Institution', 'Total Budget', 'Project Period', 'Sponsoring Agency'}
    assert PROMPTS[0].digest != PROMPTS[0].model_copy(update={'revision': PROMPTS[0].revision + 1}).digest


@pytest.mark.parametrize('changes', [{'actor_user_id': 'learner'}, {'submitted_at': 'yesterday'}, {'passed': True}, {'reason': ' '*20}])
def test_decision_cannot_assert_provenance_grade_or_blank_explanation(changes):
    body = {'request_id': uuid4().hex, 'run_id': uuid4().hex, 'prompt_sha256': PROMPTS[0].digest,
            'choice': 'approve', 'reason': 'I compared the selected source with the assigned source.'}
    with pytest.raises(ValidationError):
        DecisionSubmission.model_validate({**body, **changes})


@pytest.mark.parametrize('changes', [{'source_quote': ''}, {'reason': ' '*20}, {'source_quote': ' '*20}])
def test_supported_value_requires_actual_quote_and_explanation(changes):
    body = {'field': 'PI Name', 'decision': 'supported', 'checked_value': 'Jane', 'source_document_id': 'source',
            'source_quote': 'PI Name: Jane', 'reason': 'I found this name in the assigned source.'}
    with pytest.raises(ValidationError):
        ValueCheck.model_validate({**body, **changes})


@pytest.mark.parametrize('changes', [{'required_fields': ['field', 'field']}, {'choices': {'approve': '', 'decline': 'Decline'}}, {'required_fields': ['field']}])
def test_invalid_scope_prompt_is_rejected(changes):
    with pytest.raises(ValidationError):
        DecisionPrompt.model_validate({**PROMPTS[0].model_dump(), **changes})


@pytest.mark.parametrize('changes', [{'execution_choice': 'unknown'}, {'phase': 'after_execution', 'execution_choice': 'approve'}])
def test_execution_choice_must_be_explicit_and_before_execution(changes):
    with pytest.raises(ValidationError):
        DecisionPrompt.model_validate({**PROMPTS[0].model_dump(), **changes})
