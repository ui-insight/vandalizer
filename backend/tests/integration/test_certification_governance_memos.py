"""Accountable memo bytes derive from an actual source-checked repair, not authored expectations."""
import base64
from copy import deepcopy
import hashlib
import json
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_governance_repair as repair
from tests.integration import test_certification_governance_execution as execution
from app.models.certification import CertificationLabExecution, CertificationLabInput, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.governance_memos import GovernanceMemoRepository
from app.services.certification_versions.runtime import CourseOperation

repo = repair.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo, *, wrong=False):
    f = await repair.fixture(repo)
    await repair.approved_repair(repo, f)
    with patch('app.services.extraction_engine.ExtractionEngine.extract', side_effect=execution.provider(f, wrong=wrong)):
        f.final = await execution.execute(repo, f)
    f.memo_body = {'request_id': uuid4().hex, 'run_id': f.final['run_id'], 'result_sha256': encode(f.final['result'])[1],
        'case_sha256': f.case.digest, 'owner_user_id': f.learner.user_id,
        'intended_use': 'Private rehearsal of an internal award amendment routing memo; no sponsor submission.',
        'supported_inputs': 'Only the complete assigned fictional award notice and issued amendment, jointly interpreted as of January 5, 2027.',
        'limitations': 'This is one fictional award pair and an instruction-repair rehearsal. It does not establish reliability on real awards, later amendments or other layouts.',
        'review_route': 'I own this training memo. A changed real artifact would require new source checks and the appropriate research-office review under local policy; that role is not a certification staff grading queue.',
        'consent': 'save_checked_capstone_memo_without_release'}
    return f


async def submit(repo, f, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='save_capstone_memo') as progress:
        return await GovernanceMemoRepository().submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.memo_body, actor_user_id=actor or f.learner.user_id)


async def test_exact_json_preserves_actual_values_accountability_and_full_history(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        memo = await submit(repo, f)
        content = base64.b64decode(memo['file']['content_base64'])
        assert hashlib.sha256(content).hexdigest() == memo['file']['sha256']
        assert len(content) == memo['file']['byte_length'] and json.loads(content) == memo['file']['memo']
        assert memo['file']['memo']['results']['Funds Obligated to Date'] == '250000'
        assert memo['file']['memo']['owner_user_id'] == f.learner.user_id
        assert memo['file']['memo']['accountability']['review_route'] == f.memo_body['review_route']
        assert memo['release_authorized'] is memo['delivery_confirmed'] is memo['credit_awarded'] is False
        await CertificationLabExecution.get_motor_collection().delete_many({})
        await CertificationLabInput.get_motor_collection().delete_many({})
        assert await submit(repo, f) == memo
        assert await GovernanceMemoRepository().get('foreign', memo['uuid']) is None
        engine.assert_not_called()


@pytest.mark.parametrize('change', ['actor', 'owner', 'run', 'result', 'case', 'blank', 'unsupported', 'reuse'])
async def test_memo_cannot_claim_other_ownership_or_unchecked_result(repo, change):
    f = await fixture(repo, wrong=change == 'unsupported')
    if change == 'owner':
        f.memo_body['owner_user_id'] = 'fictional-pi-is-not-this-learner'
    elif change == 'run':
        f.memo_body['run_id'] = f.original['run_id']
        f.memo_body['result_sha256'] = encode(f.original['result'])[1]
    elif change in ('result', 'case'):
        f.memo_body[change + '_sha256'] = '0' * 64
    elif change == 'blank':
        f.memo_body['limitations'] = ' ' * 40
    elif change == 'reuse':
        await submit(repo, f)
        f.memo_body['review_route'] += ' Changed route requires a new memo identity.'
    with pytest.raises(ValueError):
        await submit(repo, f, actor='foreign' if change == 'actor' else None)


@pytest.mark.parametrize('change', ['bytes', 'values', 'owner', 'authority'])
async def test_rehashed_memo_cannot_change_exact_generated_content(repo, change):
    f = await fixture(repo)
    memo = await submit(repo, f)
    altered = deepcopy(memo)
    if change == 'bytes':
        altered['file']['content_base64'] = base64.b64encode(b'{}').decode()
    elif change == 'values':
        altered['file']['memo']['results']['Funds Obligated to Date'] = '600000'
    elif change == 'owner':
        altered['file']['memo']['owner_user_id'] = 'foreign'
    else:
        altered['release_authorized'] = True
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': memo['uuid']})
    raw['record_json'], raw['record_sha256'] = encode(altered)
    with pytest.raises(CourseCatalogError):
        GovernanceMemoRepository.decode(raw)
