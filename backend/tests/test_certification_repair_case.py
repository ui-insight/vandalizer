"""Authored repair asset integrity; no live grader or learner-credit claims."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from pydantic import ValidationError

from app.services.certification_versions.learner_decisions import DecisionPrompt
from app.services.certification_versions.outcomes import OutcomeContract
from app.services.certification_versions.repair_case import ExtractionRepairCase
from app.services.certification_versions.repair_case import load_repair_case
from app.services.certification_versions.catalog import CourseCatalogError

DRAFT = Path(__file__).resolve().parents[1] / 'certification-data/drafts/v5.0'


@pytest.fixture
def design():
    return json.loads((DRAFT / 'extraction-engine-repair.json').read_text())


def prompts():
    return [DecisionPrompt.model_validate(item) for item in json.loads((DRAFT / 'extraction-engine-decisions.json').read_text())]


def test_authored_specimen_is_distinct_from_execution_and_expected_answers(design):
    case = ExtractionRepairCase.model_validate(design)
    contract = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
    case.verify_contract(contract, prompts())
    public = case.public_definition()
    assert public['baseline']['provenance'] == 'authored_flawed_example_not_an_execution'
    assert public['baseline']['output']['Total Budget'] == '304000'
    assert public['baseline']['output']['Postdoctoral Fellow Name'] == 'Dr. Alex Morgan'
    assert 'expectations' not in public
    assert 'expected_value' not in json.dumps(public)
    assert public['case_sha256'] == case.digest
    assert all(outcome.assessment_status == 'implemented' for module in contract.modules
               if module.module_id == 'extraction_engine' for outcome in module.outcomes)


def test_source_anchors_and_absence_are_grounded_in_exact_draft_pdf(design):
    case = ExtractionRepairCase.model_validate(design)
    source = (DRAFT / 'documents' / case.source_filename).read_bytes()
    with fitz.open(stream=source, filetype='pdf') as pdf:
        texts = [page.get_text() for page in pdf]
        assert len(texts) == 2
        case.verify_source(source, texts)
    absent = next(item for item in case.expectations if item.field == 'Postdoctoral Fellow Name')
    assert absent.expected_value is None
    assert absent.absence_policy == 'absent_when_unnamed'
    with pytest.raises(ValueError, match='source bytes changed'):
        case.verify_source(source + b' ', texts)
    with pytest.raises(ValueError, match='unavailable source anchor'):
        case.verify_source(source, [texts[0].replace('1,250,000', '304,000'), texts[1]])
    with pytest.raises(ValueError, match='unavailable source anchor'):
        case.verify_source(source, texts[:1])
    legacy = DRAFT.parents[1] / 'courses/legacy-2026-10-02.1/documents' / case.source_filename
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() != case.source_sha256


@pytest.mark.parametrize('mutation', ['execution_claim', 'run_id', 'missing_field', 'duplicate_field',
                                    'no_error', 'invented_absence', 'unsupported_category', 'foreign_outcome', 'same_prompt'])
def test_rejects_misleading_or_ambiguous_repair_assets(design, mutation):
    if mutation == 'execution_claim':
        design['baseline']['provenance'] = 'actual_execution'
    elif mutation == 'run_id':
        design['baseline']['run_id'] = 'a' * 32
    elif mutation == 'missing_field':
        del design['baseline']['output']['Total Budget']
    elif mutation == 'duplicate_field':
        design['baseline']['fields'].append(deepcopy(design['baseline']['fields'][0]))
    elif mutation == 'no_error':
        design['baseline']['output'] = {item['field']: item['expected_value'] for item in design['expectations']}
    elif mutation == 'invented_absence':
        design['expectations'][1]['expected_value'] = 'Dr. Alex Morgan'
    elif mutation == 'unsupported_category':
        design['expectations'][2]['expected_value'] = 'Not applicable'
    elif mutation == 'foreign_outcome':
        design['outcome_ids'][0] = 'foundations.scoped_proposal'
    else:
        design['value_prompt_id'] = design['scope_prompt_id']
    with pytest.raises(ValidationError):
        ExtractionRepairCase.model_validate(design)


@pytest.mark.parametrize('mutation', ['missing_prompt', 'duplicate_prompt', 'wrong_outcome', 'missing_value_check', 'no_approval'])
def test_rejects_unbound_or_incomplete_decision_requirements(design, mutation):
    case = ExtractionRepairCase.model_validate(design)
    contract = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
    values = [item.model_dump(mode='json') for item in prompts()]
    if mutation == 'missing_prompt':
        values.pop()
    elif mutation == 'duplicate_prompt':
        values.append(values[0])
    elif mutation == 'wrong_outcome':
        values[0]['outcome_id'] = 'extraction_engine.quality_repair'
    elif mutation == 'missing_value_check':
        values[1]['required_fields'].pop()
    else:
        values[0]['execution_choice'] = None
    with pytest.raises(ValueError):
        case.verify_contract(contract, [DecisionPrompt.model_validate(item) for item in values])


@pytest.mark.parametrize('mutation', [None, 'missing_case', 'old_source', 'wrong_assignment', 'wrong_module', 'wrong_prompt',
                                    'legacy_counts', 'exposed_answers', 'case_reference'])
def test_package_binding_rejects_wrong_source_or_requirements(design, monkeypatch, mutation):
    from app.services.certification_versions import learner_decisions, outcomes
    contract = OutcomeContract.model_validate_json((DRAFT / 'outcomes.json').read_bytes())
    assets = {'repair-cases/extraction_engine.json': design,
              'exercises.json': {'extraction_engine': json.loads((DRAFT / 'extraction-engine-exercise.json').read_text())},
              'decisions/extraction_engine.json': [item.model_dump(mode='json') for item in prompts()]}
    package = SimpleNamespace(manifest=SimpleNamespace(artifacts={
        'repair-cases/extraction_engine.json': 'a' * 64,
        'documents/nih-r01-neuroscience.pdf': design['source_sha256']}), json=assets.__getitem__)
    monkeypatch.setattr(outcomes, 'package_outcomes', lambda _: contract)
    monkeypatch.setattr(learner_decisions, 'load_prompt', lambda _p, _m, identity:
                        DecisionPrompt.model_validate(next(item for item in assets['decisions/extraction_engine.json'] if item['id'] == identity)))
    if mutation == 'missing_case':
        del package.manifest.artifacts['repair-cases/extraction_engine.json']
        assert load_repair_case(package, 'extraction_engine') is None
    elif mutation is None:
        assert load_repair_case(package, 'extraction_engine').digest == ExtractionRepairCase.model_validate(design).digest
    else:
        if mutation == 'old_source':
            package.manifest.artifacts['documents/nih-r01-neuroscience.pdf'] = 'f' * 64
        elif mutation == 'wrong_assignment':
            assets['exercises.json']['extraction_engine']['documents'] = ['nsf-proposal-alpine-ecology.pdf']
        elif mutation == 'wrong_module':
            design['module_id'] = 'foundations'
        elif mutation == 'legacy_counts':
            assets['exercises.json']['extraction_engine']['star_criteria'] = {'3': 'Create 25 fields'}
        elif mutation == 'exposed_answers':
            assets['exercises.json']['extraction_engine']['expected_values'] = {'Total Budget': '1250000'}
        elif mutation == 'case_reference':
            assets['exercises.json']['extraction_engine']['repair_case_sha256'] = 'f' * 64
        else:
            assets['decisions/extraction_engine.json'][0]['outcome_id'] = 'extraction_engine.quality_repair'
        with pytest.raises(CourseCatalogError, match='repair case is invalid'):
            load_repair_case(package, 'extraction_engine')
