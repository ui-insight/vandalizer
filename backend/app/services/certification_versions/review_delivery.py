"""Read-only delivery of saved draft assessments; never dispatch or retry a judge."""
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .outcomes import package_outcomes
from .review_attempts import ReviewAttemptRepository


class SavedReviewUnavailable(ValueError):
    pass


class ReviewDelivery:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.reviews = ReviewAttemptRepository()

    async def course(self, user_id, enrollment_id, module_id=None):
        enrollment = await self.repository._enrollment(user_id, enrollment_id)
        package = self.repository.catalog.load(enrollment.course_version)
        contract = package_outcomes(package)
        if contract is None or (module_id is not None and not any(m.module_id == module_id for m in contract.modules)):
            raise SavedReviewUnavailable('Saved automatic assessments are unavailable for these course requirements')
        return enrollment, contract

    @staticmethod
    def public(saved, enrollment, contract):
        try:
            return ReviewDelivery._public(saved, enrollment, contract)
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, (CourseCatalogError, SavedReviewUnavailable)):
                raise
            raise CourseCatalogError('The saved assessment could not be displayed safely') from exc

    @staticmethod
    def _public(saved, enrollment, contract):
        record = saved['record']
        if (record['user_id'] != enrollment.user_id or record['enrollment_id'] != enrollment.uuid
                or record['course_version'] != enrollment.course_version or record['manifest_sha256'] != enrollment.manifest_sha256
                or record['contract'] != contract.model_dump(mode='json')):
            raise CourseCatalogError('The saved assessment does not match its original course requirements')
        process = record['submission_channel'] == 'trusted_saved_process_records' and record['module_id'] == 'process_mapping'
        workflow = record['submission_channel'] == 'trusted_saved_workflow_design_records' and record['module_id'] == 'workflow_design'
        connected = record['submission_channel'] == 'trusted_saved_connected_records' and record['module_id'] == 'multi_step'
        budget = record['submission_channel'] == 'trusted_saved_budget_records' and record['module_id'] == 'advanced_nodes'
        output = record['submission_channel'] == 'trusted_saved_output_records' and record['module_id'] == 'output_delivery'
        governance = record['submission_channel'] == 'trusted_saved_governance_records' and record['module_id'] == 'governance'
        batch = record['submission_channel'] == 'trusted_saved_batch_records' and record['module_id'] == 'batch_processing'
        validation = record['submission_channel'] == 'trusted_saved_validation_records' and record['module_id'] == 'validation_qa'
        if not process and not workflow and not connected and not budget and not output and not validation and not batch and not governance and record['submission_channel'] != 'trusted_saved_practical_records':
            raise SavedReviewUnavailable('This saved assessment has no verified practical record origin')
        module = next((m for m in contract.modules if m.module_id == record['module_id']), None)
        if module is None:
            raise CourseCatalogError('The saved assessment module is unavailable')
        from .review_result_integrity import validate_saved_review_result
        validate_saved_review_result(saved, contract)
        result = saved['result']
        assessment = result['assessment'] if result else None
        if assessment and any(assessment.get(key) is not False for key in ('credit_awarded', 'module_completion_eligible', 'staff_review_required')):
            raise CourseCatalogError('The saved assessment is not a supported draft result')
        status = assessment['status'] if assessment else saved['state']
        if status not in ('prepared', 'evaluating', 'requirements_supported', 'revision_required', 'grading_unavailable'):
            raise CourseCatalogError('The saved assessment status is unsupported')
        outcomes = []
        evidence = {item['id']: item for item in record['evidence']}
        decisions = {item['outcome_id']: item for item in assessment.get('outcomes', [])} if assessment else {}
        deterministic = {item['outcome_id']: item for item in assessment.get('deterministic_outcomes', [])} if assessment else {}
        for required in module.outcomes:
            decision, check = decisions.get(required.id), deterministic.get(required.id)
            if required.method == 'structured_review' and decision:
                outcomes.append({'outcome_id': required.id, 'statement': required.statement, 'method': required.method,
                                 'verdict': decision['verdict'], 'explanation': decision['explanation'],
                                 'revision_instruction': decision['revision_instruction'],
                                 'citations': [{'kind': evidence[item['evidence_id']]['kind'], 'quote': item['quote']}
                                               for item in decision['citations']]})
            elif required.method == 'deterministic' and check:
                outcomes.append({'outcome_id': required.id, 'statement': required.statement, 'method': required.method,
                                 'verdict': 'supported' if check['passed'] is True else 'contradicted' if check['passed'] is False else 'unclear',
                                 'explanation': check['explanation'], 'revision_instruction': check.get('revision_instruction', ''), 'citations': []})
            else:
                outcomes.append({'outcome_id': required.id, 'statement': required.statement, 'method': required.method,
                                 'verdict': 'not_assessed', 'explanation': 'No saved assessment result is available for this outcome.',
                                 'revision_instruction': '', 'citations': []})
        return {'attempt_id': saved['attempt_id'], 'enrollment_id': enrollment.uuid, 'course_version': enrollment.course_version,
                'manifest_sha256': enrollment.manifest_sha256, 'module_id': record['module_id'],
                'run_id': record['provenance']['corrected_run_id'] if connected else None if process or workflow else record['provenance']['run_id'], 'prepared_at': record['prepared_at'],
                **({'process_submission_id': record['provenance']['process_submission_id']} if process else {}),
                **({'workflow_design_submission_id': record['provenance']['workflow_design_submission_id']} if workflow else {}),
                **({'connected_review_submission_id': record['provenance']['connected_review_submission_id']} if connected else {}),
                **({'output_review_submission_id': record['provenance']['output_review_submission_id']} if output else {}),
                **({'governance_review_submission_id': record['provenance']['governance_review_submission_id']} if governance else {}),
                **({'batch_review_submission_id': record['provenance']['batch_review_submission_id']} if batch else {}),
                **({'validation_review_submission_id': record['provenance']['validation_review_submission_id']} if validation else {}),
                **({'budget_review_submission_id': record['provenance']['budget_review_submission_id']} if budget else {}),
                'finished_at': result.get('finished_at') if result else None,
                'parent_attempt_id': record.get('parent_attempt_id'), 'status': status, 'outcomes': outcomes,
                'assessment_kind': 'governance_capstone_review_draft' if governance else 'bounded_batch_review_draft' if batch else 'validation_suite_review_draft' if validation else 'output_workflow_review_draft' if output else 'budget_workflow_review_draft' if budget else 'connected_workflow_review_draft' if connected else 'workflow_design_review_draft' if workflow else 'process_design_review_draft' if process else 'practical_review_draft', 'credit_awarded': False,
                'module_completion_eligible': False, 'staff_review_required': False,
                'can_request_review': False, 'can_retry_review': False}

    async def get(self, user_id, enrollment_id, attempt_id):
        saved = await self.reviews.get(user_id, attempt_id)
        if saved is None:
            raise SavedReviewUnavailable('This saved assessment is unavailable')
        if saved['record']['enrollment_id'] != enrollment_id:
            raise EnrollmentConflict('Open the course that owns this saved assessment')
        enrollment, contract = await self.course(user_id, enrollment_id)
        return self.public(saved, enrollment, contract)

    async def list(self, user_id, enrollment_id, module_id):
        enrollment, contract = await self.course(user_id, enrollment_id, module_id)
        rows = await self.reviews.records.find({'user_id': user_id, 'enrollment_id': enrollment_id,
                                                'module_id': module_id}).sort('_id', -1).limit(51).to_list(51)
        attempts = []
        for row in rows[:50]:
            saved = self.reviews.decode(row)
            if saved['record']['submission_channel'] not in ('trusted_saved_practical_records', 'trusted_saved_process_records', 'trusted_saved_workflow_design_records', 'trusted_saved_connected_records', 'trusted_saved_budget_records', 'trusted_saved_output_records', 'trusted_saved_validation_records', 'trusted_saved_batch_records', 'trusted_saved_governance_records'):
                continue
            view = self.public(saved, enrollment, contract)
            summary = {key: view[key] for key in ('attempt_id', 'enrollment_id', 'module_id', 'run_id',
                                                       'prepared_at', 'finished_at', 'parent_attempt_id', 'status')}
            if 'process_submission_id' in view:
                summary['process_submission_id'] = view['process_submission_id']
            if 'workflow_design_submission_id' in view:
                summary['workflow_design_submission_id'] = view['workflow_design_submission_id']
            if 'connected_review_submission_id' in view:
                summary['connected_review_submission_id'] = view['connected_review_submission_id']
            for key in ('budget_review_submission_id', 'output_review_submission_id', 'validation_review_submission_id', 'batch_review_submission_id', 'governance_review_submission_id'):
                if key in view:
                    summary[key] = view[key]
            attempts.append(summary)
        return {'enrollment_id': enrollment_id, 'module_id': module_id, 'attempts': attempts,
                'older_attempts_available': len(rows) > 50}
