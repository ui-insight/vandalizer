"""Vandal Workflow Architect certification endpoints."""

import datetime
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import Settings
from app.dependencies import get_current_user, get_settings
from app.models.user import User
from app.routers.certification_connected import router as connected_router
from app.routers.certification_advanced import router as advanced_router
from app.routers.certification_output import router as output_router
from app.routers.certification_validation import router as validation_router
from app.routers.certification_batch import router as batch_router
from app.routers.certification_governance import router as governance_router
from app.routers.certification_selection import router as selection_router
from app.routers.certification_upgrades import router as upgrades_router
from app.services import certification_service as svc
from app.services.certificate_pdf import render_certificate_pdf
from app.services.certification_versions.runtime import course_operation
from app.services.certification_versions.runtime import current_operation
from app.services.certification_versions.credentials import CredentialRepository, CredentialSnapshot
from app.services.certification_versions.catalog import CourseCatalogError
from app.services.certification_versions.learner_decisions import DecisionSubmission, DecisionValidationError, LearnerDecisionRepository, load_prompt
from app.services.certification_versions.practical_preparation import PreparationSubmission
from app.services.certification_versions.practical_execution import ExecutionSubmission
from app.services.certification_versions.practical_assessment import AssessmentSubmission, AssessmentRetrySubmission
from app.services.certification_versions.process_submissions import ProcessSubmission
from app.services.certification_versions.workflow_design_inputs import DesignCaptureRequest
from app.services.certification_versions.workflow_design_submissions import WorkflowDesignSubmission


class AssessmentPayload(BaseModel):
    answers: dict


class LessonPositionPayload(BaseModel):
    module_id: str
    lesson_id: str
    expected_revision: int = Field(ge=0, strict=True)


class ScenarioSubmissionPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    bank_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    answers: dict[str, str]


class OutcomeCompletionPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    consent: Literal['complete_selected_saved_outcomes']
    review_attempt_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    scenario_attempt_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

    @model_validator(mode='after')
    def require_selection(self):
        if self.review_attempt_id is None and self.scenario_attempt_id is None:
            raise ValueError('Explicitly select original saved assessments')
        return self

router = APIRouter()
router.include_router(connected_router)
router.include_router(advanced_router)
router.include_router(output_router)
router.include_router(validation_router)
router.include_router(batch_router)
router.include_router(governance_router)
router.include_router(selection_router)
router.include_router(upgrades_router)


async def _upgrade_comparison(user, enrollment_id, target_version=None):
    from app.services.certification_versions.runtime import versioning_enabled
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.upgrade_comparison import UpgradeComparison, UpgradeUnavailable
    if not versioning_enabled():
        raise HTTPException(status_code=404, detail='Course comparison is not available')
    try:
        comparison = UpgradeComparison()
        if target_version is None:
            return await comparison.options(user.user_id, enrollment_id)
        return await comparison.inspect(user.user_id, enrollment_id, target_version)
    except UpgradeUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/upgrade-options')
async def get_upgrade_options(enrollment_id: str, user: User = Depends(get_current_user)):
    return await _upgrade_comparison(user, enrollment_id)


@router.get('/upgrade-preview')
async def get_upgrade_preview(enrollment_id: str, target_version: str, user: User = Depends(get_current_user)):
    return await _upgrade_comparison(user, enrollment_id, target_version)


def _credential_response(record: CredentialSnapshot):
    pdf = render_certificate_pdf(
        name=record.learner_name, level=record.level,
        certified_at=datetime.datetime.fromisoformat(record.certified_at) if record.certified_at else None,
        credential_id=record.credential_id.upper(),
        course_title=record.course_title, course_version=record.course_version,
        module_count=len(record.module_ids), legacy_unknown=record.provenance == 'legacy_completion_unverified',
        credential_promise=(record.credential_scope.promise if getattr(record, 'credential_scope', None) else None),
    )
    return Response(content=pdf, media_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="vandal-certification-{record.credential_id}.pdf"',
    })


