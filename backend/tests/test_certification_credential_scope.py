"""New scope records never reinterpret or expand an existing issuance schema."""
import hashlib
import json

import pytest

from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog
from app.services.certification_versions.credential_scope import public_credential_scope
from app.services.certification_versions.credentials import CredentialRepository, CredentialSnapshot, parse_credential_snapshot
from tests import test_certification_outcome_rubric as rubric_fixtures

candidate = rubric_fixtures.candidate


def record():
    return CredentialSnapshot(credential_id='credential', user_id='learner', enrollment_id='original',
        learner_name='Synthetic learner', course_title='Original course', course_version='original-course',
        manifest_sha256='a' * 64, rubric_id='original-rubric', provenance='versioned_course_completion',
        certified_at='2026-10-01T12:00:00+00:00', recorded_at='2026-10-01T12:00:00+00:00',
        level='validated', module_ids=('original-module',), evidence=())


def test_schema_one_keeps_its_exact_shape_without_inventing_scope():
    original = record()
    # Also covers a competency credential issued before scope was recorded.
    original = original.model_copy(update={'outcomes': ('original-module.outcome',)})
    serialized = json.dumps(original.model_dump(mode='json'), sort_keys=True, separators=(',', ':'))
    raw = {'uuid': original.credential_id, 'user_id': original.user_id, 'enrollment_id': original.enrollment_id,
           'record_json': serialized, 'record_sha256': hashlib.sha256(serialized.encode()).hexdigest()}
    restored = CredentialRepository.decode(raw)
    assert not hasattr(restored, 'credential_scope')
    assert restored.schema_version == 1
    assert json.dumps(restored.model_dump(mode='json'), sort_keys=True, separators=(',', ':')) == serialized
    assert parse_credential_snapshot(original.model_dump()).model_dump_json() == original.model_dump_json()


def test_public_scope_uses_exact_pinned_contract_and_does_not_relabel_legacy(candidate):
    scope = public_credential_scope(candidate.package)
    contract = candidate.package.json('outcomes.json')
    assert scope['promise'] == contract['credential_promise']
    assert scope['agent_assistance'] == contract['agent_assistance']
    assert scope['exclusions'] == contract['exclusions']
    assert scope['contract_sha256'] == candidate.package.manifest.artifacts['outcomes.json']
    assert public_credential_scope(CourseCatalog(CATALOG_ROOT).load('legacy-2026-10-02.1', preview=True)) is None


@pytest.mark.parametrize('change', ['missing_scope', 'unknown_schema', 'boolean_schema', 'no_outcomes', 'legacy_provenance'])
def test_incomplete_or_mislabeled_scope_records_are_rejected(candidate, change):
    scope = public_credential_scope(candidate.package)
    scope.pop('state')
    value = {**record().model_dump(mode='json'), 'schema_version': 2, 'credential_scope': scope,
             'outcomes': ['original-module.outcome']}
    if change == 'missing_scope':
        del value['credential_scope']
    elif change == 'unknown_schema':
        value['schema_version'] = 3
    elif change == 'boolean_schema':
        value['schema_version'] = True
    elif change == 'no_outcomes':
        value['outcomes'] = []
    else:
        value['provenance'] = 'legacy_completion_unverified'
    with pytest.raises(ValueError):
        parse_credential_snapshot(value)
