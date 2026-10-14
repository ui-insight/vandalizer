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
    # A declared record marked unavailable is forced to unclear, so it cannot be a false pass either.
    def caught(case):
        outcomes, evidence = review_packet(CONTRACT, suite.module_id, case.evidence)[:2]
        return {**automatic_review.availability_gaps(outcomes, evidence), **automatic_review.ordering_violations(outcomes, evidence)}
    vetoed = {(case.id, outcome_id) for case in suite.cases for outcome_id in caught(case)}
    expected_false_support = sum(v != 'supported' and (case.id, outcome_id) not in vetoed
                                 for case in suite.cases for outcome_id, v in case.expected.items())
    expected_false_rejection = sum(v == 'supported' for case in suite.cases for v in case.expected.values())
    assert result['false_support_count'] == (expected_false_support if fixed_verdict == 'supported' else 0)
    assert result['false_rejection_count'] == (expected_false_rejection if fixed_verdict == 'contradicted' else 0)
    assert result['unavailable_cases'] == 0
    assert result['all_cases_matched'] is result['release_ready'] is result['credit_awarded'] is False


def test_a_send_that_ran_before_approval_is_contradicted_in_code():
    # A live judge once excused this case; the timestamp order now decides it.
    suite = next(suite for suite in SUITES if suite.module_id == 'workflow_design')
    for case in suite.cases:
        outcomes, evidence = review_packet(CONTRACT, suite.module_id, case.evidence)[:2]
        vetoed = automatic_review.ordering_violations(outcomes, evidence)
        if case.id == 'external_send_before_review':
            assert vetoed['workflow_design.approval_boundary']['verdict'] == 'contradicted'
        if case.expected.get('workflow_design.approval_boundary') == 'supported':
            assert 'workflow_design.approval_boundary' not in vetoed, case.id


@pytest.mark.parametrize('suite', SUITES, ids=lambda suite: suite.module_id)
async def test_unavailable_judge_is_not_a_learner_rejection(suite):
    call = AsyncMock(side_effect=RuntimeError('synthetic provider outage'))
    result = await run_review_calibration(CONTRACT, suite, model_name='synthetic-judge', system_config=CONFIG, call_model=call)
    assert call.await_count == len(suite.cases)
    assert result['unavailable_cases'] == len(suite.cases)
    assert result['false_support_count'] == result['false_rejection_count'] == 0
    assert result['all_cases_matched'] is result['release_ready'] is result['credit_awarded'] is False


def unavailable_case(module_id, case_id):
    suite = next(suite for suite in SUITES if suite.module_id == module_id)
    return next(case for case in suite.cases if case.id == case_id)


@pytest.mark.parametrize('module_id, case_id', [
    ('advanced_nodes', 'calculation_record_unreadable'), ('extraction_engine', 'source_check_record_unavailable'),
    ('governance', 'supervision_record_unavailable'), ('multi_step', 'stage_review_record_unavailable'),
    ('output_delivery', 'retry_receipt_unavailable'), ('validation_qa', 'retest_receipt_unavailable'),
    ('batch_processing', 'pilot_quality_unavailable'), ('process_mapping', 'method_rationale_unavailable'),
    ('workflow_design', 'approval_time_unavailable')])
async def test_a_lost_record_cannot_support_its_outcome_even_from_an_always_passing_judge(module_id, case_id):
    case = unavailable_case(module_id, case_id)
    async def model(name, config, payload):
        return verdict_response(payload, {o['id']: 'supported' for o in json.loads(payload)['requirements']})
    result = await automatic_review.evaluate_draft_structured_review(
        CONTRACT, module_id, [item.model_dump(mode='json') for item in case.evidence],
        model_name='synthetic-judge', system_config=CONFIG, call_model=model)
    actual = {item['outcome_id']: item['verdict'] for item in result['outcomes']}
    assert actual == case.expected
    assert result['passed'] is False
    gap = next(item for item in result['outcomes'] if item['verdict'] == 'unclear')
    assert gap['revision_instruction'] == automatic_review.UNAVAILABLE_REVISION


async def test_a_lost_record_keeps_a_contradiction_the_judge_found_elsewhere():
    case = unavailable_case('extraction_engine', 'source_check_record_unavailable')
    async def model(name, config, payload):
        return verdict_response(payload, {'extraction_engine.field_semantics': 'supported',
                                          'extraction_engine.quality_repair': 'contradicted'})
    result = await automatic_review.evaluate_draft_structured_review(
        CONTRACT, 'extraction_engine', [item.model_dump(mode='json') for item in case.evidence],
        model_name='synthetic-judge', system_config=CONFIG, call_model=model)
    assert {item['outcome_id']: item['verdict'] for item in result['outcomes']}['extraction_engine.quality_repair'] == 'contradicted'


async def test_available_records_leave_the_judge_verdict_alone():
    suite = next(suite for suite in SUITES if suite.module_id == 'extraction_engine')
    for case in suite.cases:
        if 'unavailable' in json.dumps([item.model_dump(mode='json') for item in case.evidence]):
            continue
        outcomes, evidence = review_packet(CONTRACT, 'extraction_engine', [item.model_dump(mode='json') for item in case.evidence])[:2]
        assert automatic_review.availability_gaps(outcomes, evidence) == {}
