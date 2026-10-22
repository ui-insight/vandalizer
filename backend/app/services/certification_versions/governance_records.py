"""Common authenticated, immutable journal protocol for capstone learner records."""
import datetime

from pymongo.errors import DuplicateKeyError

from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .governance_case import load_governance_case
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import LearnerDecisionRepository

MAX_RECORD_BYTES = 14 * 1024 * 1024
IDENTITY_KEYS = ('user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'run_id')


def embedded_record(saved):
    serialized, digest = encode(saved)
    return {**saved, 'record_json': serialized, 'record_sha256': digest}


class GovernanceJournal(LearnerDecisionRepository):
    request_model = None
    prompt_id = None
    channel = None

    @classmethod
    def decode(cls, raw):
        saved = LearnerDecisionRepository.decode(raw)
        try:
            body = cls.request_model.model_validate(saved['submission'])
            if (saved['module_id'] != 'governance' or saved['record_kind'] != cls.prompt_id or saved['prompt_id'] != cls.prompt_id
                    or saved['uuid'] != body.request_id or saved['run_id'] != body.run_id
                    or saved['request_sha256'] != encode(body.model_dump(mode='json'))[1]
                    or saved['case']['case_sha256'] != body.case_sha256 or saved['submission_channel'] != cls.channel
                    or datetime.datetime.fromisoformat(saved['submitted_at']).tzinfo is None
                    or any(saved[k] is not False for k in ('external_effects_authorized', 'credit_awarded', 'module_completion_eligible'))):
                raise ValueError('The original authenticated identity, authority or submission changed')
            cls.validate(saved, body)
            return saved
        except (KeyError, TypeError, ValueError, StopIteration, AttributeError) as exc:
            raise CourseCatalogError('The saved Governance learner record failed integrity verification') from exc

    @classmethod
    def validate(cls, saved, body):
        raise NotImplementedError

    async def get(self, user_id, reference):
        raw = await self.records.find_one({'uuid': reference, 'user_id': user_id, 'module_id': 'governance', 'prompt_id': self.prompt_id})
        return self.decode(raw) if raw else None

    async def after_save(self, operation, saved, *, replay):
        return None

    async def build(self, operation, body):
        raise NotImplementedError

    async def submit(self, operation, body, *, actor_user_id):
        body = self.request_model.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('This capstone decision requires the authenticated learner')
        identity = {'uuid': body.request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
            'module_id': 'governance', 'course_version': operation.package.manifest.release_id,
            'manifest_sha256': operation.package.manifest_sha256, 'run_id': body.run_id, 'prompt_id': self.prompt_id}
        lease = LabExecutionRepository.check_operation(operation, identity)
        request = body.model_dump(mode='json')
        request_hash = encode(request)[1]

        async def replay(raw):
            if any(raw.get(k) != v for k, v in identity.items()) or raw.get('request_sha256') != request_hash:
                raise EnrollmentConflict('This capstone request identity belongs to different evidence, answers or another learner')
            saved = self.decode(raw)
            await self.after_save(operation, saved, replay=True)
            return saved

        await LabInputRepository._check_lease(lease)
        existing = await self.records.find_one({'uuid': body.request_id})
        if existing is not None:
            return await replay(existing)
        case = load_governance_case(operation.package)
        if body.case_sha256 != case.digest:
            raise EnrollmentConflict('Use the exact assigned capstone case')
        evidence = await self.build(operation, body)
        saved = {**evidence, **identity, 'record_kind': self.prompt_id, 'request_sha256': request_hash,
            'submission': request, 'case': case.public_definition(),
            'submitted_at': evidence.get('submitted_at', datetime.datetime.now(datetime.timezone.utc).isoformat()),
            'submission_channel': self.channel, 'external_effects_authorized': False, 'credit_awarded': False, 'module_completion_eligible': False}
        serialized, digest = encode(saved)
        if len(serialized.encode()) > MAX_RECORD_BYTES:
            raise EnrollmentConflict('The complete capstone record exceeds its storage limit; no evidence was truncated')
        self.decode({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_hash, 'record_json': serialized, 'record_sha256': digest})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': body.request_id})
            if existing is None:
                raise EnrollmentConflict('This capstone identity was claimed by another operation')
            return await replay(existing)
        await self.after_save(operation, saved, replay=False)
        return saved
