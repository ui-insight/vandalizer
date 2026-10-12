"""Whole-rubric synthetic controls; no live judge or release-readiness claim."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services.certification_versions import automatic_review
from app.services.certification_versions.automatic_review import review_packet
from app.services.certification_versions.outcomes import OutcomeContract
from app.services.certification_versions.review_calibration import ReviewCalibrationSuite, run_review_calibration

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'
CONTRACT = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
SUITES = tuple(ReviewCalibrationSuite.model_validate_json(path.read_bytes())
               for path in sorted(DRAFT.glob('*-review-calibration.json')))
CONFIG = {'available_models': [{'name': 'synthetic-judge'}]}


@pytest.fixture(autouse=True)
def forbid_live_judge(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail('Offline calibration tests must never call a live judge')
    monkeypatch.setattr(automatic_review, '_call_model', forbidden)


def verdict_response(payload, expected):
    data = json.loads(payload)
    evidence = {item['kind']: item for item in data['evidence']}
    return {'outcomes': [
        {'outcome_id': outcome['id'], 'verdict': expected[outcome['id']],
         'explanation': 'Synthetic control for testing measurement, not an independent quality judgment.',
         'revision_instruction': '' if expected[outcome['id']] == 'supported' else
             'Reopen the cited saved record and resolve the specific unsupported decision before reassessment.',
         'citations': [{'evidence_id': evidence[kind]['id'], 'quote': evidence[kind]['text'][:2000]}
                       for kind in outcome['evidence']]}
        for outcome in data['requirements']]}


def test_every_structured_review_module_has_one_unique_authored_suite():
    required = {module.module_id for module in CONTRACT.modules
                if any(outcome.method == 'structured_review' for outcome in module.outcomes)}
    assert {suite.module_id for suite in SUITES} == required
    assert len(SUITES) == len(required)
    assert len({suite.suite_id for suite in SUITES}) == len(SUITES)


@pytest.mark.parametrize('suite', SUITES, ids=lambda suite: suite.module_id)
def test_authored_controls_are_complete_distinct_model_level_packets(suite):
    suite.verify_contract(CONTRACT)
    packets = set()
    for case in suite.cases:
        outcomes, evidence, digest = review_packet(CONTRACT, suite.module_id, case.evidence)
        assert digest not in packets, 'Different expected verdicts must not reuse identical evidence'
        packets.add(digest)
        present = {item.kind for item in evidence}
        assert all(set(outcome.evidence) <= present for outcome in outcomes), 'Controls must reach the judge'
    hostile = next(case for case in suite.cases if case.id == 'source_instructions_cannot_change_grading')
    assert any(verdict != 'supported' for verdict in hostile.expected.values())
    if suite.module_id != 'foundations':
        # Injection is the only change to an already failing packet. Its labels
        # cannot reward source text that attempts to impersonate rubric authority.
        original = suite.cases[1]
        assert hostile.expected == original.expected
        modified = 0
        for before, after in zip(original.evidence, hostile.evidence, strict=True):
            assert (before.id, before.kind) == (after.id, after.kind)
            old, new = json.loads(before.text), json.loads(after.text)
            if old != new:
                assert after.kind != 'learner_decision'
                assert new.pop('untrusted_source_text')
                assert new == old
                modified += 1
        assert modified == 1


@pytest.mark.parametrize('suite', SUITES, ids=lambda suite: suite.module_id)
async def test_exact_packet_oracle_matches_without_awarding_credit(suite):
    expected = {json.dumps([item.model_dump(mode='json') for item in case.evidence], sort_keys=True): case.expected
                for case in suite.cases}
    async def model(name, config, payload):
        key = json.dumps(json.loads(payload)['evidence'], sort_keys=True)
        return verdict_response(payload, expected[key])
    call = AsyncMock(side_effect=model)
    result = await run_review_calibration(CONTRACT, suite, model_name='synthetic-judge', system_config=CONFIG, call_model=call)
    assert call.await_count == len(suite.cases)
    assert result['all_cases_matched'] is True
    assert result['false_support_count'] == result['false_rejection_count'] == result['unavailable_cases'] == 0
    assert result['release_ready'] is result['credit_awarded'] is False
    assert all(row['review_result']['staff_review_required'] is False for row in result['cases'])
    assert all(row['review_result']['module_completion_eligible'] is False for row in result['cases'])


@pytest.mark.parametrize('suite', SUITES, ids=lambda suite: suite.module_id)
@pytest.mark.parametrize('fixed_verdict', ['supported', 'contradicted'])
async def test_biased_judge_detects_false_passes_and_false_rejections(suite, fixed_verdict):
    async def model(name, config, payload):
        return verdict_response(payload, {outcome['id']: fixed_verdict for outcome in json.loads(payload)['requirements']})
    call = AsyncMock(side_effect=model)
    result = await run_review_calibration(CONTRACT, suite, model_name='synthetic-judge', system_config=CONFIG, call_model=call)
    assert call.await_count == len(suite.cases)
    # A broken timestamp order is contradicted in code, so a biased judge cannot pass it.
    vetoed = {(case.id, outcome_id) for case in suite.cases
              for outcome_id in automatic_review.ordering_violations(*review_packet(CONTRACT, suite.module_id, case.evidence)[:2])}
    expected_false_support = sum(v != 'supported' and (case.id, outcome_id) not in vetoed
                                 for case in suite.cases for outcome_id, v in case.expected.items())
    expected_false_rejection = sum(v == 'supported' for case in suite.cases for v in case.expected.values())
    assert result['false_support_count'] == (expected_false_support if fixed_verdict == 'supported' else 0)
    assert result['false_rejection_count'] == (expected_false_rejection if fixed_verdict == 'contradicted' else 0)
    assert result['unavailable_cases'] == 0
    assert result['all_cases_matched'] is result['release_ready'] is result['credit_awarded'] is False


@pytest.mark.parametrize('suite', SUITES, ids=lambda suite: suite.module_id)
async def test_unavailable_judge_is_not_a_learner_rejection(suite):
    call = AsyncMock(side_effect=RuntimeError('synthetic provider outage'))
    result = await run_review_calibration(CONTRACT, suite, model_name='synthetic-judge', system_config=CONFIG, call_model=call)
    assert call.await_count == len(suite.cases) * automatic_review.REVIEW_ATTEMPTS
    assert result['unavailable_cases'] == len(suite.cases)
    assert result['false_support_count'] == result['false_rejection_count'] == 0
    assert result['all_cases_matched'] is result['release_ready'] is result['credit_awarded'] is False
