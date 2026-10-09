"""Read and verify original saved work under a held source-course boundary.

This neither recovers workers nor rejudges evidence. Every supported record is
retained in its original enrollment. The returned digest describes this read,
not permission to activate later or proof of outcome equivalence.
"""
from importlib import import_module

from app.models import certification as models
from .attempts import AttemptRepository, encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .lab_inputs import LabInputRepository
from .outcomes import package_outcomes
from .transition_preview import fingerprint
from .writes import require_lease


COLLECTIONS = {
    'inputs': models.CertificationLabInput,
    'runs': models.CertificationLabExecution,
    'decisions': models.CertificationLearnerDecision,
    'reviews': models.CertificationReviewAttempt,
    'scenarios': models.CertificationScenarioAttempt,
    'processes': models.CertificationProcessSubmission,
    'designs': models.CertificationWorkflowDesignSubmission,
    'completions': models.CertificationAttempt,
    'recoveries': models.CertificationRecoveryRecord,
}
INPUT_DECODERS = {
    'foundations': ('lab_inputs', 'LabInputRepository'),
    'extraction_engine': ('lab_inputs', 'LabInputRepository'),
    'workflow_design': ('workflow_design_inputs', 'WorkflowDesignInputRepository'),
    'multi_step': ('connected_workflow_inputs', 'ConnectedWorkflowInputRepository'),
    'advanced_nodes': ('advanced_workflow_inputs', 'AdvancedWorkflowInputRepository'),
    'output_delivery': ('output_workflow_inputs', 'OutputWorkflowInputRepository'),
    'validation_qa': ('validation_inputs', 'ValidationInputRepository'),
    'batch_processing': ('batch_inputs', 'BatchInputRepository'),
    'governance': ('governance_inputs', 'GovernanceInputRepository'),
}
RUN_DECODERS = {
    'foundations': ('lab_execution', 'LabExecutionRepository'),
    'extraction_engine': ('lab_execution', 'LabExecutionRepository'),
    'multi_step': ('connected_workflow_preparation', 'ConnectedWorkflowPreparation'),
    'advanced_nodes': ('advanced_workflow_preparation', 'AdvancedWorkflowPreparation'),
    'output_delivery': ('output_workflow_preparation', 'OutputWorkflowPreparation'),
    'validation_qa': ('validation_preparation', 'ValidationPreparation'),
    'batch_processing': ('batch_preparation', 'BatchPreparation'),
    'governance': ('governance_preparation', 'GovernancePreparation'),
}
DECISION_DECODERS = {
    'connected_workflow_scope': ('connected_workflow_approval', 'ConnectedScopeRepository'),
    'budget_workflow_scope': ('advanced_workflow_approval', 'AdvancedScopeRepository'),
    'output_generation_scope': ('output_workflow_approval', 'OutputScopeRepository'),
    'validation_suite_scope': ('validation_approval', 'ValidationScopeRepository'),
    'bounded_batch_scope': ('batch_approval', 'BatchScopeRepository'),
    'bounded_governance_execution': ('governance_approval', 'GovernanceApprovalRepository'),
    'connected_workflow_result_review': ('connected_workflow_reviews', 'ConnectedReviewRepository'),
    'connected_stopped_run_recovery_decision': ('connected_recovery_decisions', 'ConnectedRecoveryDecisionRepository'),
    'budget_result_review': ('advanced_workflow_reviews', 'AdvancedReviewRepository'),
    'output_file_inspection_and_release': ('output_file_reviews', 'OutputFileReviewRepository'),
    'output_private_training_handoff': ('output_private_handoff', 'OutputPrivateHandoffRepository'),
    'output_delivery_result_review': ('output_outcome_reviews', 'OutputOutcomeReviewRepository'),
    'validation_representative_suite': ('validation_suites', 'ValidationSuiteRepository'),
    'validation_result_review': ('validation_reviews', 'ValidationReviewRepository'),
    'batch_result_review': ('batch_reviews', 'BatchReviewRepository'),
    'governance_scope_correction': ('governance_scope', 'GovernanceScopeCorrection'),
    'governance_original_source_finding': ('governance_findings', 'GovernanceFindingRepository'),
    'governance_accountable_memo': ('governance_memos', 'GovernanceMemoRepository'),
    'governance_memo_release_choice': ('governance_release', 'GovernanceReleaseRepository'),
    'governance_private_training_handoff': ('governance_handoff', 'GovernanceHandoffRepository'),
    'governance_final_supervision_review': ('governance_reviews', 'GovernanceReviewRepository'),
}