@router.get('/credentials')
async def list_credentials(user: User = Depends(get_current_user)):
    """Read preserved credentials without consulting today's course or progress."""
    try:
        records = await CredentialRepository().list(user.user_id)
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {'credentials': [{
        'credential_id': record.credential_id, 'enrollment_id': record.enrollment_id,
        'learner_name': record.learner_name, 'course_title': record.course_title,
        'course_version': record.course_version, 'certified_at': record.certified_at,
        'provenance': record.provenance,
        **({'credential_scope': record.credential_scope.model_dump(mode='json')}
           if getattr(record, 'credential_scope', None) is not None else {}),
    } for record in records]}


@router.get('/credentials/{credential_id}/certificate')
async def download_preserved_certificate(credential_id: str, user: User = Depends(get_current_user)):
    try:
        record = await CredentialRepository().get(user.user_id, credential_id)
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail='This credential is unavailable')
    return _credential_response(record)


@router.put('/position')
@course_operation(write=True, http=True)
async def save_lesson_position(payload: LessonPositionPayload, user: User = Depends(get_current_user), enrollment_id: str | None = None):
    return await svc.save_learning_position(user.user_id, payload.module_id, payload.lesson_id, payload.expected_revision)


@router.get("/progress")
@course_operation(http=True)
async def get_progress(user: User = Depends(get_current_user)):
    return await svc.get_progress_dict(user.user_id)


@router.get('/course')
@course_operation(http=True)
async def get_course(user: User = Depends(get_current_user), enrollment_id: str | None = None):
    return await svc.get_course_definition(user.user_id)


@router.get("/certificate")
@course_operation(http=True)
async def download_certificate(user: User = Depends(get_current_user), enrollment_id: str | None = None):
    """Return the caller's certificate as a printable PDF, once certified."""
    prog = await svc.get_progress(user.user_id)
    if current_operation():
        record = await CredentialRepository().for_enrollment(user.user_id, prog.enrollment_id)
        if record is not None:
            return _credential_response(record)
        if prog.certified:
            raise HTTPException(status_code=409, detail='The original credential needs history reconciliation before download')
    if not prog.certified or not prog.certified_at:
        raise HTTPException(status_code=404, detail="Complete your selected course's requirements to earn a certificate")
    pdf = render_certificate_pdf(
        name=user.name or user.email or user.user_id,
        level=prog.level,
        certified_at=prog.certified_at,
        credential_id=str(prog.id)[-8:].upper(),
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="vandal-workflow-architect-certificate.pdf"'},
    )


@router.post("/modules/{module_id}/validate")
@course_operation(http=True)
async def validate_module(module_id: str, user: User = Depends(get_current_user), enrollment_id: str | None = None):
    result = await svc.validate_module(user.user_id, module_id)
    return result


@router.post("/modules/{module_id}/complete")
@course_operation(write=True, http=True)
async def complete_module(module_id: str, user: User = Depends(get_current_user), enrollment_id: str | None = None, request_id: str | None = None, payload: OutcomeCompletionPayload | None = None, expected_attempts: Annotated[int | None, Query(ge=0)] = None):
    selected = {}
    if expected_attempts is not None:
        selected['expected_attempts'] = expected_attempts
    if payload is not None:
        if not request_id:
            raise HTTPException(status_code=422, detail='Selected outcome completion requires an explicit request_id')
        selected['assessment_selection'] = payload.model_dump(exclude={'consent'}, exclude_none=True)
    result = await svc.complete_module(user.user_id, module_id, request_id=request_id, **selected)
    if "error" in result:
        detail = ({'message': result['error'], 'code': 'certification_execution_failed', 'attempt_id': result['attempt_id']}
                  if result.get('failure_kind') == 'execution' else result['error'])
        raise HTTPException(status_code=400, detail=detail)
    return result


@router.post("/modules/{module_id}/assessment")
@course_operation(write=True, http=True)
async def submit_assessment(
    module_id: str,
    payload: AssessmentPayload,
    user: User = Depends(get_current_user),
    enrollment_id: str | None = None,
):
    """Store self-assessment answers for a module."""
    result = await svc.store_assessment(user.user_id, module_id, payload.answers)
    return result


@router.get('/modules/{module_id}/lab-status')
@course_operation(http=True)
async def get_lab_status(module_id: str, user: User = Depends(get_current_user), enrollment_id: str | None = None):
    from app.services.certification_versions.lab_status import read_lab_status
    return await read_lab_status(user, module_id)


