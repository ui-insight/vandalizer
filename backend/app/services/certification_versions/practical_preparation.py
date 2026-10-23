"""Prepare owned, frozen practical inputs without dispatching or awarding credit."""
from pydantic import BaseModel, ConfigDict, Field

from app.models.system_config import SystemConfig
from app.services.storage import get_storage
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .learner_decisions import execution_requirement
from .outcomes import package_outcomes
from .runtime import CourseOperation


class PreparationUnavailable(ValueError):
    pass


class PreparationRejected(EnrollmentConflict):
    """Confirmed input rejection before saving this request; selection may be edited."""


class PreparationSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    artifact_id: str = Field(min_length=1, max_length=200, pattern=r'^\S+$')


async def configured_runtime():
    # Preparation must not create or repair global application settings.
    config = await SystemConfig.find_one()
    if config is None:
        raise CourseCatalogError('Assessed execution settings are unavailable; your saved work is preserved')
    # Runtime fingerprints require JSON data. Database identity and edit
    # attribution are not execution settings and must not invalidate a plan.
    return config.model_dump(mode='json', exclude={'id', 'updated_at', 'updated_by'})


class PracticalPreparation:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.inputs = LabInputRepository()
        self.runs = LabExecutionRepository()

    @staticmethod
    def eligible(package, module_id):
        contract = package_outcomes(package)
        if (module_id not in ('foundations', 'extraction_engine') or contract is None
                or not any(module.module_id == module_id for module in contract.modules)
                or execution_requirement(package, module_id) is None):
            raise PreparationUnavailable('This course does not offer preparation for this practical module')
        if module_id == 'foundations' and 'proposals/foundations.json' not in package.manifest.artifacts:
            raise PreparationUnavailable('This course does not offer preparation for this practical module')
        if module_id == 'extraction_engine':
            from .repair_case import load_repair_case
            if load_repair_case(package, module_id) is None:
                raise PreparationUnavailable('This course does not offer preparation for this practical module')

    @staticmethod
    def public(snapshot, run):
        if run and (run['plan']['input_snapshot_id'] != snapshot['uuid']
                or run['plan']['input_snapshot_sha256'] != encode(snapshot)[1]
                or any(run['plan'][key] != snapshot[key] for key in
                       ('user_id', 'enrollment_id', 'course_version', 'manifest_sha256', 'module_id'))):
            raise CourseCatalogError('The prepared run does not match its saved inputs')
        # All returned properties are intentionally selected. Runtime routing,
        # credentials, implementation details and raw source text remain private.
        return {
            'request_id': snapshot['uuid'], 'input_snapshot_id': snapshot['uuid'],
            'enrollment_id': snapshot['enrollment_id'], 'module_id': snapshot['module_id'],
            'course_version': snapshot['course_version'], 'manifest_sha256': snapshot['manifest_sha256'],
            'artifact_id': snapshot['artifact_id'], 'artifact_title': snapshot['artifact']['title'],
            'artifact_sha256': snapshot['artifact_sha256'], 'captured_at': snapshot['captured_at'],
            'fields': [item['searchphrase'] for item in snapshot['artifact']['fields']],
            'documents': [{'document_id': item['document_id'], 'assigned_filename': item['assigned_filename'],
                           'source_sha256': item['source_sha256']} for item in snapshot['documents']],
            'state': run['state'] if run else 'inputs_saved',
            'run_id': run['run_id'] if run else None,
            'plan_sha256': run['plan_sha256'] if run else None,
            'model_names': run['plan']['model_names'] if run else [],
            'scope_prompt_id': run['plan']['approval_requirement']['prompt_id']
                if run and run['plan'].get('approval_requirement') else None,
            'can_execute': False, 'credit_awarded': False, 'module_completion_eligible': False,
        }

    async def get(self, user_id, enrollment_id, request_id):
        snapshot = await self.inputs.get(user_id, request_id)
        if snapshot is None or snapshot.get('record_kind') is not None:
            raise PreparationUnavailable('This saved preparation is unavailable')
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        if (snapshot['enrollment_id'] != enrollment_id or snapshot['course_version'] != enrollment.course_version
                or snapshot['manifest_sha256'] != enrollment.manifest_sha256):
            raise EnrollmentConflict('This preparation belongs to a different course')
        return self.public(snapshot, await self.runs.get(user_id, request_id))

    async def prepare(self, user_id, enrollment_id, module_id, submission):
        repo = self.repository
        source = await repo.current(user_id)
        if source is None or source.uuid != enrollment_id:
            raise EnrollmentConflict('Select your existing course before preparing an assessed run')
        package = repo.catalog.load(source.course_version)
        self.eligible(package, module_id)
        async with repo.write_boundary(user_id, enrollment_id, operation='prepare_practical_run') as progress:
            operation = CourseOperation(user_id, package, progress, True)
            existing = await self.runs.records.find_one({'uuid': submission.request_id})
            if existing is not None:
                if (existing.get('user_id') != user_id or existing.get('enrollment_id') != enrollment_id
                        or existing.get('module_id') != module_id
                        or existing.get('input_snapshot_id') != submission.request_id):
                    raise EnrollmentConflict('This preparation reference was used for different work')
                run = self.runs.decode(existing)
                self.runs.check_operation(operation, run['plan'])
                snapshot = await self.inputs.get(user_id, submission.request_id)
                if snapshot is None:
                    raise EnrollmentConflict('The original prepared inputs are unavailable; they cannot be reconstructed from current work')
                if snapshot['artifact_id'] != submission.artifact_id:
                    raise EnrollmentConflict('This preparation reference was used for a different extraction')
                return self.public(snapshot, run)
            # The same request identity binds both records. If preparation was
            # interrupted after capture, GET exposes the saved-input state and
            # an explicit retry continues from that original snapshot.
            try:
                snapshot = await self.inputs.capture_extraction(operation, module_id, submission.artifact_id,
                                                               submission.request_id, get_storage())
            except EnrollmentConflict as exc:
                # A lost lease or an existing capture is not a definite unsaved
                # request. Keep those cases recoverable under the same ID.
                from .writes import require_lease
                await self.inputs._check_lease(require_lease(user_id, enrollment_id))
                if await self.inputs.records.find_one({'uuid': submission.request_id}) is not None:
                    raise
                raise PreparationRejected(str(exc)) from exc
            run = await self.runs.prepare(operation, snapshot['uuid'], submission.request_id,
                                          await configured_runtime())
            return self.public(snapshot, run)