def decode_with(mapping, key, raw):
    if key not in mapping:
        raise CourseCatalogError('This saved work has no supported preservation integrity check')
    module, name = mapping[key]
    return getattr(import_module('.' + module, __package__), name).decode(raw)


def check_identity(raw, enrollment, package, *, recovery=False):
    expected = {'user_id': enrollment.user_id, 'enrollment_id': enrollment.uuid}
    if not recovery:
        expected.update(course_version=enrollment.course_version, manifest_sha256=enrollment.manifest_sha256)
    if (any(raw.get(key) != value for key, value in expected.items())
            or (not recovery and raw.get('module_id') not in {module.id for module in package.manifest.modules})):
        raise CourseCatalogError('Saved work differs from its original learner or pinned course')


def check_completion(raw, enrollment, package):
    if raw['state'] not in ('applied', 'rejected', 'failed'):
        raise EnrollmentConflict('Resolve the original completion before changing courses')
    if raw.get('rubric_id') != package.manifest.rubric_id or raw.get('artifact_sha256') != package.manifest.artifacts:
        raise CourseCatalogError('The original completion requirements changed')
    progress = AttemptRepository.payload(raw, 'progress')
    if any(progress.get(key) != value for key, value in {
            'user_id': enrollment.user_id, 'enrollment_id': enrollment.uuid, 'course_version': enrollment.course_version}.items()):
        raise CourseCatalogError('The original completion progress belongs to another course')
    AttemptRepository.assessment_selection(raw)
    if raw['state'] != 'failed' or raw.get('validation_json') is not None:
        AttemptRepository.payload(raw, 'validation')
    result = AttemptRepository.payload(raw, 'result')
    if result.get('attempt_id') != raw['uuid']:
        raise CourseCatalogError('The original completion result identifies another request')


def check_recovery(raw, enrollment):
    if raw['state'] != 'completed':
        raise EnrollmentConflict('Confirm the original recovery before changing courses')
    request = AttemptRepository.payload(raw, 'request')
    review = AttemptRepository.payload(raw, 'review')
    result = AttemptRepository.payload(raw, 'result')
    identity = {'user_id': enrollment.user_id, 'enrollment_id': enrollment.uuid}
    if (any(request.get(key) != value or review.get(key) != value for key, value in identity.items())
            or request.get('request_id') != raw['uuid'] or result.get('request_id') != raw['uuid']
            or request.get('actor_user_id') != raw['actor_user_id'] or result.get('actor_user_id') != raw['actor_user_id']
            or request.get('review_sha256') != raw['review_sha256']
            or review.get('course_version') != enrollment.course_version or review.get('manifest_sha256') != enrollment.manifest_sha256
            or result.get('enrollment_id') != enrollment.uuid or result.get('course_version') != enrollment.course_version
            or result.get('reason') != request.get('reason')):
        raise CourseCatalogError('The original recovery receipt changed its reviewed identity')


def check_decision(raw, package):
    from .learner_decisions import DecisionSubmission, LearnerDecisionRepository, load_prompt
    saved = LearnerDecisionRepository.decode(raw)
    kind = saved.get('record_kind')
    if kind is not None:
        return decode_with(DECISION_DECODERS, kind, raw)
    if saved['module_id'] not in ('foundations', 'extraction_engine'):
        raise CourseCatalogError('This saved learner decision needs a supported integrity check')
    body = DecisionSubmission.model_validate(saved['submission'])
    prompt = load_prompt(package, saved['module_id'], saved['prompt_id'])
    identity = {key: saved[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version',
                                          'manifest_sha256', 'run_id', 'prompt_id')}
    if (body.request_id != saved['uuid'] or body.run_id != saved['run_id']
            or body.prompt_sha256 != prompt.digest or saved['prompt_sha256'] != prompt.digest
            or saved['prompt'] != prompt.model_dump(mode='json') or body.choice not in prompt.choices
            or saved['submission_channel'] != 'authenticated_learner_request' or saved['credit_awarded'] is not False
            or saved['request_sha256'] != encode({**identity, 'submission': body.model_dump(mode='json', exclude_none=True)})[1]):
        raise CourseCatalogError('The original learner decision changed its prompt or request')
    return saved