@router.post("/modules/{module_id}/provision")
@course_operation(write=True, http=True)
async def provision_module(
    module_id: str,
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    enrollment_id: str | None = None,
):
    """Provision sample documents for a certification module into the user's workspace."""
    result = await svc.provision_module_documents(user, module_id, settings)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/modules/{module_id}/exercise")
@course_operation(http=True)
async def get_exercise(module_id: str, user: User = Depends(get_current_user), enrollment_id: str | None = None):
    """Return the exercise definition for a certification module."""
    exercise = svc.get_exercise(module_id)
    if not exercise:
        raise HTTPException(status_code=404, detail=f"No exercise for module {module_id}")
    return exercise


@router.get('/modules/{module_id}/scenarios')
@course_operation(http=True)
async def get_scenario_assessment(module_id: str, user: User = Depends(get_current_user), enrollment_id: str | None = None):
    from app.services.certification_versions.scenario_submissions import module_bank
    operation = current_operation()
    if operation is None:
        raise HTTPException(status_code=404, detail='This course does not offer scenario assessments')
    return module_bank(operation.package, module_id).public_definition()


@router.post('/modules/{module_id}/scenarios')
@course_operation(write=True, http=True)
async def submit_scenario_assessment(module_id: str, payload: ScenarioSubmissionPayload,
        user: User = Depends(get_current_user), enrollment_id: str | None = None):
    from app.services.certification_versions.scenario_submissions import ScenarioSubmissionRepository
    operation = current_operation()
    if operation is None:
        raise HTTPException(status_code=404, detail='This course does not offer scenario assessments')
    return await ScenarioSubmissionRepository().submit(
        operation, module_id, payload.request_id, payload.bank_sha256, payload.answers, actor_user_id=user.user_id,
    )


@router.get('/scenario-attempts/{attempt_id}')
async def get_scenario_submission(attempt_id: str, user: User = Depends(get_current_user)):
    from app.services.certification_versions.scenario_submissions import ScenarioSubmissionRepository
    try:
        record = await ScenarioSubmissionRepository().status(user.user_id, attempt_id)
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail='This scenario submission is unavailable')
    return record


@router.get('/modules/{module_id}/decisions/{prompt_id}')
@course_operation(http=True)
async def get_practical_decision_prompt(module_id: str, prompt_id: str,
        user: User = Depends(get_current_user), enrollment_id: str | None = None):
    operation = current_operation()
    if operation is None:
        raise HTTPException(status_code=404, detail='This course does not offer practical decision capture')
    prompt = load_prompt(operation.package, module_id, prompt_id)
    return {**prompt.model_dump(mode='json'), 'prompt_sha256': prompt.digest}


@router.post('/modules/{module_id}/decisions/{prompt_id}')
@course_operation(write=True, http=True)
async def submit_practical_decision(module_id: str, prompt_id: str, payload: DecisionSubmission,
        user: User = Depends(get_current_user), enrollment_id: str | None = None):
    operation = current_operation()
    if operation is None:
        raise HTTPException(status_code=404, detail='This course does not offer practical decision capture')
    try:
        return await LearnerDecisionRepository().submit(operation, module_id, prompt_id, payload, actor_user_id=user.user_id)
    except DecisionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/learner-decisions/{decision_id}')
async def get_practical_decision(decision_id: str, user: User = Depends(get_current_user)):
    try:
        record = await LearnerDecisionRepository().get(user.user_id, decision_id)
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail='This learner decision is unavailable')
    return record


async def _course_history(user, enrollment_id=None):
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.course_history import CourseHistory
    try:
        history = CourseHistory()
        return await history.course(user.user_id, enrollment_id) if enrollment_id else await history.courses(user.user_id)
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/practical-history')
async def get_practical_history_courses(user: User = Depends(get_current_user)):
    return await _course_history(user)


@router.get('/practical-history/{enrollment_id}')
async def get_practical_history_course(enrollment_id: str, user: User = Depends(get_current_user)):
    return await _course_history(user, enrollment_id)


