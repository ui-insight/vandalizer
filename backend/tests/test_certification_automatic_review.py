"""Transport/schema/evidence boundaries; these do not calibrate an actual LLM."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.services.certification_versions.automatic_review import AutomaticReviewPolicy, evaluate_draft_structured_review
from app.services.certification_versions.outcomes import OutcomeContract

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'
CONTRACT = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
MODULE = next(module for module in CONTRACT.modules if module.module_id == 'foundations')
REQUIRED = [outcome for outcome in MODULE.outcomes if outcome.method == 'structured_review']
CONFIG = {'available_models': [{'name': 'synthetic-judge', 'api_key': 'private-key'}]}


def packet():
    return [{'id': kind, 'kind': kind, 'text': f'Synthetic saved evidence for {kind}.'}
            for kind in sorted({kind for outcome in REQUIRED for kind in outcome.evidence})]


def decisions(evidence=None):
    by_kind = {item['kind']: item for item in evidence or packet()}
    return {'outcomes': [{'outcome_id': outcome.id, 'verdict': 'supported',
        'explanation': 'Synthetic judgment for boundary testing only.', 'revision_instruction': '',
        'citations': [{'evidence_id': by_kind[kind]['id'], 'quote': by_kind[kind]['text']} for kind in outcome.evidence]}
        for outcome in REQUIRED]}


async def review(evidence=None, model=None, config=None):
    return await evaluate_draft_structured_review(CONTRACT, 'foundations', packet() if evidence is None else evidence,
        model_name='synthetic-judge', system_config=CONFIG if config is None else config,
        call_model=model or AsyncMock(return_value=decisions()))


def test_selected_policy_has_no_staff_fallback_and_rejects_policy_drift():
    policy = AutomaticReviewPolicy.model_validate_json((DRAFT / 'assessment-policy.json').read_bytes())
    assert policy.staff_queue_enabled is False
    with pytest.raises(ValidationError):
        AutomaticReviewPolicy(staff_queue_enabled=True)


async def test_missing_required_evidence_returns_learner_revision_without_model_or_staff():
    model = AsyncMock()
    result = await review([], model)
    assert result['status'] == 'revision_required'
    assert result['passed'] is False
    assert result['staff_review_required'] is False
    assert result['credit_awarded'] is False
    assert all(item['revision_instruction'] and 'missing' in item['explanation'] for item in result['outcomes'])
    model.assert_not_called()


async def test_supported_judgment_cites_required_saved_evidence_but_does_not_complete_module():
    model = AsyncMock(return_value=decisions())
    result = await review(model=model)
    assert result['status'] == 'requirements_supported'
    assert result['passed'] is True
    assert result['module_completion_eligible'] is False
    assert result['credit_awarded'] is False
    assert result['staff_review_required'] is False
    assert result['assessed_outcome_ids'] == [outcome.id for outcome in REQUIRED]
    assert 'foundations.executed_extraction' not in result['assessed_outcome_ids']
    assert 'private-key' not in json.dumps(result)
    payload = json.loads(model.call_args.args[2])
    assert payload['evidence'] == packet()
    assert {item['id'] for item in payload['requirements']} == {item.id for item in REQUIRED}


@pytest.mark.parametrize('verdict', ['unclear', 'contradicted'])
async def test_one_unmet_outcome_requires_revision_even_when_all_other_outcomes_are_supported(verdict):
    response = decisions()
    response['outcomes'][0].update(verdict=verdict,
        revision_instruction='Check the assigned document and record which field definition needs correction.')
    result = await review(model=AsyncMock(return_value=response))
    assert result['status'] == 'revision_required'
    assert result['passed'] is False
    assert result['outcomes'][0]['verdict'] == verdict
    assert result['staff_review_required'] is False


@pytest.mark.parametrize('mutation', ['missing_outcome', 'duplicate_outcome', 'foreign_outcome', 'fabricated_quote',
                                     'foreign_reference', 'missing_kind', 'empty_revision', 'extra_credit', 'contradictory_revision'])
async def test_invalid_model_output_is_a_retryable_grader_problem_not_a_learner_failure(mutation):
    response = decisions()
    first = response['outcomes'][0]
    if mutation == 'missing_outcome':
        response['outcomes'].pop()
    elif mutation == 'duplicate_outcome':
        response['outcomes'].append(first)
    elif mutation == 'foreign_outcome':
        first['outcome_id'] = 'governance.accountable_handoff'
    elif mutation == 'fabricated_quote':
        first['citations'][0]['quote'] = 'This evidence does not exist.'
    elif mutation == 'foreign_reference':
        first['citations'][0]['evidence_id'] = 'foreign-learner-source'
    elif mutation == 'missing_kind':
        first['citations'].pop()
    elif mutation == 'empty_revision':
        first['verdict'] = 'unclear'
    elif mutation == 'extra_credit':
        response['credit_awarded'] = True
    else:
        first['revision_instruction'] = 'This supposedly supported outcome actually requires correction.'
    result = await review(model=AsyncMock(return_value=response))
    assert result['status'] == 'grading_unavailable'
    assert result['passed'] is None
    assert result['retryable'] is True
    assert result['credit_awarded'] is False
    assert result['outcomes'] == []


async def test_provider_exception_does_not_expose_source_or_credentials_or_send_to_staff():
    result = await review(model=AsyncMock(side_effect=RuntimeError('private-key and private source text')))
    assert result['status'] == 'grading_unavailable'
    assert result['passed'] is None
    assert result['staff_review_required'] is False
    assert 'private' not in json.dumps(result)


async def test_timeout_is_retryable_and_cancellation_propagates():
    async def slow(*args):
        await asyncio.sleep(1)
    with patch('app.services.certification_versions.automatic_review.REVIEW_TIMEOUT_SECONDS', 0.001):
        result = await review(model=slow)
    assert result['status'] == 'grading_unavailable'
    with pytest.raises(asyncio.CancelledError):
        await review(model=AsyncMock(side_effect=asyncio.CancelledError))


async def test_unknown_judge_does_not_fall_back_to_a_different_model():
    model = AsyncMock()
    result = await review(model=model, config={'available_models': [{'name': 'some-other-model'}]})
    assert result['status'] == 'grading_unavailable'
    assert result['model_called'] is False
    model.assert_not_called()


@pytest.mark.parametrize('mutation', ['duplicate', 'irrelevant_kind', 'oversized'])
async def test_bad_evidence_packets_are_rejected_before_model_dispatch(mutation):
    evidence = packet()
    model = AsyncMock()
    if mutation == 'duplicate':
        evidence.append(evidence[0])
    elif mutation == 'irrelevant_kind':
        evidence[0]['kind'] = 'unrelated_private_document'
    else:
        evidence[0]['text'] = 'x' * 30_001
    with pytest.raises(ValueError):
        await review(evidence, model)
    model.assert_not_called()


async def test_snapshot_and_reviewer_fingerprints_change_with_the_requirements():
    initial = await review()
    evidence = packet()
    evidence[0]['text'] += ' Changed source.'
    changed = await review(evidence, AsyncMock(return_value=decisions(evidence)))
    assert initial['evidence_sha256'] != changed['evidence_sha256']
    config = {'available_models': [{'name': 'synthetic-judge', 'api_key': 'rotated-key'}]}
    rotated = await review(config=config)
    assert initial['reviewer'] == rotated['reviewer']
    config['available_models'][0]['endpoint'] = 'https://example.invalid/different-routing'
    rerouted = await review(config=config)
    assert initial['reviewer']['runtime_config_sha256'] != rerouted['reviewer']['runtime_config_sha256']


async def test_recognition_only_module_cannot_be_sent_to_the_structured_judge():
    with pytest.raises(ValueError, match='no declared'):
        await evaluate_draft_structured_review(CONTRACT, 'ai_literacy', [], model_name='synthetic-judge', system_config=CONFIG)


async def test_actual_agent_adapter_uses_structured_output_without_action_tools():
    from pydantic_ai.models.test import TestModel
    from app.services.certification_versions.automatic_review import _call_model
    test_model = TestModel(custom_output_args=decisions())
    with patch('app.services.llm_service.get_agent_model', return_value=test_model):
        result = await _call_model('synthetic-judge', CONFIG, '{}')
    assert len(result.outcomes) == len(REQUIRED)
    assert test_model.last_model_request_parameters.function_tools == []
