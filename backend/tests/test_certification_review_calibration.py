"""Synthetic suite and measurement tests, not live model calibration."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

from app.services.certification_versions.outcomes import OutcomeContract
from app.services.certification_versions.review_calibration import ReviewCalibrationSuite, run_review_calibration

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'
CONTRACT = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
SUITE = ReviewCalibrationSuite.model_validate_json((DRAFT / 'foundations-review-calibration.json').read_bytes())
CONFIG = {'available_models': [{'name': 'synthetic-judge'}]}


def response(payload, expected=None):
    data = json.loads(payload)
    evidence = {item['kind']: item for item in data['evidence']}
    results = []
    for outcome in data['requirements']:
        verdict = (expected or {}).get(outcome['id'], 'supported')
        results.append({'outcome_id': outcome['id'], 'verdict': verdict,
                        'explanation': 'Synthetic oracle response for harness verification.',
                        'revision_instruction': '' if verdict == 'supported' else 'Inspect and correct the missing or contradictory source review before submitting again.',
                        'citations': [{'evidence_id': evidence[kind]['id'], 'quote': evidence[kind]['text'][:2000]}
                                      for kind in outcome['evidence']]})
    return {'outcomes': results}


def test_authored_suite_covers_positive_negative_unclear_and_source_instruction_cases():
    SUITE.verify_contract(CONTRACT)
    assert len(SUITE.cases) == 6
    assert 'source_instructions_cannot_change_grading' in {case.id for case in SUITE.cases}


async def test_calibration_detects_five_false_supports_from_an_always_passing_judge():
    async def model(name, config, payload):
        return response(payload)
    result = await run_review_calibration(CONTRACT, SUITE, model_name='synthetic-judge', system_config=CONFIG, call_model=model)
    assert result['false_support_count'] == 5
    assert result['all_cases_matched'] is False
    assert result['release_ready'] is False
    assert result['credit_awarded'] is False


async def test_matching_oracle_does_not_claim_release_readiness():
    # First evidence can be shared across cases; compare the entire packet.
    expected = {json.dumps([item.model_dump(mode='json') for item in case.evidence], sort_keys=True): case.expected for case in SUITE.cases}
    async def model(name, config, payload):
        return response(payload, expected[json.dumps(json.loads(payload)['evidence'], sort_keys=True)])
    result = await run_review_calibration(CONTRACT, SUITE, model_name='synthetic-judge', system_config=CONFIG, call_model=model)
    assert result['all_cases_matched'] is True
    assert result['false_support_count'] == 0
    assert result['release_ready'] is False


async def test_unavailable_judge_is_not_counted_as_calibrated_failure_detection():
    result = await run_review_calibration(CONTRACT, SUITE, model_name='synthetic-judge', system_config=CONFIG,
                                         call_model=AsyncMock(side_effect=RuntimeError('provider failed')))
    assert result['unavailable_cases'] == 6
    assert result['all_cases_matched'] is False
    assert result['false_support_count'] == 0
