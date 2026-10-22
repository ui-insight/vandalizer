"""Learner-requested automatic assessment from trusted saved records only."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import practical_preparation as preparation
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .practical_execution import PracticalExecution
from .review_attempts import ReviewAttemptRepository
from .review_delivery import ReviewDelivery, SavedReviewUnavailable
from .runtime import CourseOperation


class AssessmentSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    consent: Literal['assess_saved_work']


class AssessmentRetrySubmission(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    consent: Literal['retry_saved_assessment']


def assessment_model(config):
    """Use the system judge/default; never a learner-selected chat model.

    An explicitly configured but missing judge must not silently change the
    assessment model. With neither setting, use the existing app's first-model
    default, and freeze that choice in the assessment receipt.
    """
    models = [item.get('name') for item in config.get('available_models', []) if isinstance(item, dict) and item.get('name')]
    selected = (config.get('validation_judge_model') or config.get('default_model') or (models[0] if models else '')).strip()
    if not selected or models.count(selected) != 1:
        raise CourseCatalogError('The configured automatic assessment model is unavailable; no assessment was started')
    return selected


class PracticalAssessment:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.reviews = ReviewAttemptRepository()

    async def selected(self, user_id, enrollment_id):
        source = await self.repository.current(user_id)
        if source is None or source.uuid != enrollment_id:
            raise EnrollmentConflict('Select your existing course before requesting automatic assessment')
        return source

    async def existing(self, user_id, enrollment_id, run_id, request_id, parent_id=None):
        raw = await self.reviews.records.find_one({'uuid': request_id})
        if raw is None:
            return None
        saved = self.reviews.decode(raw)
        record = saved['record']
        if (record['user_id'] != user_id or record['enrollment_id'] != enrollment_id
                or record['module_id'] not in ('foundations', 'extraction_engine') or record.get('provenance', {}).get('run_id') != run_id
                or record['submission_channel'] != 'trusted_saved_practical_records'
                or record.get('parent_attempt_id') != parent_id):
            raise EnrollmentConflict('This assessment reference belongs to different saved work')
        return saved

    async def finish(self, user_id, enrollment_id, saved, config=None):
        # A replay/recovery of in-flight or terminal work requires no settings.
        # evaluate_saved never resets an evaluating intent or dispatches twice.
        if saved['state'] == 'prepared' and config is None:
            config = await preparation.configured_runtime()
        await self.reviews.evaluate_saved(self.repository, user_id, enrollment_id, saved['attempt_id'], config or {})
        return await ReviewDelivery(self.repository).get(user_id, enrollment_id, saved['attempt_id'])

    async def request(self, user_id, enrollment_id, run_id, submission):
        source = await self.selected(user_id, enrollment_id)
        saved = await self.existing(user_id, enrollment_id, run_id, submission.request_id)
        if saved is not None:
            return await self.finish(user_id, enrollment_id, saved)
        _, package = await PracticalExecution(self.repository).owned(user_id, enrollment_id, run_id)
        config = await preparation.configured_runtime()
        model = assessment_model(config)
        async with self.repository.write_boundary(user_id, source.uuid, operation='prepare_trusted_review') as progress:
            saved = await self.reviews.prepare_from_run(CourseOperation(user_id, package, progress, True), run_id,
                submission.request_id, actor_user_id=user_id, model_name=model, system_config=config)
        return await self.finish(user_id, enrollment_id, saved, config)

    async def retry(self, user_id, enrollment_id, parent_id, submission):
        await self.selected(user_id, enrollment_id)
        # Validate the parent's owned pinned public contract before allowing a
        # child; an internal/untrusted producer cannot become a learner retry.
        parent = await ReviewDelivery(self.repository).get(user_id, enrollment_id, parent_id)
        if parent['module_id'] not in ('foundations', 'extraction_engine'):
            raise SavedReviewUnavailable('Automatic assessment is unavailable for this module')
        saved = await self.existing(user_id, enrollment_id, parent['run_id'], submission.request_id, parent_id)
        if saved is not None:
            return await self.finish(user_id, enrollment_id, saved)
        config = await preparation.configured_runtime()
        async with self.repository.write_boundary(user_id, enrollment_id, operation='prepare_automatic_review_retry') as progress:
            package = self.repository.catalog.load(progress.course_version)
            saved = await self.reviews.prepare_retry(CourseOperation(user_id, package, progress, True), parent_id,
                submission.request_id, actor_user_id=user_id, system_config=config)
        return await self.finish(user_id, enrollment_id, saved, config)
