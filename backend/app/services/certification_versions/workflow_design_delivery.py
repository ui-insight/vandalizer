"""Owned capture, approval and history; automatic assessment is explicit."""
from app.models.workflow import Workflow
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .process_delivery import ProcessAssessment, ProcessDelivery
from .runtime import CourseOperation
from .workflow_design_case import load_workflow_design_case
from .workflow_design_inputs import WorkflowDesignInputRepository
from .workflow_design_submissions import WorkflowDesignSubmissionRepository


class WorkflowDesignUnavailable(ValueError):
    pass


class WorkflowDesignDelivery:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.inputs = WorkflowDesignInputRepository()
        self.records = WorkflowDesignSubmissionRepository()

    async def course(self, user_id, enrollment_id):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        if 'design-cases/workflow_design.json' not in package.manifest.artifacts:
            raise WorkflowDesignUnavailable('This course does not offer Workflow Design assessment')
        return enrollment, package, load_workflow_design_case(package)

    @staticmethod
    def verify(saved, enrollment, case, *, capture=False):
        snapshot = saved if capture else saved['input_snapshot']
        if (any(saved[key] != value for key, value in {'user_id': enrollment.user_id,
                'enrollment_id': enrollment.uuid, 'course_version': enrollment.course_version,
                'manifest_sha256': enrollment.manifest_sha256, 'module_id': 'workflow_design'}.items())
                or snapshot['case'] != case.public_definition()):
            raise CourseCatalogError('The saved workflow design does not match its original course')
        return saved

    async def get(self, user_id, enrollment_id, submission_id, *, capture=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        saved = await (self.inputs if capture else self.records).get(user_id, submission_id)
        if saved is None:
            raise WorkflowDesignUnavailable('This saved workflow design is unavailable')
        saved = self.verify(saved, enrollment, case, capture=capture)
        return {**saved, 'input_snapshot_sha256': encode(saved)[1]} if capture else saved

    async def list(self, user_id, enrollment_id, *, delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        query = {'user_id': user_id, 'enrollment_id': enrollment_id, 'module_id': 'workflow_design'}
        rows = await self.records.records.find(query).sort('_id', -1).limit(51).to_list(51)
        submissions = []
        for row in rows[:50]:
            saved = self.verify(self.records.decode(row), enrollment, case)
            submissions.append({'submission_id': saved['uuid'], 'submitted_at': saved['submitted_at'],
                'previous_submission_id': saved['submission']['previous_submission_id'],
                'input_snapshot_id': saved['submission']['input_snapshot_id'],
                'workflow_name': saved['input_snapshot']['artifact']['workflow']['name']})
        selection = await self.repository.selections.find_one({'user_id': user_id})
        writable = (delivery_enabled and enrollment.state in ('active', 'completed')
                    and selection is not None and selection.get('active_enrollment_id') == enrollment_id)
        workflows, process_choices, older_workflows, older_processes = [], [], False, False
        if writable:
            owned = await Workflow.find({'user_id': user_id}).sort('-updated_at').limit(51).to_list()
            workflows = [{'workflow_id': str(item.id), 'name': item.name, 'version': item.version} for item in owned[:50]]
            older_workflows = len(owned) > 50
            maps = await ProcessDelivery(self.repository).list(user_id, enrollment_id)
            process_choices, older_processes = maps['submissions'], maps['older_submissions_available']
        return {'enrollment_id': enrollment_id, 'module_id': 'workflow_design', 'course_version': enrollment.course_version,
                'manifest_sha256': enrollment.manifest_sha256, 'case': case.public_definition(), 'submissions': submissions,
                'older_submissions_available': len(rows) > 50, 'workflows': workflows, 'older_workflows_available': older_workflows,
                'process_choices': process_choices, 'older_process_choices_available': older_processes,
                'can_submit': writable, 'read_only_reason': None if writable else 'This is preserved course history. Select an available current course before saving new work.'}

    async def save(self, user_id, enrollment_id, payload, *, capture=False):
        current = await self.repository.current(user_id)
        if current is None or current.uuid != enrollment_id:
            raise EnrollmentConflict('Select your existing course before saving Workflow Design work')
        _, package, _ = await self.course(user_id, enrollment_id)
        async with self.repository.write_boundary(user_id, enrollment_id, operation='save_workflow_design') as progress:
            operation = CourseOperation(user_id, package, progress, True)
            if capture:
                saved = await self.inputs.capture(operation, payload, actor_user_id=user_id)
                return {**saved, 'input_snapshot_sha256': encode(saved)[1]}
            return await self.records.submit(operation, payload, actor_user_id=user_id)


class WorkflowDesignAssessment(ProcessAssessment):
    module_id = 'workflow_design'
    channel = 'trusted_saved_workflow_design_records'
    reference_key = 'workflow_design_submission_id'
    assessment_kind = 'workflow_design_review_draft'
    delivery_class = WorkflowDesignDelivery
    prepare_method = 'prepare_from_workflow_design'

    def __init__(self, repository=None):
        super().__init__(repository or EnrollmentRepository())
