"""Owned design saving/history and explicit assessment; no automatic execution."""
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .practical_assessment import PracticalAssessment, assessment_model
from . import practical_preparation
from .process_case import load_process_case
from .process_submissions import ProcessSubmissionRepository
from .review_delivery import ReviewDelivery, SavedReviewUnavailable
from .runtime import CourseOperation


class ProcessDesignUnavailable(ValueError):
    pass


class ProcessDelivery:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.records = ProcessSubmissionRepository()

    async def course(self, user_id, enrollment_id):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        if 'process-cases/process_mapping.json' not in package.manifest.artifacts:
            raise ProcessDesignUnavailable('This course does not offer the process-design assessment')
        return enrollment, package, load_process_case(package)

    @staticmethod
    def verify(record, enrollment, case):
        if (record['user_id'] != enrollment.user_id or record['enrollment_id'] != enrollment.uuid
                or record['course_version'] != enrollment.course_version or record['manifest_sha256'] != enrollment.manifest_sha256
                or record['module_id'] != 'process_mapping' or record['case'] != case.public_definition()):
            raise CourseCatalogError('The saved design does not match its original course requirements')
        return record

    async def get(self, user_id, enrollment_id, submission_id):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        saved = await self.records.get(user_id, submission_id)
        if saved is None:
            raise ProcessDesignUnavailable('This saved process design is unavailable')
        return self.verify(saved, enrollment, case)

    async def list(self, user_id, enrollment_id, *, delivery_enabled=False):
        enrollment, _, case = await self.course(user_id, enrollment_id)
        rows = await self.records.records.find({'user_id': user_id, 'enrollment_id': enrollment_id,
            'module_id': 'process_mapping'}).sort('_id', -1).limit(51).to_list(51)
        submissions = []
        for row in rows[:50]:
            saved = self.verify(self.records.decode(row), enrollment, case)
            submissions.append({'submission_id': saved['uuid'], 'submitted_at': saved['submitted_at'],
                'previous_submission_id': saved['submission']['previous_submission_id']})
        selection = await self.repository.selections.find_one({'user_id': user_id})
        writable = (delivery_enabled and enrollment.state in ('active', 'completed')
                    and selection is not None and selection.get('active_enrollment_id') == enrollment_id)
        return {'enrollment_id': enrollment_id, 'module_id': 'process_mapping',
                'course_version': enrollment.course_version, 'manifest_sha256': enrollment.manifest_sha256,
                'case': case.public_definition(), 'submissions': submissions, 'older_submissions_available': len(rows) > 50,
                'can_submit': writable, 'read_only_reason': None if writable else 'This is preserved course history. Select an available current course before saving new work.'}

    async def save(self, user_id, enrollment_id, payload):
        current = await self.repository.current(user_id)
        if current is None or current.uuid != enrollment_id:
            raise EnrollmentConflict('Select your existing course before saving a process design')
        _, package, _ = await self.course(user_id, enrollment_id)
        async with self.repository.write_boundary(user_id, enrollment_id, operation='save_process_design') as progress:
            return await self.records.submit(CourseOperation(user_id, package, progress, True), payload, actor_user_id=user_id)


class ProcessAssessment(PracticalAssessment):
    module_id = 'process_mapping'
    channel = 'trusted_saved_process_records'
    reference_key = 'process_submission_id'
    assessment_kind = 'process_design_review_draft'
    delivery_class = ProcessDelivery
    prepare_method = 'prepare_from_process'

    def __init__(self, repository=None):
        super().__init__(repository or EnrollmentRepository())

    async def existing(self, user_id, enrollment_id, submission_id, request_id, parent_id=None):
        raw = await self.reviews.records.find_one({'uuid': request_id})
        if raw is None:
            return None
        saved = self.reviews.decode(raw)
        record = saved['record']
        if (record['user_id'] != user_id or record['enrollment_id'] != enrollment_id
                or record['module_id'] != self.module_id
                or record['submission_channel'] != self.channel
                or record.get('provenance', {}).get(self.reference_key) != submission_id
                or record.get('parent_attempt_id') != parent_id):
            raise EnrollmentConflict('This assessment reference belongs to different saved work')
        return saved

    async def request(self, user_id, enrollment_id, submission_id, payload):
        await self.selected(user_id, enrollment_id)
        saved = await self.existing(user_id, enrollment_id, submission_id, payload.request_id)
        if saved is not None:
            return await self.finish(user_id, enrollment_id, saved)
        delivery = self.delivery_class(self.repository)
        await delivery.get(user_id, enrollment_id, submission_id)
        _, package, _ = await delivery.course(user_id, enrollment_id)
        config = await practical_preparation.configured_runtime()
        model = assessment_model(config)
        async with self.repository.write_boundary(user_id, enrollment_id, operation='prepare_process_review') as progress:
            saved = await getattr(self.reviews, self.prepare_method)(CourseOperation(user_id, package, progress, True),
                submission_id, payload.request_id, actor_user_id=user_id, model_name=model, system_config=config)
        return await self.finish(user_id, enrollment_id, saved, config)

    async def retry(self, user_id, enrollment_id, parent_id, payload):
        await self.selected(user_id, enrollment_id)
        parent = await ReviewDelivery(self.repository).get(user_id, enrollment_id, parent_id)
        if parent['module_id'] != self.module_id or parent['assessment_kind'] != self.assessment_kind:
            raise SavedReviewUnavailable('This assessment does not belong to this design module')
        saved = await self.existing(user_id, enrollment_id, parent[self.reference_key], payload.request_id, parent_id)
        if saved is not None:
            return await self.finish(user_id, enrollment_id, saved)
        config = await practical_preparation.configured_runtime()
        async with self.repository.write_boundary(user_id, enrollment_id, operation='retry_process_review') as progress:
            package = self.repository.catalog.load(progress.course_version)
            saved = await self.reviews.prepare_retry(CourseOperation(user_id, package, progress, True), parent_id,
                payload.request_id, actor_user_id=user_id, system_config=config)
        return await self.finish(user_id, enrollment_id, saved, config)