class TransitionRecordReconciliation:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()

    async def inventory(self, user_id, enrollment_id):
        query = {'user_id': user_id, 'enrollment_id': enrollment_id}
        return {kind: await model.get_motor_collection().find(query).sort('uuid', 1).to_list(None)
                for kind, model in COLLECTIONS.items()}

    async def check_boundary(self, lease):
        if (await self.repository.selections.find_one(lease.selection_filter()) is None
                or await self.repository.progress.find_one(lease.progress_filter()) is None):
            raise EnrollmentConflict('Preservation verification lost its original course boundary')

    async def inspect(self, user_id, enrollment_id):
        lease = require_lease(user_id, enrollment_id)
        await self.check_boundary(lease)
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        if package.manifest_sha256 != enrollment.manifest_sha256:
            raise CourseCatalogError('The original course requirements changed')
        original = await self.inventory(user_id, enrollment_id)
        self.verify_inventory(original, enrollment, package)
        # Compare actual bytes, not just claimed digests. No provider, grading,
        # retry, cancellation, artifact deletion or history mutation occurs.
        if fingerprint(original) != fingerprint(await self.inventory(user_id, enrollment_id)):
            raise EnrollmentConflict('Saved work changed during preservation verification')
        await self.check_boundary(lease)
        result = {'schema_version': 1, 'source_enrollment_id': enrollment_id,
                  'source_manifest_sha256': enrollment.manifest_sha256, 'read_only': True,
                  'credit_transferred': False, 'can_activate': False,
                  'record_counts': {kind: len(rows) for kind, rows in original.items()},
                  'records_sha256': fingerprint(original)}
        return {**result, 'reconciliation_sha256': encode(result)[1]}

    @classmethod
    def verify_inventory(cls, original, enrollment, package):
        """Pure integrity check shared by held commits and read-only previews."""
        try:
            for kind, records in original.items():
                if len({row['uuid'] for row in records}) != len(records):
                    raise CourseCatalogError('Saved work contains duplicate request identities')
                for row in records:
                    check_identity(row, enrollment, package, recovery=kind == 'recoveries')
                    cls.check(kind, row, enrollment, package)
            cls.check_run_inputs(original)
        except (KeyError, TypeError, ValueError, AttributeError, StopIteration) as exc:
            if isinstance(exc, (CourseCatalogError, EnrollmentConflict)):
                raise
            raise CourseCatalogError('Original saved work needs integrity reconciliation before changing courses') from exc

    @staticmethod
    def check(kind, raw, enrollment, package):
        if kind == 'inputs':
            saved = LabInputRepository.decode(raw)
            if raw['module_id'] == 'advanced_nodes' and saved.get('record_kind') == 'advanced_calculation_input':
                from .advanced_calculation_records import AdvancedCalculationRepository
                AdvancedCalculationRepository.decode(raw)
            else:
                decode_with(INPUT_DECODERS, raw['module_id'], raw)
            if raw['module_id'] in ('foundations', 'extraction_engine') and saved.get('record_kind') is not None:
                raise CourseCatalogError('Unsupported extraction input kind')
        elif kind == 'runs':
            if raw['state'] not in ('prepared', 'completed', 'failed'):
                raise EnrollmentConflict('Resolve the original running or uncertain lab before changing courses')
            saved = decode_with(RUN_DECODERS, raw['module_id'], raw)
            if raw['module_id'] in ('foundations', 'extraction_engine') and saved['plan'].get('executor_id') != 'saved-text-extraction.1':
                raise CourseCatalogError('Unsupported original extraction executor')
        elif kind == 'decisions':
            check_decision(raw, package)
        elif kind == 'reviews':
            from .review_attempts import ReviewAttemptRepository
            from .review_result_integrity import validate_saved_review_result
            if raw['state'] not in ('prepared', 'evaluated', 'unavailable'):
                raise EnrollmentConflict('Resolve the original automatic review before changing courses')
            validate_saved_review_result(ReviewAttemptRepository.decode(raw), package_outcomes(package))
        elif kind == 'scenarios':
            from .scenario_history import ScenarioHistory, module_bank
            ScenarioHistory.receipt(raw, enrollment, module_bank(package, raw['module_id']))
        elif kind == 'processes':
            from .process_submissions import ProcessSubmissionRepository
            ProcessSubmissionRepository.decode(raw)
        elif kind == 'designs':
            from .workflow_design_submissions import WorkflowDesignSubmissionRepository
            WorkflowDesignSubmissionRepository.decode(raw)
        elif kind == 'completions':
            check_completion(raw, enrollment, package)
        elif kind == 'recoveries':
            check_recovery(raw, enrollment)

    @staticmethod
    def check_run_inputs(inventory):
        inputs = {row['uuid']: row for row in inventory['inputs']}
        for raw in inventory['runs']:
            from .lab_execution import LabExecutionRepository
            plan = LabExecutionRepository.decode(raw)['plan']
            original = inputs.get(plan['input_snapshot_id'])
            if (original is None or original['module_id'] != plan['module_id']
                    or original['record_sha256'] != plan['input_snapshot_sha256']):
                raise CourseCatalogError('The original lab run inputs are missing or changed')
