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


async def test_an_invalid_response_is_a_technical_failure_without_an_automatic_second_call():
    bad = decisions()
    bad['outcomes'][0]['citations'][0]['quote'] = 'Fields stitched together from several places.'
    model = AsyncMock(side_effect=[bad, decisions()])
    result = await review(model=model)
    assert result['status'] == 'grading_unavailable'
    assert model.await_count == 1


def timed_packet(approved_at, started_at):
    evidence = packet()
    texts = {'learner_decision': {'scope_review': {'approved_at': approved_at, 'approved_document_id': 'doc-A'}},
             'execution_receipt': {'run_id': 'run-A', 'started_at': started_at, 'status': 'completed'}}
    for item in evidence:
        if item['kind'] in texts:
            item['text'] = json.dumps(texts[item['kind']])
    assert {item['kind'] for item in evidence} >= set(texts)
    return evidence


async def test_approval_recorded_after_execution_is_contradicted_even_when_the_model_supports_it():
    evidence = timed_packet('2026-01-02T10:02:00Z', '2026-01-02T10:01:00Z')
    result = await review(evidence, AsyncMock(return_value=decisions(evidence)))
    assert result['status'] == 'revision_required'
    assert result['passed'] is False
    scoped = next(item for item in result['outcomes'] if item['outcome_id'] == 'foundations.scoped_proposal')
    assert scoped['verdict'] == 'contradicted'
    assert {c['quote'] for c in scoped['citations']} == {'2026-01-02T10:02:00Z', '2026-01-02T10:01:00Z'}
    assert 'before you start the run' in scoped['revision_instruction']
    others = [item for item in result['outcomes'] if item['outcome_id'] != 'foundations.scoped_proposal']
    assert others and all(item['verdict'] == 'supported' for item in others)


@pytest.mark.parametrize('approved_at, started_at', [
    ('2026-01-02T10:00:00Z', '2026-01-02T10:01:00Z'),
    ('2026-01-02T10:01:00Z', '2026-01-02T10:01:00Z'),
    ('2026-01-02T10:02:00', '2026-01-02T10:01:00Z'),
    ('not a time', '2026-01-02T10:01:00Z'),
])
async def test_ordering_check_leaves_timely_or_unreadable_approval_to_the_model(approved_at, started_at):
    evidence = timed_packet(approved_at, started_at)
    result = await review(evidence, AsyncMock(return_value=decisions(evidence)))
    assert result['status'] == 'requirements_supported'


def test_ordering_check_must_enforce_a_declared_critical_failure():
    raw = json.loads((DRAFT / 'outcomes.json').read_text())
    outcome = next(o for m in raw['modules'] for o in m['outcomes'] if o['id'] == 'foundations.scoped_proposal')
    outcome['ordering_checks'][0]['critical_failure'] = 'A failure the rubric never declared.'
    with pytest.raises(ValidationError):
        OutcomeContract.model_validate(raw)


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
        result = await _call_model('synthetic-judge', CONFIG, adapter_payload())
    assert len(result.outcomes) == len(REQUIRED)
    assert test_model.last_model_request_parameters.function_tools == []


def adapter_payload():
    return json.dumps({'requirements': [outcome.model_dump(mode='json') for outcome in REQUIRED], 'evidence': packet()})


@pytest.mark.parametrize('fixed_on_retry', [True, False])
async def test_agent_adapter_lets_the_model_repair_a_misquoted_citation_once(fixed_on_retry):
    from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from app.services.certification_versions.automatic_review import _call_model
    bad = decisions()
    bad['outcomes'][0]['citations'][0]['quote'] = 'Fields stitched together from several places.'
    seen = []

    def reply(messages, info):
        retries = [part for message in messages for part in getattr(message, 'parts', []) if isinstance(part, RetryPromptPart)]
        seen.append([str(part.content) for part in retries])
        args = decisions() if retries and fixed_on_retry else bad
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

    with patch('app.services.llm_service.get_agent_model', return_value=FunctionModel(reply)):
        if fixed_on_retry:
            result = await _call_model('synthetic-judge', CONFIG, adapter_payload())
            assert len(result.outcomes) == len(REQUIRED)
        else:
            with pytest.raises(Exception):
                await _call_model('synthetic-judge', CONFIG, adapter_payload())
    assert len(seen) == 2
    assert 'not an exact contiguous span' in seen[1][0]
    assert 'Fields stitched' not in seen[1][0]



async def test_agent_adapter_names_the_evidence_kind_a_supported_verdict_left_uncited():
    # A vague "cite every kind" retry let the live judge repeat the omission;
    # the retry must name the outcome, the kind and where that kind lives.
    from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from app.services.certification_versions.automatic_review import _call_model
    bad = decisions()
    outcome = bad['outcomes'][0]
    dropped = outcome['citations'].pop()['evidence_id']
    seen = []

    def reply(messages, info):
        retries = [part for message in messages for part in getattr(message, 'parts', []) if isinstance(part, RetryPromptPart)]
        seen.append([str(part.content) for part in retries])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, decisions() if retries else bad)])

    with patch('app.services.llm_service.get_agent_model', return_value=FunctionModel(reply)):
        result = await _call_model('synthetic-judge', CONFIG, adapter_payload())
    assert len(result.outcomes) == len(REQUIRED) and len(seen) == 2
    assert outcome['outcome_id'] in seen[1][0] and f'cite {dropped} evidence' in seen[1][0]
    assert repr(dropped) in seen[1][0]


@pytest.mark.parametrize('quote,accepted', [
    ('"actual_value":"177000"', True),           # nested JSON read without escape backslashes
    ('Total Budget: $1,250,000', True),          # escaped line break read as a space
    ('"actual_value":"185000"', False),          # a changed value is still fabricated
    ('Total Budget: $1,350,000', False)])
async def test_quotes_match_json_evidence_as_a_person_reads_it(quote, accepted):
    # Evidence records are JSON with JSON nested in strings; the live judge
    # quoted their readable form and every honest packet came back unavailable.
    inner = json.dumps({'actual_value': '177000', 'page': 'Total Budget:\n$1,250,000'}, separators=(',', ':'))
    evidence = packet()
    evidence[0]['text'] = json.dumps({'record_json': inner}, separators=(',', ':'))
    answer = decisions(evidence)
    for outcome in answer['outcomes']:
        for citation in outcome['citations']:
            if citation['evidence_id'] == evidence[0]['id']:
                citation['quote'] = quote
    result = await review(evidence, AsyncMock(return_value=answer))
    assert (result['status'] == 'requirements_supported') is accepted
    assert (result['status'] == 'grading_unavailable') is not accepted

def test_grading_timeout_ends_before_the_recovery_deadline():
    from app.services.certification_versions.automatic_review import REVIEW_TIMEOUT_SECONDS
    from app.services.certification_versions.review_recovery import REVIEW_RECOVERY_SECONDS
    assert REVIEW_TIMEOUT_SECONDS < REVIEW_RECOVERY_SECONDS
