"""Insert-only credential records, independent of mutable progress and catalogs.

The continuation rubric proves stored module completion only. It does not
supply evidence for the proposed new Vandalizer 5.0 supervision outcomes.
"""
import datetime
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationCredential
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .credential_scope import CredentialScope, scope_from_contract


class CredentialSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = 1
    credential_id: str
    user_id: str
    enrollment_id: str
    learner_name: str
    name_policy: str = 'Profile display name recorded when this issuance was preserved'
    credential_title: str = 'Vandal Workflow Architect'
    course_title: str
    course_version: str | None
    manifest_sha256: str | None
    rubric_id: str | None
    provenance: str
    certified_at: str | None
    recorded_at: str
    level: str
    module_ids: tuple[str, ...]
    evidence: tuple[dict, ...]
    outcomes: tuple[str, ...] = ()
    outcome_evidence_status: str = 'Stored module credit; new 5.0 supervision outcomes are not established'
    supersedes_credential_id: str | None = None


class CompetencyCredentialSnapshot(CredentialSnapshot):
    """New issuance format; schema-1 records retain their original exact shape."""
    schema_version: Literal[2] = 2
    credential_scope: CredentialScope

    @model_validator(mode='after')
    def competency_identity(self):
        if (self.provenance != 'versioned_course_completion' or not self.outcomes or not self.module_ids
                or not self.course_version or not self.manifest_sha256 or not self.rubric_id):
            raise ValueError('A recorded competency scope requires its original versioned outcome credential')
        return self


def parse_credential_snapshot(value):
    if not isinstance(value, dict) or type(value.get('schema_version', 1)) is not int:
        raise ValueError('Invalid credential schema')
    schema = value.get('schema_version', 1)
    if schema not in (1, 2):
        raise ValueError('Unsupported credential schema')
    model = CompetencyCredentialSnapshot if schema == 2 else CredentialSnapshot
    return model.model_validate(value)


