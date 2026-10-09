"""Persist automatic-review requests and results without grading twice.

Internal staged caller only: evidence must already be authenticated and verified
by its producer. No client evidence endpoint, earned credit or staff queue exists.
"""
import asyncio
from copy import deepcopy
import datetime
import hashlib
import json
import re

from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationReviewAttempt
from .attempts import encode
from .automatic_review import AutomaticReviewPolicy, evaluate_draft_structured_review, review_packet, reviewer_identity
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .lab_execution import LabExecutionRepository
from .lab_inputs import LabInputRepository
from .outcomes import OutcomeContract, package_outcomes


class ReviewAlreadyExists(EnrollmentConflict):
    def __init__(self, attempt_id):
        super().__init__('This saved work already has an assessment request. Check its original saved assessment')
        self.detail = {'code': 'CERTIFICATION_REVIEW_EXISTS', 'message': str(self), 'attempt_id': attempt_id}


def evidence_request_digest(record):
    """Identify one trusted evidence packet independently of a tab's request ID."""
    return encode({key: record.get(key) for key in (
        'user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
        'evidence', 'provenance', 'parent_attempt_id', 'contract', 'policy', 'reviewer',
        'submission_channel')})[1]


class ReviewAttemptRepository:
    @property
    def records(self):
        return CertificationReviewAttempt.get_motor_collection()

    @staticmethod
    def decode(raw):
        try:
            if hashlib.sha256(raw['record_json'].encode()).hexdigest() != raw['record_sha256']:
                raise ValueError('Request digest mismatch')
            record = json.loads(raw['record_json'])
            if any(record[key] != raw[key] for key in ('uuid', 'user_id', 'enrollment_id', 'module_id',
                    'course_version', 'manifest_sha256', 'request_sha256')):
                raise ValueError('Request identity mismatch')
            if record.get('parent_attempt_id') != raw.get('parent_attempt_id'):
                raise ValueError('Retry lineage mismatch')
            if (raw.get('evidence_request_sha256') is not None
                    and raw['evidence_request_sha256'] != evidence_request_digest(record)):
                raise ValueError('Evidence request identity mismatch')
            result = None
            if raw['state'] in ('evaluated', 'unavailable'):
                if hashlib.sha256(raw['result_json'].encode()).hexdigest() != raw['result_sha256']:
                    raise ValueError('Result digest mismatch')
                result = json.loads(raw['result_json'])
                expected_state = 'unavailable' if result['assessment']['status'] == 'grading_unavailable' else 'evaluated'
                if (result['attempt_id'] != raw['uuid'] or result['record_sha256'] != raw['record_sha256']
                        or raw['state'] != expected_state):
                    raise ValueError('Result identity mismatch')
            elif raw['state'] not in ('prepared', 'evaluating') or raw.get('result_json') is not None:
                raise ValueError('Unexpected state')
            return {'attempt_id': raw['uuid'], 'state': raw['state'], 'record': record,
                    'record_sha256': raw['record_sha256'], 'result': result}
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The saved automatic review failed integrity verification') from exc

    async def get(self, user_id, attempt_id):
        raw = await self.records.find_one({'uuid': attempt_id, 'user_id': user_id})
        return self.decode(raw) if raw else None

    async def prepare_from_run(self, operation, run_id, request_id, *, actor_user_id, model_name, system_config):
        """Prepare from saved records only; callers cannot supply grading text.

        An identical request keeps its original collected evidence even if the
        learner saves a later value review. Revised work needs a new request.
        """
        from .practical_evidence import PracticalEvidenceRepository, EvidenceAssemblyUnavailable
        if actor_user_id != operation.user_id or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Automatic review requires the authenticated learner and a request identity')
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            saved = self.decode(existing)
            record = saved['record']
            LabExecutionRepository.check_operation(operation, record)
            if (record['submission_channel'] != 'trusted_saved_practical_records'
                    or record.get('parent_attempt_id') is not None or record['module_id'] not in ('foundations', 'extraction_engine')
                    or record.get('provenance', {}).get('run_id') != run_id
                    or record['reviewer']['model_name'] != model_name):
                raise EnrollmentConflict('This review request already belongs to different saved work')
            return saved
        run = await LabExecutionRepository().get(actor_user_id, run_id)
        if run is None:
            raise EnrollmentConflict('Select an owned practical run before requesting assessment')
        if run['plan']['module_id'] == 'foundations':
            packet = await PracticalEvidenceRepository().assemble_foundations(operation, run_id, actor_user_id=actor_user_id)
        elif run['plan']['module_id'] == 'extraction_engine':
            from .extraction_evidence import assemble_extraction
            packet = await assemble_extraction(operation, run_id, actor_user_id=actor_user_id)
        else:
            raise EnrollmentConflict('This practical module has no trusted evidence collector')
        if not packet['collection_complete']:
            raise EvidenceAssemblyUnavailable('Complete the saved proposal and value review before requesting assessment; no grade was recorded')
        return await self.prepare(operation, packet['module_id'], packet['evidence'], request_id,
            actor_user_id=actor_user_id, model_name=model_name, system_config=system_config,
            _provenance=packet['provenance'])

    async def prepare_from_process(self, operation, submission_id, request_id, *, actor_user_id, model_name, system_config):
        from .process_evidence import assemble_process
        if actor_user_id != operation.user_id or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Process review requires the authenticated learner and a request identity')
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            saved = self.decode(existing)
            record = saved['record']
            LabExecutionRepository.check_operation(operation, record)
            if (record['submission_channel'] != 'trusted_saved_process_records'
                    or record.get('parent_attempt_id') is not None or record['module_id'] != 'process_mapping'
                    or record.get('provenance', {}).get('process_submission_id') != submission_id
                    or record['reviewer']['model_name'] != model_name):
                raise EnrollmentConflict('This assessment request belongs to a different saved process design')
            return saved
        packet = await assemble_process(operation, submission_id, actor_user_id=actor_user_id)
        return await self.prepare(operation, packet['module_id'], packet['evidence'], request_id,
            actor_user_id=actor_user_id, model_name=model_name, system_config=system_config,
            _provenance=packet['provenance'])

    async def prepare_from_workflow_design(self, operation, submission_id, request_id, *, actor_user_id, model_name, system_config):
        from .workflow_design_evidence import assemble_workflow_design
        if actor_user_id != operation.user_id or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Workflow Design review requires the authenticated learner and a request identity')
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            saved = self.decode(existing)
            record = saved['record']
            LabExecutionRepository.check_operation(operation, record)
            if (record['submission_channel'] != 'trusted_saved_workflow_design_records'
                    or record.get('parent_attempt_id') is not None or record['module_id'] != 'workflow_design'
                    or record.get('provenance', {}).get('workflow_design_submission_id') != submission_id
                    or record['reviewer']['model_name'] != model_name):
                raise EnrollmentConflict('This assessment request belongs to a different saved workflow approval')
            return saved
        packet = await assemble_workflow_design(operation, submission_id, actor_user_id=actor_user_id)
        return await self.prepare(operation, packet['module_id'], packet['evidence'], request_id,
            actor_user_id=actor_user_id, model_name=model_name, system_config=system_config,
            _provenance=packet['provenance'])

    async def prepare_from_connected_review(self, operation, submission_id, request_id, *, actor_user_id, model_name, system_config):
        from .connected_workflow_evidence import assemble_connected_review
        if actor_user_id != operation.user_id or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Connected review requires the authenticated learner and a request identity')
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            saved = self.decode(existing)
            record = saved['record']
            LabExecutionRepository.check_operation(operation, record)
            if (record['submission_channel'] != 'trusted_saved_connected_records'
                    or record.get('parent_attempt_id') is not None or record['module_id'] != 'multi_step'
                    or record.get('provenance', {}).get('connected_review_submission_id') != submission_id
                    or record['reviewer']['model_name'] != model_name):
                raise EnrollmentConflict('This assessment request belongs to a different saved connected comparison')
            return saved
        packet = await assemble_connected_review(operation, submission_id, actor_user_id=actor_user_id)
        return await self.prepare(operation, packet['module_id'], packet['evidence'], request_id,
            actor_user_id=actor_user_id, model_name=model_name, system_config=system_config,
            _provenance=packet['provenance'])

    async def prepare_from_budget_review(self, operation, submission_id, request_id, *, actor_user_id, model_name, system_config):
        from .advanced_workflow_evidence import assemble_budget_review
        if actor_user_id != operation.user_id or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Budget review requires the authenticated learner and a request identity')
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            saved = self.decode(existing)
            record = saved['record']
            LabExecutionRepository.check_operation(operation, record)
            if (record['submission_channel'] != 'trusted_saved_budget_records'
                    or record.get('parent_attempt_id') is not None or record['module_id'] != 'advanced_nodes'
                    or record.get('provenance', {}).get('budget_review_submission_id') != submission_id
                    or record['reviewer']['model_name'] != model_name):
                raise EnrollmentConflict('This assessment request belongs to a different saved budget review')
            return saved
        packet = await assemble_budget_review(operation, submission_id, actor_user_id=actor_user_id)
        return await self.prepare(operation, packet['module_id'], packet['evidence'], request_id,
            actor_user_id=actor_user_id, model_name=model_name, system_config=system_config,
            _provenance=packet['provenance'])

    async def prepare_from_output_review(self, operation, submission_id, request_id, *, actor_user_id, model_name, system_config):
        from .output_workflow_evidence import assemble_output_review
        if actor_user_id != operation.user_id or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Output review requires the authenticated learner and a request identity')
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            saved = self.decode(existing)
            record = saved['record']
            LabExecutionRepository.check_operation(operation, record)
            if (record['submission_channel'] != 'trusted_saved_output_records'
                    or record.get('parent_attempt_id') is not None or record['module_id'] != 'output_delivery'
                    or record.get('provenance', {}).get('output_review_submission_id') != submission_id
                    or record['reviewer']['model_name'] != model_name):
                raise EnrollmentConflict('This assessment request belongs to a different saved output review')
            return saved
        packet = await assemble_output_review(operation, submission_id, actor_user_id=actor_user_id)
        return await self.prepare(operation, packet['module_id'], packet['evidence'], request_id,
            actor_user_id=actor_user_id, model_name=model_name, system_config=system_config,
            _provenance=packet['provenance'])

    async def prepare_from_validation_review(self, operation, submission_id, request_id, *, actor_user_id, model_name, system_config):
        from .validation_evidence import assemble_validation_review
        if actor_user_id != operation.user_id or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Validation review requires the authenticated learner and a request identity')
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            saved = self.decode(existing)
            record = saved['record']
            LabExecutionRepository.check_operation(operation, record)
            if (record['submission_channel'] != 'trusted_saved_validation_records'
                    or record.get('parent_attempt_id') is not None or record['module_id'] != 'validation_qa'
                    or record.get('provenance', {}).get('validation_review_submission_id') != submission_id
                    or record['reviewer']['model_name'] != model_name):
                raise EnrollmentConflict('This assessment request belongs to a different saved validation review')
            return saved
        packet = await assemble_validation_review(operation, submission_id, actor_user_id=actor_user_id)
        return await self.prepare(operation, packet['module_id'], packet['evidence'], request_id,
            actor_user_id=actor_user_id, model_name=model_name, system_config=system_config,
            _provenance=packet['provenance'])

    async def prepare_from_batch_review(self, operation, submission_id, request_id, *, actor_user_id, model_name, system_config):
        from .batch_evidence import assemble_batch_review
        if actor_user_id != operation.user_id or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Batch review requires the authenticated learner and a request identity')
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            saved = self.decode(existing)
            record = saved['record']
            LabExecutionRepository.check_operation(operation, record)
            if (record['submission_channel'] != 'trusted_saved_batch_records'
                    or record.get('parent_attempt_id') is not None or record['module_id'] != 'batch_processing'
                    or record.get('provenance', {}).get('batch_review_submission_id') != submission_id
                    or record['reviewer']['model_name'] != model_name):
                raise EnrollmentConflict('This assessment request belongs to a different saved batch review')
            return saved
        packet = await assemble_batch_review(operation, submission_id, actor_user_id=actor_user_id)
        return await self.prepare(operation, packet['module_id'], packet['evidence'], request_id,
            actor_user_id=actor_user_id, model_name=model_name, system_config=system_config,
            _provenance=packet['provenance'])

    async def prepare_from_governance_review(self, operation, submission_id, request_id, *, actor_user_id, model_name, system_config):
        from .governance_evidence import assemble_governance_review
        if actor_user_id != operation.user_id or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Governance review requires the authenticated learner and a request identity')
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            saved = self.decode(existing)
            record = saved['record']
            LabExecutionRepository.check_operation(operation, record)
            if (record['submission_channel'] != 'trusted_saved_governance_records'
                    or record.get('parent_attempt_id') is not None or record['module_id'] != 'governance'
                    or record.get('provenance', {}).get('governance_review_submission_id') != submission_id
                    or record['reviewer']['model_name'] != model_name):
                raise EnrollmentConflict('This assessment request belongs to a different saved Governance review')
            return saved
        packet = await assemble_governance_review(operation, submission_id, actor_user_id=actor_user_id)
        return await self.prepare(operation, packet['module_id'], packet['evidence'], request_id,
            actor_user_id=actor_user_id, model_name=model_name, system_config=system_config,
            _provenance=packet['provenance'])

    async def prepare_retry(self, operation, parent_attempt_id, request_id, *, actor_user_id, system_config):
        """Start one explicit technical retry using the original saved evidence.

        Replaying either request returns its own receipt. A failed child can be
        retried in turn; callers cannot fan out retries from the same failure.
        """
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Automatic review requires the authenticated learner')
        parent = await self.get(actor_user_id, parent_attempt_id)
        if parent is None or parent['state'] != 'unavailable':
            raise EnrollmentConflict('Only a saved technical grading failure can be retried')
        record = parent['record']
        LabExecutionRepository.check_operation(operation, record)
        contract = package_outcomes(operation.package)
        if contract is None or contract.model_dump(mode='json') != record['contract']:
            raise EnrollmentConflict('A technical retry must preserve the original assessment requirements')
        return await self.prepare(operation, record['module_id'], record['evidence'], request_id,
            actor_user_id=actor_user_id, model_name=record['reviewer']['model_name'],
            system_config=system_config, _parent_attempt_id=parent_attempt_id, _provenance=record.get('provenance'))

    async def prepare(self, operation, module_id, evidence, request_id, *, actor_user_id, model_name, system_config,
                      _parent_attempt_id=None, _provenance=None):
        if actor_user_id != operation.user_id or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Automatic review requires the authenticated learner and a request identity')
        if not isinstance(model_name, str) or not model_name.strip() or len(model_name) > 200:
            raise EnrollmentConflict('Select an explicit assessment model before preparing a review')
        package = operation.package
        identity = {'uuid': request_id, 'user_id': actor_user_id, 'enrollment_id': operation.progress.enrollment_id,
                    'module_id': module_id, 'course_version': package.manifest.release_id,
                    'manifest_sha256': package.manifest_sha256}
        lease = LabExecutionRepository.check_operation(operation, identity)
        contract = package_outcomes(package)
        if contract is None:
            raise EnrollmentConflict('Automatic review requires a packaged outcome contract')
        _, checked, _ = review_packet(contract, module_id, evidence)
        payload = [item.model_dump(mode='json') for item in checked]
        provenance = {'provenance': deepcopy(_provenance)} if _provenance is not None else {}
        request_digest = encode({**identity, 'model_name': model_name, 'evidence': payload,
                                 **provenance,
                                 'parent_attempt_id': _parent_attempt_id})[1]
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            if existing['request_sha256'] != request_digest:
                raise EnrollmentConflict('This review request already belongs to different evidence or another learner')
            return self.decode(existing)
        if _parent_attempt_id is not None:
            parent = await self.get(actor_user_id, _parent_attempt_id)
            if (parent is None or parent['state'] != 'unavailable'
                    or any(parent['record'][key] != value for key, value in identity.items() if key != 'uuid')
                    or parent['record']['evidence'] != payload
                    or parent['record'].get('provenance') != _provenance
                    or parent['record']['reviewer']['model_name'] != model_name
                    or parent['record']['contract'] != contract.model_dump(mode='json')
                    or parent['record']['policy'] != AutomaticReviewPolicy().model_dump(mode='json')):
                raise EnrollmentConflict('A technical retry must preserve the original evidence and requirements')
        record = {**identity, 'request_sha256': request_digest, 'evidence': payload,
                  **provenance,
                  'parent_attempt_id': _parent_attempt_id,
                  'contract': contract.model_dump(mode='json'),
                  'policy': AutomaticReviewPolicy().model_dump(mode='json'),
                  'reviewer': reviewer_identity(model_name, deepcopy(system_config)),
                  'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'submission_channel': ('trusted_saved_governance_records' if _provenance and _provenance.get('record_kind') == 'saved_governance_result_review'
                      else 'trusted_saved_batch_records' if _provenance and _provenance.get('record_kind') == 'saved_batch_result_review'
                      else 'trusted_saved_validation_records' if _provenance and _provenance.get('record_kind') == 'saved_validation_result_review'
                      else 'trusted_saved_output_records' if _provenance and _provenance.get('record_kind') == 'saved_output_result_review'
                      else 'trusted_saved_budget_records' if _provenance and _provenance.get('record_kind') == 'saved_budget_result_review'
                      else 'trusted_saved_connected_records' if _provenance and _provenance.get('record_kind') == 'saved_connected_result_review'
                      else 'trusted_saved_workflow_design_records' if _provenance and _provenance.get('record_kind') == 'approved_workflow_design'
                      else 'trusted_saved_process_records' if _provenance and _provenance.get('record_kind') == 'saved_process_design'
                      else 'trusted_saved_practical_records' if _provenance is not None else 'internal_authenticated_evidence_producer')}
        evidence_digest = evidence_request_digest(record) if _provenance is not None else None
        if evidence_digest is not None:
            await self.reject_duplicate_evidence(record, evidence_digest)
        serialized, digest = encode(record)
        await LabInputRepository._check_lease(lease)
        try:
            await self.records.insert_one({**identity, 'request_sha256': request_digest,
                                           **({'evidence_request_sha256': evidence_digest} if evidence_digest else {}),
                                           'parent_attempt_id': _parent_attempt_id,
                                           'record_json': serialized, 'record_sha256': digest, 'state': 'prepared'})
        except DuplicateKeyError:
            existing = await self.records.find_one({'uuid': request_id})
            if existing is None or existing['request_sha256'] != request_digest:
                if existing is None and evidence_digest is not None:
                    await self.reject_duplicate_evidence(record, evidence_digest)
                raise EnrollmentConflict('This review request identity or technical retry was already claimed')
        return await self.get(actor_user_id, request_id)

    async def reject_duplicate_evidence(self, record, digest):
        scope = {key: record[key] for key in ('user_id', 'enrollment_id', 'module_id',
                                             'course_version', 'manifest_sha256')}
        # New records have an atomic unique key. Historical receipts are read
        # and verified without rewriting their immutable inputs or results.
        candidates = self.records.find({**scope, '$or': [
            {'evidence_request_sha256': digest}, {'evidence_request_sha256': None},
        ]}).sort('_id', 1)
        async for raw in candidates:
            saved = self.decode(raw)
            if saved['attempt_id'] != record['uuid'] and evidence_request_digest(saved['record']) == digest:
                raise ReviewAlreadyExists(saved['attempt_id'])

    async def evaluate(self, operation, attempt_id, system_config, *, call_model=None):
        from .review_recovery import bind_review_worker
        saved = await self.get(operation.user_id, attempt_id)
        if saved is None:
            raise EnrollmentConflict('Prepare the assessment evidence before reviewing it')
        record = saved['record']
        lease = LabExecutionRepository.check_operation(operation, record)
        if saved['state'] != 'prepared':
            # A receipt saved before a lost response always wins. An evaluating
            # intent is never reset by elapsed time or a duplicate request.
            return saved
        config = deepcopy(system_config)
        if (reviewer_identity(record['reviewer']['model_name'], config) != record['reviewer']
                or AutomaticReviewPolicy().model_dump(mode='json') != record['policy']):
            raise EnrollmentConflict('The assessment model, policy or implementation changed; prepare a new review')
        contract = OutcomeContract.model_validate(record['contract'])
        await LabInputRepository._check_lease(lease)
        timing = await bind_review_worker(saved, lease)
        claimed = await self.records.update_one(
            {'uuid': attempt_id, 'state': 'prepared', 'record_sha256': saved['record_sha256']},
            {'$set': {'state': 'evaluating', 'worker_id': lease.write_id, **timing}},
        )
        if claimed.modified_count != 1:
            return await self.get(operation.user_id, attempt_id)
        started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            result = await evaluate_draft_structured_review(contract, record['module_id'], record['evidence'],
                model_name=record['reviewer']['model_name'], system_config=config, call_model=call_model)
        except asyncio.CancelledError:
            await asyncio.shield(self._finish(saved, lease, self._unavailable('caller_cancelled'), started_at))
            raise
        except Exception:
            result = self._unavailable('reviewer_execution_error')
        await self._finish(saved, lease, result, started_at)
        return await self.get(operation.user_id, attempt_id)

    async def evaluate_saved(self, repository, user_id, enrollment_id, attempt_id, system_config, *, call_model=None):
        """Self-service orchestration; reconcile expired work before dispatch.

        Recovery never creates a retry or repeats a model call. A technical retry
        remains a new explicitly linked request through prepare_retry.
        """
        from .review_recovery import ReviewRecovery
        from .runtime import CourseOperation
        saved = await ReviewRecovery(repository).reconcile(user_id, enrollment_id, attempt_id)
        if saved['state'] != 'prepared':
            return saved
        async with repository.write_boundary(user_id, enrollment_id, operation='evaluate_automatic_review',
                                              review_attempt_id=attempt_id) as progress:
            package = repository.catalog.load(progress.course_version)
            return await self.evaluate(CourseOperation(user_id, package, progress, True), attempt_id,
                                       system_config, call_model=call_model)

    @staticmethod
    def _unavailable(reason):
        return {'status': 'grading_unavailable', 'passed': None, 'retryable': True, 'reason': reason,
                'credit_awarded': False, 'module_completion_eligible': False, 'staff_review_required': False}

    @staticmethod
    def with_saved_checks(saved, assessment):
        supporting = saved['record'].get('provenance', {}).get('supporting_checks')
        if supporting is not None:
            assessment = {**assessment, 'supporting_checks': deepcopy(supporting),
                          'model_outcomes': deepcopy(assessment.get('outcomes', []))}
            # A source/arithmetic veto never upgrades model uncertainty and
            # never turns a technical model failure into learner failure.
            if assessment.get('status') in ('requirements_supported', 'revision_required'):
                failed = {item['outcome_id']: item for item in supporting if item['passed'] is not True}
                evidence = {item['id']: item for item in saved['record']['evidence']}
                decisions = []
                for decision in assessment.get('outcomes', []):
                    check = failed.get(decision['outcome_id'])
                    if check:
                        if check['evidence_id'] not in evidence or check['quote'] not in evidence[check['evidence_id']]['text']:
                            raise CourseCatalogError('The saved arithmetic check does not cite its original evidence')
                        decision = {**decision, 'verdict': 'contradicted', 'explanation': check['explanation'],
                                    'revision_instruction': check['revision_instruction'],
                                    'citations': [{'evidence_id': check['evidence_id'], 'quote': check['quote']}]}
                    decisions.append(decision)
                assessment = {**assessment, 'outcomes': decisions}
                if failed:
                    assessment = {**assessment, 'passed': False, 'status': 'revision_required'}
        deterministic = saved['record'].get('provenance', {}).get('deterministic_outcomes')
        if deterministic is not None:
            assessment = {**assessment, 'assessment_kind': 'practical_review_draft',
                          'deterministic_outcomes': deepcopy(deterministic),
                          'assessed_outcome_ids': [*assessment.get('assessed_outcome_ids', []),
                                                  *(item['outcome_id'] for item in deterministic)]}
            if assessment.get('passed') is True and any(item['passed'] is not True for item in deterministic):
                assessment = {**assessment, 'passed': False, 'status': 'revision_required'}
        return assessment

    async def _finish(self, saved, lease, assessment, started_at):
        assessment = self.with_saved_checks(saved, assessment)
        result = {'attempt_id': saved['attempt_id'], 'record_sha256': saved['record_sha256'],
                  'assessment': assessment, 'started_at': started_at,
                  'finished_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(result)
        state = 'unavailable' if assessment['status'] == 'grading_unavailable' else 'evaluated'
        updated = await self.records.update_one(
            {'uuid': saved['attempt_id'], 'record_sha256': saved['record_sha256'], 'state': 'evaluating', 'worker_id': lease.write_id},
            {'$set': {'state': state, 'result_json': serialized, 'result_sha256': digest}},
        )
        if updated.modified_count != 1:
            raise EnrollmentConflict('The saved review changed; inspect the original assessment before retrying')
