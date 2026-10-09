"""Support distinguishes execution from private handoff without copying files out."""
import json

import pytest

from app.models.certification import CertificationLearnerDecision
from app.services.certification_versions.attempts import encode
from app.services.certification_versions.support_operations import support_operations
from tests.integration import test_certification_enrollments as base
from tests.integration import test_certification_output_private_handoff as output
from tests.integration import test_certification_governance_handoff as governance
from tests.integration.test_certification_support_snapshot import snapshot

repo = base.repo
pytestmark = base.pytestmark


async def fixture(repo, monkeypatch, family):
    if family == 'output':
        f = await output.fixture(repo, monkeypatch)
        failed = await output.handoff(repo, f)
        f.handoff_body = output.retry_body(f, failed)
        delivered = await output.handoff(repo, f)
    else:
        f = await governance.fixture(repo)
        approved = await governance.release(repo, f)
        failed = await governance.send(repo, f, governance.handoff_body(f, approved))
        delivered = await governance.send(repo, f, governance.retry_body(failed))
    return f, failed, delivered


@pytest.mark.parametrize('family', ['output', 'governance'])
async def test_original_failed_and_successful_handoffs_are_read_only_private_metadata(repo, monkeypatch, family):
    f, failed, delivered = await fixture(repo, monkeypatch, family)
    before = await snapshot(repo)
    result = await support_operations(f.learner, f.package)
    group = result['groups'][2]
    assert group['kind'] == 'private_handoff' and group['more_pending'] is False
    assert [row['request_id'] for row in group['records']] == [delivered['uuid'], failed['uuid']]
    assert [row['state'] for row in group['records']] == ['delivered', 'failed']
    assert 'not sponsor delivery' in group['records'][0]['next_step']
    assert 'stopped before writing' in group['records'][1]['next_step']
    assert group['records'][0]['references']['previous_failed_id'] == failed['uuid']
    assert group['records'][0]['references']['run_id'] == delivered['run_id']
    text = json.dumps(group)
    assert all(key not in text for key in ('destination_copy', 'file_sha256', 'record_json', 'submission_channel', 'submitted_at'))
    assert await support_operations(f.learner, f.package) == result
    assert await snapshot(repo) == before


@pytest.mark.parametrize('family', ['output', 'governance'])
async def test_rehashed_changed_destination_cannot_claim_private_delivery(repo, monkeypatch, family):
    f, _, delivered = await fixture(repo, monkeypatch, family)
    records = CertificationLearnerDecision.get_motor_collection()
    raw = await records.find_one({'uuid': delivered['uuid']})
    record = json.loads(raw['record_json'])
    record['destination']['audience'] = 'PRIVATE WRONG AUDIENCE'
    serialized, digest = encode(record)
    await records.update_one({'uuid': delivered['uuid']}, {'$set': {'record_json': serialized, 'record_sha256': digest}})
    before = await snapshot(repo)
    result = await support_operations(f.learner, f.package)
    row = result['groups'][2]['records'][0]
    assert set(row) == {'state', 'next_step'} and row['state'] == 'unavailable'
    assert 'PRIVATE WRONG AUDIENCE' not in json.dumps(result)
    assert await snapshot(repo) == before
