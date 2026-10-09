"""Read an explicit set of saved draft assessments against every module outcome.

This is a preparation step for the new rubric, not its credit runner. No latest
or best attempt is inferred, no judge is dispatched, and no progress is written.
Only original, integrity-checked, owned receipts are eligible for this preview.
"""
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .outcomes import package_outcomes
from .review_attempts import ReviewAttemptRepository
from .review_delivery import ReviewDelivery, SavedReviewUnavailable
from .scenario_history import ScenarioHistory
from .scenario_submissions import ScenarioSubmissionRepository, module_bank


class ModuleReadiness:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()

    async def preview(self, user_id, enrollment_id, module_id, *, review_attempt_id=None,
                      scenario_attempt_id=None):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        if package.manifest_sha256 != enrollment.manifest_sha256:
            raise CourseCatalogError('The selected course no longer matches its enrollment')
        contract = package_outcomes(package)
        module = next((item for item in contract.modules if item.module_id == module_id), None) if contract else None
        if module is None:
            raise EnrollmentConflict('This course has no competency outcomes for that module')
        methods = {item.method for item in module.outcomes}
        if review_attempt_id is not None and not methods - {'scenario_choice'}:
            raise EnrollmentConflict('This module requires scenario answers, not a practical review')
        if scenario_attempt_id is not None and 'scenario_choice' not in methods:
            raise EnrollmentConflict('This module does not require a scenario assessment')
        for attempt_id in (review_attempt_id, scenario_attempt_id):
            if attempt_id is not None and (not isinstance(attempt_id, str) or not attempt_id.strip()):
                raise EnrollmentConflict('Select a saved assessment by its exact identity')

        review, scenario, receipts = None, None, []
        if review_attempt_id is not None:
            saved = await ReviewAttemptRepository().get(user_id, review_attempt_id)
            if saved is None:
                raise SavedReviewUnavailable('The selected saved assessment is unavailable')
            if saved['record']['module_id'] != module_id:
                raise EnrollmentConflict('The selected assessment belongs to another module')
            review = ReviewDelivery.public(saved, enrollment, contract)
            receipts.append({'kind': 'automatic_review', 'attempt_id': review_attempt_id,
                             'record_sha256': saved['record_sha256'],
                             'result_sha256': encode(saved['result'])[1] if saved['result'] else None})
        if scenario_attempt_id is not None:
            raw = await ScenarioSubmissionRepository().records.find_one({
                'uuid': scenario_attempt_id, 'user_id': user_id,
                'enrollment_id': enrollment_id, 'module_id': module_id})
            if raw is None:
                raise SavedReviewUnavailable('The selected scenario assessment is unavailable')
            scenario = ScenarioHistory.receipt(raw, enrollment, module_bank(package, module_id))
            receipts.append({'kind': 'scenario_recognition', 'attempt_id': scenario_attempt_id,
                             'record_sha256': raw['record_sha256'],
                             'result_sha256': encode(scenario['result'])[1]})

        reviewed = {item['outcome_id']: item for item in review['outcomes']} if review else {}
        recognized = {item['outcome_id']: item for item in scenario['result']['outcomes']} if scenario else {}
        outcomes = []
        for required in module.outcomes:
            if required.method == 'scenario_choice':
                result = recognized.get(required.id)
                state = 'selection_required' if result is None else 'supported' if result['passed'] else 'revision_required'
                selected = scenario_attempt_id
            elif review is None:
                state, selected = 'selection_required', None
            else:
                selected = review_attempt_id
                if review['status'] in ('prepared', 'evaluating'):
                    state = 'assessment_pending'
                elif review['status'] == 'grading_unavailable':
                    state = 'grading_unavailable'
                else:
                    result = reviewed.get(required.id)
                    # Missing/unclear evidence never becomes a successful outcome.
                    state = 'supported' if result and result['verdict'] == 'supported' else 'revision_required'
            outcomes.append({'outcome_id': required.id, 'statement': required.statement,
                             'method': required.method, 'state': state, 'attempt_id': selected})
        states = {item['state'] for item in outcomes}
        # Return every outcome so a technical failure cannot hide a separate
        # failed scenario, and a passed scenario cannot hide unfinished review.
        status = next((state for state in ('revision_required', 'grading_unavailable',
                      'assessment_pending', 'selection_required') if state in states), 'requirements_supported')
        return {'enrollment_id': enrollment_id, 'course_version': enrollment.course_version,
                'manifest_sha256': enrollment.manifest_sha256, 'module_id': module_id,
                'contract_sha256': encode(contract.model_dump(mode='json'))[1],
                'rubric_id': contract.rubric_id, 'assessment_kind': 'module_readiness_draft',
                'status': status, 'all_required_outcomes_supported': states == {'supported'},
                'outcomes': outcomes, 'selected_receipts': receipts, 'read_only': True,
                'credit_awarded': False, 'module_completion_eligible': False,
                'staff_review_required': False}
