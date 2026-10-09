"""An authenticated scope correction neither dispatches work nor broadens authority."""
from copy import deepcopy
import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from tests.integration import test_certification_governance_inputs as inputs
from app.models.certification import CertificationLabInput, CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.governance_scope import GovernanceScopeCorrection
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.runtime import CourseOperation

repo = inputs.repo
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def fixture(repo):
    f = await inputs.fixture(repo)
    f.snapshot = await inputs.capture(repo, f)
    f.scope_body = {'request_id': uuid4().hex, 'input_snapshot_id': f.snapshot['uuid'], 'input_snapshot_sha256': encode(f.snapshot)[1],
        'case_sha256': f.case.digest, 'choice': 'reject_broad_proposal', 'source_document_ids': [d.uuid for d in f.documents],
        'destination_id': 'private_training_inbox', 'audience': 'enrolled_learner_only', 'ongoing_automation': 'keep_disabled',
        'reason': 'The agent cannot approve on my behalf. Only these two assigned records are in scope; broad sharing, sponsor email and the recurring send remain disabled. I would stop an unintended trigger before inspecting its original receipts.',
        'consent': 'save_my_corrected_capstone_scope_without_execution'}
    return f


async def submit(repo, f, actor=None):
    async with repo.write_boundary(f.learner.user_id, f.learner.uuid, operation='correct_capstone_scope') as progress:
        return await GovernanceScopeCorrection().submit(CourseOperation(f.learner.user_id, f.package, progress, True),
            f.scope_body, actor_user_id=actor or f.learner.user_id)


async def test_saved_correction_survives_workspace_deletion_without_dispatch_or_credit(repo):
    f = await fixture(repo)
    with patch('app.services.extraction_engine.ExtractionEngine.extract') as engine:
        saved = await submit(repo, f)
        await CertificationLabInput.get_motor_collection().delete_many({})
        for doc in f.documents:
            await doc.delete()
        await f.artifact.delete()
        assert await submit(repo, f) == saved
        assert await GovernanceScopeCorrection().get(f.learner.user_id, saved['uuid']) == saved
        assert await GovernanceScopeCorrection().get('foreign', saved['uuid']) is None
        engine.assert_not_called()
    assert saved['execution_authorized'] is saved['external_effects_authorized'] is saved['credit_awarded'] is False
    assert (await repo.read_progress(f.learner.user_id, f.learner.uuid)).total_xp == 0


@pytest.mark.parametrize('change', ['actor', 'source', 'duplicate_source', 'capture', 'hash', 'case', 'broad_audience', 'sponsor', 'automation', 'agent_approval', 'blank', 'extra_credit', 'reuse'])
async def test_correction_cannot_claim_other_sources_or_external_authority(repo, change):
    f = await fixture(repo)
    if change == 'source':
        f.scope_body['source_document_ids'][0] = uuid4().hex
    elif change == 'duplicate_source':
        f.scope_body['source_document_ids'][1] = f.scope_body['source_document_ids'][0]
    elif change == 'capture':
        f.scope_body['input_snapshot_id'] = uuid4().hex
    elif change in ('hash', 'case'):
        f.scope_body['input_snapshot_sha256' if change == 'hash' else 'case_sha256'] = '0' * 64
    elif change == 'broad_audience':
        f.scope_body['audience'] = 'workspace_everyone'
    elif change == 'sponsor':
        f.scope_body['destination_id'] = 'sponsor_email'
    elif change == 'automation':
        f.scope_body['ongoing_automation'] = 'enable'
    elif change == 'agent_approval':
        f.scope_body['choice'] = 'agent_says_approved'
    elif change == 'blank':
        f.scope_body['reason'] = ' ' * 45
    elif change == 'extra_credit':
        f.scope_body['passed'] = True
    elif change == 'reuse':
        await submit(repo, f)
        f.scope_body['reason'] += ' Changed decision cannot overwrite the earlier record.'
    with pytest.raises(ValueError):
        await submit(repo, f, actor='foreign' if change == 'actor' else None)


@pytest.mark.parametrize('change', ['sources', 'authority', 'prompt', 'channel'])
async def test_rehashed_correction_cannot_replace_original_source_or_actor_context(repo, change):
    f = await fixture(repo)
    saved = await submit(repo, f)
    modified = deepcopy(saved)
    if change == 'sources':
        modified['submission']['source_document_ids'].reverse()
        modified['request_sha256'] = encode(modified['submission'])[1]
    elif change == 'authority':
        modified['execution_authorized'] = True
    elif change == 'prompt':
        modified['prompt']['phase'] = 'after_original_before_repair'
    else:
        modified['submission_channel'] = 'agent_claim'
    raw = await CertificationLearnerDecision.get_motor_collection().find_one({'uuid': saved['uuid']})
    raw['record_json'], raw['record_sha256'] = encode(modified)
    with pytest.raises(CourseCatalogError):
        GovernanceScopeCorrection.decode(raw)
