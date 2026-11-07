import json
from pathlib import Path

from pydantic import ValidationError
import pytest

from app.services.certification_versions.outcomes import OutcomeContract

DATA = Path(__file__).resolve().parents[1] / 'certification-data'


@pytest.fixture
def design():
    return json.loads((DATA / 'drafts/v5.0/outcomes.json').read_text())


def test_draft_covers_every_module_with_traceable_teaching_and_calibration(design):
    contract = OutcomeContract.model_validate(design)
    contract.verify_teaching_references(json.loads((DATA / 'lessons.json').read_text()))
    assert len(contract.modules) == 11
    assert len(contract.required_outcomes()) == 33
    assert all(outcome.teaching_status == 'authored' for module in contract.modules for outcome in module.outcomes)
    implemented = {outcome.id for module in contract.modules for outcome in module.outcomes if outcome.assessment_status == 'implemented'}
    expected = {outcome.id for module in contract.modules for outcome in module.outcomes if module.module_id in ('foundations', 'extraction_engine', 'process_mapping', 'workflow_design', 'multi_step', 'advanced_nodes', 'output_delivery', 'validation_qa', 'batch_processing', 'governance') or outcome.method == 'scenario_choice'}
    assert implemented == expected and len(implemented) == 33
    assert all(outcome.assessment_status != 'verified' for module in contract.modules for outcome in module.outcomes)


def test_authored_outcomes_have_real_draft_lesson_replacements(design):
    contract = OutcomeContract.model_validate(design)
    drafts = {draft['module_id']: draft for draft in (json.loads(path.read_text()) for path in (DATA / 'drafts/v5.0').glob('*-teaching.json'))}
    assert sum(len(draft['replacements']) for draft in drafts.values()) == 74
    for module in contract.modules:
        replaced = {lesson['id'] for lesson in drafts[module.module_id]['replacements']}
        assert all(set(outcome.lesson_ids) <= replaced for outcome in module.outcomes)


@pytest.mark.parametrize('all_implemented', [False, True])
def test_unverified_design_cannot_claim_release_readiness(design, all_implemented):
    if all_implemented:
        for module in design['modules']:
            for outcome in module['outcomes']:
                outcome['assessment_status'] = 'implemented'
    design['state'] = 'release_candidate'
    with pytest.raises(ValidationError, match='verified assessments'):
        OutcomeContract.model_validate(design)


@pytest.mark.parametrize('mutation', ['missing_failure', 'duplicate_case', 'wrong_module', 'duplicate_outcome', 'empty_evidence', 'unknown_field'])
def test_rejects_ambiguous_or_incomplete_assessment_contract(design, mutation):
    first = design['modules'][0]['outcomes'][0]
    if mutation == 'missing_failure':
        first['calibration'][1]['expected'] = 'pass'
    elif mutation == 'duplicate_case':
        first['calibration'][1]['id'] = first['calibration'][0]['id']
    elif mutation == 'wrong_module':
        first['id'] = 'foundations.source_support'
    elif mutation == 'duplicate_outcome':
        design['modules'][0]['outcomes'].append(first)
    elif mutation == 'empty_evidence':
        first['evidence'] = []
    else:
        first['award_from_agent_assertion'] = True
    with pytest.raises(ValidationError):
        OutcomeContract.model_validate(design)


@pytest.mark.parametrize('mutation', ['missing_module', 'missing_lesson', 'foreign_lesson'])
def test_rejects_missing_or_cross_module_teaching_links(design, mutation):
    lessons = json.loads((DATA / 'lessons.json').read_text())
    if mutation == 'missing_module':
        del lessons['foundations']
    else:
        design['modules'][0]['outcomes'][0]['lesson_ids'] = [
            'missing-lesson' if mutation == 'missing_lesson' else lessons['foundations']['lessons'][0]['id']
        ]
    with pytest.raises(ValueError):
        OutcomeContract.model_validate(design).verify_teaching_references(lessons)