class CredentialRepository:
    @property
    def records(self):
        return CertificationCredential.get_motor_collection()

    @staticmethod
    def decode(raw) -> CredentialSnapshot:
        try:
            if hashlib.sha256(raw['record_json'].encode()).hexdigest() != raw['record_sha256']:
                raise CourseCatalogError('The preserved credential failed its integrity check')
            record = parse_credential_snapshot(json.loads(raw['record_json']))
            if (record.credential_id, record.user_id, record.enrollment_id) != (raw['uuid'], raw['user_id'], raw['enrollment_id']):
                raise CourseCatalogError('The preserved credential identity is inconsistent')
            # Dates are used to render the original issuance, never repaired or
            # substituted with today's date when a stored payload is malformed.
            datetime.datetime.fromisoformat(record.recorded_at)
            if record.certified_at is not None:
                datetime.datetime.fromisoformat(record.certified_at)
        except CourseCatalogError:
            raise
        except (KeyError, AttributeError, TypeError, ValidationError, ValueError) as exc:
            raise CourseCatalogError('The preserved credential needs record reconciliation') from exc
        return record

    async def get(self, user_id: str, credential_id: str):
        raw = await self.records.find_one({'uuid': credential_id, 'user_id': user_id})
        return self.decode(raw) if raw else None

    async def for_enrollment(self, user_id: str, enrollment_id: str):
        raw = await self.records.find_one({'enrollment_id': enrollment_id, 'user_id': user_id})
        return self.decode(raw) if raw else None

    async def list(self, user_id: str):
        rows = await self.records.find({'user_id': user_id}).to_list(None)
        return [self.decode(raw) for raw in rows]

    async def _insert_snapshot(self, progress, package, learner_name: str, *, legacy=False):
        """Caller holds the enrollment write boundary; no update path exists."""
        existing = await self.for_enrollment(progress.user_id, progress.enrollment_id)
        if existing:
            return existing
        return await self.persist(self.prepare(progress, package, learner_name, legacy=legacy))

    @staticmethod
    def prepare(progress, package, learner_name: str, *, legacy=False) -> CredentialSnapshot:
        if not progress.certified:
            raise EnrollmentConflict('This enrollment has not earned certification')
        if not progress.enrollment_id or progress.course_version != package.manifest.release_id:
            raise EnrollmentConflict('The credential must match the enrolled course')
        module_ids = tuple(module.id for module in package.manifest.modules)
        if not legacy and (not progress.certified_at or not all(progress.modules.get(mid, {}).get('completed') for mid in module_ids)):
            raise EnrollmentConflict('Complete course evidence and its original date are required for new issuance')
        if legacy:
            module_ids = tuple(mid for mid, data in progress.modules.items() if isinstance(data, dict) and data.get('completed'))
        from .outcomes import package_outcomes
        from .outcome_credit import verified_credit_snapshot
        contract = None if legacy else package_outcomes(package)
        if contract:
            from .grading import load_rubric
            if package.entry.state == 'draft' or not package.entry.supported_for_existing:
                raise CourseCatalogError('Competency credentials require a supported published course')
            load_rubric(package)
        evidence = []
        for mid in module_ids:
            credit = progress.modules[mid]
            item = {'module_id': mid, 'progress_id': str(progress.id),
                    'completed_at': credit.get('completed_at'), 'stars': credit.get('stars'),
                    'attempt_id': credit.get('completion_attempt_id'), 'basis': 'stored_module_credit'}
            if contract:
                snapshot = verified_credit_snapshot(package, progress, mid, credit.get('outcome_credit'),
                    expected_attempt_id=credit.get('completion_attempt_id'))
                item.update(basis='selected_required_outcomes', assessment_snapshot=snapshot,
                            completion_validation_sha256=credit['outcome_credit']['validation_sha256'])
                if snapshot.get('assessment_kind') == 'transferred_outcomes':
                    item.update(basis='transferred_required_outcomes', xp_carried=snapshot['xp_carried'], xp_earned=0)
            evidence.append(item)
        snapshot_model = CompetencyCredentialSnapshot if contract else CredentialSnapshot
        return snapshot_model(
            credential_id=uuid5(NAMESPACE_URL, 'vandalizer:credential:' + progress.enrollment_id).hex,
            user_id=progress.user_id, enrollment_id=progress.enrollment_id,
            learner_name=learner_name or progress.user_id,
            course_title='Legacy certification - historical version unknown' if legacy else package.manifest.title,
            course_version=None if legacy else package.manifest.release_id,
            manifest_sha256=None if legacy else package.manifest_sha256,
            rubric_id=None if legacy else package.manifest.rubric_id,
            provenance='legacy_completion_unverified' if legacy else 'versioned_course_completion',
            certified_at=progress.certified_at.isoformat() if progress.certified_at else None,
            recorded_at=datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            level=progress.level, module_ids=module_ids,
            evidence=tuple(evidence),
            outcomes=contract.required_outcomes() if contract else (),
            outcome_evidence_status=('All required competency outcomes supported by original selected assessment receipts'
                                     if contract else 'Stored module credit; new 5.0 supervision outcomes are not established'),
            **({'credential_scope': scope_from_contract(package, contract)} if contract else {}),
        )

    async def persist(self, record: CredentialSnapshot) -> CredentialSnapshot:
        """Insert the already frozen payload, including on an interrupted retry."""
        serialized = json.dumps(record.model_dump(mode='json'), sort_keys=True, separators=(',', ':'))
        try:
            await self.records.insert_one({
                'uuid': record.credential_id, 'user_id': record.user_id,
                'enrollment_id': record.enrollment_id, 'record_json': serialized,
                'record_sha256': hashlib.sha256(serialized.encode()).hexdigest(),
            })
        except DuplicateKeyError:
            pass  # Restart/concurrent replay returns the original issuance.
        preserved = await self.for_enrollment(record.user_id, record.enrollment_id)
        if preserved is None:
            raise EnrollmentConflict('Credential identity conflicts with another record')
        return preserved

    async def preserve_legacy(self, repository: EnrollmentRepository, user_id: str, enrollment_id: str, learner_name: str):
        """Explicit migration primitive; never invoked by a read or publication."""
        enrollment = await repository._enrollment(user_id, enrollment_id)
        if enrollment.provenance != 'legacy_version_unknown':
            raise EnrollmentConflict('Legacy preservation requires unknown historical provenance')
        async with repository.write_boundary(user_id, enrollment_id, operation='preserve_legacy_credential') as progress:
            return await self._insert_snapshot(progress, repository.catalog.load(enrollment.course_version), learner_name, legacy=True)
