"""Real editor PATCH preserves certification field identity and captured evidence."""
import os
from uuid import uuid4

import pytest

from app.routers.extractions import router as extraction_router
from app.dependencies import get_current_user
from app.models.user import User
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.validation_inputs import ValidationInputRepository
from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_validation_http as http

repo = base.repo
versioned_runtime = base.versioned_runtime
pytestmark = pytest.mark.skipif(not os.environ.get('CERTIFICATION_TEST_MONGO_URL'), reason='Requires disposable MongoDB')


async def test_instruction_only_editor_patch_preserves_name_identity_and_original_capture(versioned_runtime, monkeypatch):
    f = await http.fixture(versioned_runtime, monkeypatch)
    user = User(user_id=f.learner.user_id)
    f.app.dependency_overrides[get_current_user] = lambda: user
    f.app.include_router(extraction_router, prefix='/api/extractions')
    field = f.fields[1]
    field.searchphrase = 'Extract the Year 1 total instead of the complete project budget.'
    await field.save()
    params = {'enrollment_id': f.learner.uuid}
    async with f.client as client:
        before = await http.post(client, 'modules/validation_qa/validation-captures', params, f.body)
        repository = ValidationInputRepository()
        original = await repository.get(f.learner.user_id, before['uuid'])
        original_hash = encode(original)[1]
        instruction = 'Extract the full multi-year project budget as a plain USD number; never an annual subtotal.'
        response = await client.patch(f'/api/extractions/items/{field.id}', json={'searchphrase': instruction})
        assert response.status_code == 200, response.text
        changed = response.json()
        assert changed['id'] == str(field.id)
        assert changed['title'] == field.title == 'Total Project Budget'
        assert changed['searchphrase'] == instruction
        assert changed['is_optional'] == field.is_optional
        assert changed['enum_values'] == field.enum_values
        current = await client.get(f'/api/extractions/search-sets/{f.artifact.uuid}/items')
        assert current.status_code == 200, current.text
        assert next(item for item in current.json() if item['id'] == str(field.id)) == changed
        after = await http.post(client, 'modules/validation_qa/validation-captures', params, {**f.body, 'request_id': uuid4().hex})
        assert after['artifact_id'] == before['artifact_id'] == f.artifact.uuid
        assert after['input_snapshot_sha256'] != before['input_snapshot_sha256']
        assert after['artifact_sha256'] != before['artifact_sha256']
        assert [item['id'] for item in after['artifact']['fields']] == [item['id'] for item in before['artifact']['fields']]
        assert [item['title'] for item in after['artifact']['fields']] == [item['title'] for item in before['artifact']['fields']]
        assert next(item for item in after['artifact']['fields'] if item['id'] == str(field.id))['searchphrase'] == instruction
        assert encode(await repository.get(f.learner.user_id, before['uuid']))[1] == original_hash
        progress = await versioned_runtime.read_progress(f.learner.user_id, f.learner.uuid)
        assert progress.total_xp == 0 and not progress.certified
        assert f.provider.call_count == 0 and f.judge.await_count == 0