async def _scenario_history(user, enrollment_id, module_id, attempt_id=None):
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.scenario_history import ScenarioHistory
    try:
        history = ScenarioHistory()
        result = await history.attempt(user.user_id, enrollment_id, module_id, attempt_id) if attempt_id else await history.attempts(user.user_id, enrollment_id, module_id)
        if result is None:
            raise HTTPException(status_code=404, detail='This saved scenario result is unavailable')
        return result
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/practical-history/{enrollment_id}/modules/{module_id}/scenarios')
async def get_scenario_history(enrollment_id: str, module_id: str, user: User = Depends(get_current_user)):
    return await _scenario_history(user, enrollment_id, module_id)


@router.get('/practical-history/{enrollment_id}/modules/{module_id}/scenarios/{attempt_id}')
async def get_scenario_history_attempt(enrollment_id: str, module_id: str, attempt_id: str, user: User = Depends(get_current_user)):
    return await _scenario_history(user, enrollment_id, module_id, attempt_id)


async def _practical_history(user, enrollment_id, module_id, *, prompt_id=None, run_id=None):
    from app.services.certification_versions.runtime import versioning_enabled
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.practical_history import PracticalHistory
    try:
        history = PracticalHistory()
        if run_id is None:
            return await history.runs(user.user_id, enrollment_id, module_id, delivery_enabled=versioning_enabled())
        return await history.context(user.user_id, enrollment_id, module_id, prompt_id, run_id, delivery_enabled=versioning_enabled())
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/modules/{module_id}/practical-runs')
async def get_practical_runs(module_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await _practical_history(user, enrollment_id, module_id)


async def _practical_preparation(user, enrollment_id, *, module_id=None, payload=None, request_id=None):
    from app.services.certification_versions import runtime
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.practical_preparation import PracticalPreparation, PreparationUnavailable, PreparationRejected
    if payload is not None and not runtime.versioning_enabled():
        raise HTTPException(status_code=404, detail='Practical preparation is not available')
    try:
        service = PracticalPreparation()
        if payload is None:
            return await service.get(user.user_id, enrollment_id, request_id)
        return await service.prepare(user.user_id, enrollment_id, module_id, payload)
    except PreparationUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PreparationRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post('/modules/{module_id}/practical-runs')
async def prepare_practical_run(module_id: str, payload: PreparationSubmission, enrollment_id: str,
        user: User = Depends(get_current_user)):
    return await _practical_preparation(user, enrollment_id, module_id=module_id, payload=payload)


@router.get('/practical-preparations/{request_id}')
async def get_practical_preparation(request_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await _practical_preparation(user, enrollment_id, request_id=request_id)


async def _practical_execution(user, enrollment_id, run_id, payload=None):
    from app.services.certification_versions.runtime import versioning_enabled
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.practical_execution import PracticalExecution, ExecutionUnavailable
    from app.services.certification_versions.practical_preparation import PreparationUnavailable
    enabled = versioning_enabled()
    if payload is not None and not enabled:
        raise HTTPException(status_code=404, detail='Practical execution is not available')
    try:
        service = PracticalExecution()
        if payload is None:
            return await service.get(user.user_id, enrollment_id, run_id, delivery_enabled=enabled)
        return await service.execute(user.user_id, enrollment_id, run_id, payload)
    except (ExecutionUnavailable, PreparationUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/practical-runs/{run_id}/execution')
async def get_practical_execution(run_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await _practical_execution(user, enrollment_id, run_id)


@router.post('/practical-runs/{run_id}/execution')
async def execute_practical_run(run_id: str, payload: ExecutionSubmission, enrollment_id: str,
        user: User = Depends(get_current_user)):
    return await _practical_execution(user, enrollment_id, run_id, payload)


@router.get('/modules/{module_id}/decisions/{prompt_id}/runs/{run_id}')
async def get_practical_decision_context(module_id: str, prompt_id: str, run_id: str, enrollment_id: str,
        user: User = Depends(get_current_user)):
    return await _practical_history(user, enrollment_id, module_id, prompt_id=prompt_id, run_id=run_id)


async def _saved_review_delivery(user, enrollment_id, *, module_id=None, attempt_id=None):
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.review_delivery import ReviewDelivery, SavedReviewUnavailable
    # Like preserved credentials and decision receipts, owned history remains
    # readable when course delivery is disabled. These reads never initialize.
    try:
        delivery = ReviewDelivery()
        if attempt_id is not None:
            return await delivery.get(user.user_id, enrollment_id, attempt_id)
        return await delivery.list(user.user_id, enrollment_id, module_id)
    except SavedReviewUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/modules/{module_id}/automatic-reviews')
async def list_saved_automatic_reviews(module_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await _saved_review_delivery(user, enrollment_id, module_id=module_id)


@router.get('/automatic-reviews/{attempt_id}')
async def get_saved_automatic_review(attempt_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await _saved_review_delivery(user, enrollment_id, attempt_id=attempt_id)


@router.get('/modules/{module_id}/readiness')
async def preview_module_readiness(module_id: str, enrollment_id: str,
        review_attempt_id: str | None = None, scenario_attempt_id: str | None = None,
        user: User = Depends(get_current_user)):
    """Combine explicitly selected owned receipts; never grade or award credit."""
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.module_readiness import ModuleReadiness
    from app.services.certification_versions.review_delivery import SavedReviewUnavailable
    try:
        return await ModuleReadiness().preview(user.user_id, enrollment_id, module_id,
            review_attempt_id=review_attempt_id, scenario_attempt_id=scenario_attempt_id)
    except SavedReviewUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


async def _request_automatic_assessment(user, enrollment_id, payload, *, run_id=None, parent_id=None):
    from app.services.certification_versions.runtime import versioning_enabled
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.practical_assessment import PracticalAssessment
    from app.services.certification_versions.practical_execution import ExecutionUnavailable
    from app.services.certification_versions.practical_preparation import PreparationUnavailable
    from app.services.certification_versions.review_delivery import SavedReviewUnavailable
    if not versioning_enabled():
        raise HTTPException(status_code=404, detail='Automatic assessment is not available')
    try:
        service = PracticalAssessment()
        if parent_id is not None:
            return await service.retry(user.user_id, enrollment_id, parent_id, payload)
        return await service.request(user.user_id, enrollment_id, run_id, payload)
    except (ExecutionUnavailable, PreparationUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=getattr(exc, 'detail', str(exc))) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post('/practical-runs/{run_id}/automatic-reviews')
async def request_automatic_assessment(run_id: str, payload: AssessmentSubmission, enrollment_id: str,
        user: User = Depends(get_current_user)):
    return await _request_automatic_assessment(user, enrollment_id, payload, run_id=run_id)


@router.post('/automatic-reviews/{attempt_id}/retry')
async def retry_automatic_assessment(attempt_id: str, payload: AssessmentRetrySubmission, enrollment_id: str,
        user: User = Depends(get_current_user)):
    return await _request_automatic_assessment(user, enrollment_id, payload, parent_id=attempt_id)



async def _process_design_action(user, enrollment_id, *, payload=None, submission_id=None, assessment=False, parent_id=None):
    from app.services.certification_versions import runtime
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.process_delivery import ProcessDelivery, ProcessAssessment, ProcessDesignUnavailable
    from app.services.certification_versions.review_delivery import SavedReviewUnavailable
    if payload is not None and not runtime.versioning_enabled():
        raise HTTPException(status_code=404, detail='Process-design assessment is not available')
    try:
        if assessment:
            service = ProcessAssessment()
            if parent_id is not None:
                return await service.retry(user.user_id, enrollment_id, parent_id, payload)
            return await service.request(user.user_id, enrollment_id, submission_id, payload)
        service = ProcessDelivery()
        if payload is not None:
            return await service.save(user.user_id, enrollment_id, payload)
        if submission_id is not None:
            return await service.get(user.user_id, enrollment_id, submission_id)
        return await service.list(user.user_id, enrollment_id, delivery_enabled=runtime.versioning_enabled())
    except (ProcessDesignUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=getattr(exc, 'detail', str(exc))) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/modules/process_mapping/process-designs')
async def list_process_designs(enrollment_id: str, user: User = Depends(get_current_user)):
    return await _process_design_action(user, enrollment_id)


@router.post('/modules/process_mapping/process-designs')
async def save_process_design(payload: ProcessSubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await _process_design_action(user, enrollment_id, payload=payload)


@router.get('/process-designs/{submission_id}')
async def get_process_design(submission_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await _process_design_action(user, enrollment_id, submission_id=submission_id)


@router.post('/process-designs/{submission_id}/automatic-reviews')
async def assess_process_design(submission_id: str, payload: AssessmentSubmission, enrollment_id: str,
        user: User = Depends(get_current_user)):
    return await _process_design_action(user, enrollment_id, payload=payload, submission_id=submission_id, assessment=True)


@router.post('/process-automatic-reviews/{attempt_id}/retry')
async def retry_process_assessment(attempt_id: str, payload: AssessmentRetrySubmission, enrollment_id: str,
        user: User = Depends(get_current_user)):
    return await _process_design_action(user, enrollment_id, payload=payload, parent_id=attempt_id, assessment=True)


async def _workflow_design_action(user, enrollment_id, *, payload=None, reference=None, action='list'):
    from app.services.certification_versions import runtime
    from app.services.certification_versions.enrollments import EnrollmentConflict
    from app.services.certification_versions.workflow_design_delivery import WorkflowDesignDelivery, WorkflowDesignAssessment, WorkflowDesignUnavailable
    from app.services.certification_versions.review_delivery import SavedReviewUnavailable
    if payload is not None and not runtime.versioning_enabled():
        raise HTTPException(status_code=404, detail='Workflow Design assessment is not available')
    try:
        if action in ('assess', 'retry'):
            service = WorkflowDesignAssessment()
            method = service.request if action == 'assess' else service.retry
            return await method(user.user_id, enrollment_id, reference, payload)
        service = WorkflowDesignDelivery()
        if payload is not None:
            return await service.save(user.user_id, enrollment_id, payload, capture=action == 'capture')
        if reference is not None:
            return await service.get(user.user_id, enrollment_id, reference, capture=action == 'capture')
        return await service.list(user.user_id, enrollment_id, delivery_enabled=runtime.versioning_enabled())
    except (WorkflowDesignUnavailable, SavedReviewUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EnrollmentConflict as exc:
        raise HTTPException(status_code=409, detail=getattr(exc, 'detail', str(exc))) from exc
    except CourseCatalogError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/modules/workflow_design/designs')
async def list_workflow_designs(enrollment_id: str, user: User = Depends(get_current_user)):
    return await _workflow_design_action(user, enrollment_id)


@router.post('/modules/workflow_design/design-captures')
async def capture_workflow_design(payload: DesignCaptureRequest, enrollment_id: str, user: User = Depends(get_current_user)):
    return await _workflow_design_action(user, enrollment_id, payload=payload, action='capture')


@router.get('/workflow-design-captures/{snapshot_id}')
async def get_workflow_design_capture(snapshot_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await _workflow_design_action(user, enrollment_id, reference=snapshot_id, action='capture')


@router.post('/modules/workflow_design/designs')
async def approve_workflow_design(payload: WorkflowDesignSubmission, enrollment_id: str, user: User = Depends(get_current_user)):
    return await _workflow_design_action(user, enrollment_id, payload=payload, action='approve')


@router.get('/workflow-designs/{submission_id}')
async def get_workflow_design(submission_id: str, enrollment_id: str, user: User = Depends(get_current_user)):
    return await _workflow_design_action(user, enrollment_id, reference=submission_id)


@router.post('/workflow-designs/{submission_id}/automatic-reviews')
async def assess_workflow_design(submission_id: str, payload: AssessmentSubmission, enrollment_id: str,
        user: User = Depends(get_current_user)):
    return await _workflow_design_action(user, enrollment_id, payload=payload, reference=submission_id, action='assess')


@router.post('/workflow-design-automatic-reviews/{attempt_id}/retry')
async def retry_workflow_design_assessment(attempt_id: str, payload: AssessmentRetrySubmission, enrollment_id: str,
        user: User = Depends(get_current_user)):
    return await _workflow_design_action(user, enrollment_id, payload=payload, reference=attempt_id, action='retry')


@router.get("/levels")
async def get_levels():
    """Return the level definitions and XP thresholds."""
    return {
        "levels": [{"name": name, "xp_threshold": xp} for name, xp in svc.LEVELS],
        "module_xp": svc.MODULE_XP,
        "module_order": svc.MODULE_ORDER,
    }
