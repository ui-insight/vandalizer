"""Persist the learner's exact optional-upgrade preservation choice.

Internal only. Recording consent neither locks future work nor activates an
upgrade. A future activation must revalidate the frozen snapshot under its own
write boundary. A replay returns the original choice, never renewed consent.
"""
from contextlib import asynccontextmanager
import datetime
import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationUpgradeDecision
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .grading import selected_outcome_completion_available
from .transition_preview import TransitionPreview
from .upgrade_comparison import UpgradeComparison, UpgradeUnavailable


class UpgradeDecisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    source_enrollment_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    target_version: str = Field(pattern=r'^[a-z0-9][a-z0-9.-]{0,95}$')
    preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['preserve_original_work_and_require_all_new_outcomes']


class UpgradeDecisionRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = 1
    kind: Literal['optional_upgrade_preservation_decision'] = 'optional_upgrade_preservation_decision'
    user_id: str
    request: UpgradeDecisionRequest
    accepted_at: str
    preview: dict
    activated: Literal[False] = False
    credit_transferred: Literal[False] = False
    requires_fresh_activation_check: Literal[True] = True


class UpgradeDecisionRepository:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()

    @property
    def records(self):
        return CertificationUpgradeDecision.get_motor_collection()

    @staticmethod
    def decode(raw):
        try:
            if hashlib.sha256(raw['record_json'].encode()).hexdigest() != raw['record_sha256']:
                raise ValueError('Record digest mismatch')
            record = UpgradeDecisionRecord.model_validate_json(raw['record_json'])
            request, preview = record.request, record.preview
            if (request.request_id != raw['uuid'] or record.user_id != raw['user_id']
                    or request.source_enrollment_id != raw['source_enrollment_id']
                    or raw.get('target_version') not in (None, request.target_version)
                    or raw.get('decision_basis_sha256') not in (None, preview.get('decision_basis_sha256'))
                    or preview['source']['enrollment_id'] != request.source_enrollment_id
                    or preview['target']['course_version'] != request.target_version
                    or preview['preview_sha256'] != request.preview_sha256
                    or encode({key: value for key, value in preview.items() if key != 'preview_sha256'})[1] != request.preview_sha256
                    or preview['policy'] != 'optional' or preview['can_activate'] is not False
                    or preview['target']['transferred_outcome_count'] != 0):
                raise ValueError('Original decision identity differs')
            datetime.datetime.fromisoformat(record.accepted_at)
            return record
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise CourseCatalogError('The saved upgrade decision failed integrity verification') from exc

    async def get(self, user_id, request_id):
        raw = await self.records.find_one({'uuid': request_id, 'user_id': user_id})
        return self.decode(raw) if raw else None

    async def accept(self, user_id, body):
        request = UpgradeDecisionRequest.model_validate(body)
        existing = await self.records.find_one({'uuid': request.request_id})
        if existing is not None:
            return self._replay(existing, user_id, request)
        comparison = UpgradeComparison(self.repository)
        source = await comparison.source(user_id, request.source_enrollment_id)
        package, _ = comparison.target(source.course_version, request.target_version)
        if not selected_outcome_completion_available(package):
            raise UpgradeUnavailable('The offered course cannot yet award its required outcome credit')
        preview = await TransitionPreview(self.repository).inspect(user_id, source.uuid, request.target_version)
        if preview['preview_sha256'] != request.preview_sha256:
            raise EnrollmentConflict('Course work changed; review the preservation plan again before accepting it')
        if (preview['preservation_plan']['reconciliation_required_count']
                or any(item['code'] in ('write_in_flight', 'pending_assessment', 'credential_preservation') for item in preview['blockers'])):
            raise EnrollmentConflict('Resolve unfinished operations and preserve the original credential before accepting a switch plan')
        await comparison.source(user_id, source.uuid)
        current_package, _ = comparison.target(source.course_version, request.target_version)
        if package.manifest_sha256 != current_package.manifest_sha256:
            raise EnrollmentConflict('The offered course changed; review its requirements again')
        record = UpgradeDecisionRecord(user_id=user_id, request=request, preview=preview,
            accepted_at=datetime.datetime.now(tz=datetime.timezone.utc).isoformat())
        payload, digest = encode(record.model_dump(mode='json'))
        try:
            await self.records.insert_one({'uuid': request.request_id, 'user_id': user_id,
                'source_enrollment_id': source.uuid, 'target_version': request.target_version,
                'decision_basis_sha256': preview['decision_basis_sha256'], 'record_json': payload, 'record_sha256': digest})
        except DuplicateKeyError:
            pass
        saved = await self.records.find_one({'uuid': request.request_id})
        if saved is None:
            raise EnrollmentConflict('The preservation choice could not be confirmed; retry its original request')
        return self._replay(saved, user_id, request)

    @asynccontextmanager
    async def hold_reviewed_choice(self, user_id, request_id, *, activation_request=None):
        """Revalidate under the source write lock; this does not switch courses.

        External-job reconciliation and a recoverable selection commit remain
        the caller's obligations. Exiting rotates only the ownership guard.
        """
        original = await self.get(user_id, request_id)
        if original is None:
            raise EnrollmentConflict('The original preservation choice is unavailable')
        request = original.request
        comparison = UpgradeComparison(self.repository)
        async with self.repository.write_boundary(user_id, request.source_enrollment_id,
                operation='activate_optional_upgrade' if activation_request else 'revalidate_upgrade_choice',
                selection_request=activation_request) as progress:
            source = await comparison.source(user_id, request.source_enrollment_id)
            package, _ = comparison.target(source.course_version, request.target_version)
            if not selected_outcome_completion_available(package):
                raise UpgradeUnavailable('The offered course cannot yet award its required outcome credit')
            current = await TransitionPreview(self.repository).inspect(user_id, source.uuid, request.target_version, _held_write=True)
            if (not original.preview.get('decision_basis_sha256')
                    or current['decision_basis_sha256'] != original.preview['decision_basis_sha256']
                    or current['preservation_plan'] != original.preview['preservation_plan']):
                raise EnrollmentConflict('Course work changed after the choice; review and accept a new preservation plan')
            # This comparison also detects target/credential changes and keeps
            # every unresolved-operation blocker from the accepted snapshot.
            if (current['preservation_plan']['reconciliation_required_count']
                    or any(item['code'] in ('write_in_flight', 'pending_assessment', 'credential_preservation') for item in current['blockers'])):
                raise EnrollmentConflict('Resolve unfinished work before using this preservation choice')
            offered, _ = comparison.target(source.course_version, request.target_version)
            if offered.manifest_sha256 != package.manifest_sha256:
                raise EnrollmentConflict('The offered course changed during review')
            yield original, progress, package

    def _replay(self, raw, user_id, request):
        if raw['user_id'] != user_id:
            raise EnrollmentConflict('The request reference is unavailable')
        original = self.decode(raw)
        if original.request != request:
            raise EnrollmentConflict('This request already records a different preservation choice')
        return original
