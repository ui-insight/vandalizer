"""Source findings bind actual funding mistakes and original page evidence."""
from copy import deepcopy
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_governance_execution as execution
from app.models.certification import CertificationLabExecution, CertificationLabInput, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.governance_findings import GovernanceFindingRepository
from app.services.certification_versions.runtime import CourseOperation

repo = execution.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo, *, wrong=True):
    f = await execution.fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=execution.provider(f, wrong=wrong)):
        f.original = await execution.execute(repo, f)
    f.finding_body = {'request_id': uuid4().hex, 'run_id': f.original['run_id'], 'result_sha256': encode(f.original['result'])[1],
        'case_sha256': f.case.digest, 'field': 'Funds Obligated to Date', 'observed_value': '600000',
        'source_references': [f.case.expectations[0].anchors[0].model_dump(mode='json'), f.case.expectations[3].anchors[0].model_dump(mode='json')],
        'explanation': 'The original output returns $600,000, a planned ceiling. The issued amendment adds $70,000 to the original $180,000, making $250,000 actually obligated. I will revise the same funding field to use cumulative obligations from the latest issued amendment and retest both complete records.',
        'consent': 'save_my_original_source_finding_before_repair'}
    return f


async def submit(repo, f, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='save_source_finding') as progress:
        return await GovernanceFindingRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.finding_body, actor_user_id=actor or f.learner.user_id)


async def test_finding_preserves_original_result_and_sources_after_workspace_deletion(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        saved = await submit(repo, f)
        await CertificationLabExecution.get_motor_collection().delete_many({})
        await CertificationLabInput.get_motor_collection().delete_many({})
        assert await submit(repo, f) == saved
        assert await GovernanceFindingRepository().get(f.learner.user_id, saved['uuid']) == saved
        assert await GovernanceFindingRepository().get('foreign', saved['uuid']) is None
        engine.assert_not_called()
    assert saved['checks']['observed_semantic_failure'] is True and saved['credit_awarded'] is False
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['actor', 'run', 'result', 'case', 'value', 'field', 'quote', 'page', 'source', 'blank', 'reuse', 'already_correct'])
async def test_finding_cannot_invent_failure_or_source_support(repo, change):
    f = await fixture(repo, wrong=change != 'already_correct')
    if change == 'run':
        f.finding_body['run_id'] = uuid4().hex
    elif change in ('result', 'case'):
        f.finding_body[change + '_sha256'] = '0' * 64
    elif change == 'value':
        f.finding_body['observed_value'] = '180000'
    elif change == 'field':
        f.finding_body['field'] = 'Project Title'
    elif change in ('quote', 'page', 'source'):
        key, val = {'quote': ('quote', 'This invented sentence does not appear on the page.'), 'page': ('page', 2), 'source': ('source_id', 'award')}[change]
        f.finding_body['source_references'][1][key] = val
    elif change == 'blank':
        f.finding_body['explanation'] = ' ' * 40
    elif change == 'reuse':
        await submit(repo, f)
        f.finding_body['explanation'] += ' Changed explanation is a different request.'
    with pytest.raises(ValueError):
        await submit(repo, f, actor='foreign' if change == 'actor' else None)


@pytest.mark.parametrize('change', ['checks', 'result', 'channel', 'authority'])
async def test_rehashed_finding_cannot_change_its_observed_evidence(repo, change):
    f = await fixture(repo)
    saved = await submit(repo, f)
    changed = deepcopy(saved)
    if change == 'checks':
        changed['checks']['fields'][3]['actual_value'] = '180000'
    elif change == 'result':
        changed['submission']['result_sha256'] = '0' * 64
        changed['request_sha256'] = encode(changed['submission'])[1]
    elif change == 'channel':
        changed['submission_channel'] = 'agent_claim'
    else:
        changed['execution_authorized'] = True
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': saved['uuid']})
    raw['record_json'], raw['record_sha256'] = encode(changed)
    with pytest.raises(CourseCatalogError):
        GovernanceFindingRepository.decode(raw)
