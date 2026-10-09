"""Check actual result coverage separately from semantic repair assessment."""
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.extraction_checks import check_extraction_execution
from app.services.certification_versions.outcomes import OutcomeContract

CONTRACT = OutcomeContract.model_validate_json((Path(__file__).resolve().parents[1]
    / 'certification-data/drafts/v5.0/outcomes.json').read_bytes())


def records(entities):
    artifact = {'fields': [{'searchphrase': 'Budget'}, {'searchphrase': 'Postdoc'}]}
    snapshot = {'uuid': 'snapshot', 'module_id': 'extraction_engine', 'artifact': artifact,
                'artifact_sha256': encode(artifact)[1], 'documents': [{'document_id': 'source'}]}
    repair = {'input_snapshot_sha256': encode(snapshot)[1], 'artifact_sha256': snapshot['artifact_sha256']}
    plan = {'module_id': 'extraction_engine', 'input_snapshot_id': snapshot['uuid'],
            'input_snapshot_sha256': encode(snapshot)[1], 'repair_case': repair,
            'approval_requirement': {'choice': 'approve'}}
    digest = encode(plan)[1]
    scope = {'run_id': 'run', 'plan_sha256': digest, 'input_snapshot_sha256': encode(snapshot)[1],
             'run_state_at_submission': 'prepared', 'submission': {'choice': 'approve', 'repair_case_sha256': encode(repair)[1]}}
    authorization = {'decision': scope}
    run = {'run_id': 'run', 'state': 'completed', 'plan': plan, 'plan_sha256': digest, 'authorization': authorization,
           'result': {'run_id': 'run', 'status': 'completed', 'plan_sha256': digest,
                      'authorization_sha256': encode(authorization)[1], 'documents_executed': ['source'], 'entities': entities}}
    return run, snapshot


@pytest.mark.parametrize('entities,passed', [([{'Budget': '1250000', 'Postdoc': None}], True),
                                           ([{'Budget': '304000', 'Postdoc': 'An invented name'}], True),
                                           ([], False), ([{'Budget': '1250000'}], False),
                                           ([{'Budget': '1250000'}, {'Postdoc': None}], False),
                                           ([{'Budget': '1250000', 'Postdoc': None}] * 2, False)])
def test_execution_completeness_is_not_a_claim_of_correct_values(entities, passed):
    run, snapshot = records(entities)
    original = deepcopy((run, snapshot))
    result = check_extraction_execution(CONTRACT, run, snapshot)
    assert result['passed'] is passed
    assert result['status'] == ('requirements_supported' if passed else 'revision_required')
    assert bool(result['revision_instruction']) is not passed
    assert result['credit_awarded'] is result['module_completion_eligible'] is False
    assert (run, snapshot) == original


@pytest.mark.parametrize('change', ['source', 'artifact', 'approval', 'late_approval', 'result', 'unfinished', 'case', 'case_reference', 'requirement'])
def test_rejects_unbound_or_reinterpreted_execution_evidence(change):
    run, snapshot = records([{'Budget': '1250000', 'Postdoc': None}])
    contract = CONTRACT
    if change == 'source':
        run['result']['documents_executed'] = ['other-source']
    elif change == 'artifact':
        snapshot['artifact']['fields'][0]['searchphrase'] = 'Unrelated budget'
    elif change == 'approval':
        run['authorization']['decision']['submission']['choice'] = 'decline'
    elif change == 'late_approval':
        run['authorization']['decision']['run_state_at_submission'] = 'completed'
    elif change == 'result':
        run['result']['run_id'] = 'other-run'
    elif change == 'unfinished':
        run['state'], run['result'] = 'prepared', None
    elif change == 'case':
        run['plan']['repair_case']['artifact_sha256'] = 'f' * 64
    elif change == 'case_reference':
        run['authorization']['decision']['submission']['repair_case_sha256'] = 'f' * 64
    else:
        value = CONTRACT.model_dump(mode='json')
        module = next(item for item in value['modules'] if item['module_id'] == 'extraction_engine')
        next(item for item in module['outcomes'] if item['method'] == 'deterministic')['passing_conditions'] = ['A changed requirement not implemented by this checker.']
        contract = OutcomeContract.model_validate(value)
    with pytest.raises(CourseCatalogError):
        check_extraction_execution(contract, run, snapshot)
