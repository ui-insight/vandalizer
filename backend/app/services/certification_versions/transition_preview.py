"""Read-only transition planning; never initializes, migrates or awards credit.

Until assessed-outcome equivalence and external-job reconciliation exist, this
is an internal preparation view, not a learner activation API. Draft target
requirements may be inspected without making that draft enrollable.
"""
from copy import deepcopy

from bson import ObjectId, json_util

from app.models.certification import CertificationAttempt, CertificationLabInput, CertificationScenarioAttempt, CertificationLabExecution, CertificationReviewAttempt, CertificationLearnerDecision, CertificationProcessSubmission, CertificationWorkflowDesignSubmission, CertificationRecoveryRecord
from .attempts import encode
from .credentials import CredentialRepository
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .outcomes import package_outcomes
from .credit_equivalence import equivalence_plan


EXECUTION_SUMMARY_FIELDS = {'uuid': 1, 'module_id': 1, 'input_snapshot_id': 1, 'state': 1,
                            'plan_sha256': 1, 'result_sha256': 1, 'worker_id': 1,
                            'scope_decision_id': 1, 'scope_decision_sha256': 1, 'authorization_sha256': 1,
                            'stage_events_sha256': 1, 'stage_event_count': 1}


COMPLETION_SUMMARY_FIELDS = {'uuid': 1, 'module_id': 1, 'state': 1, 'progress_sha256': 1,
                             'validation_sha256': 1, 'result_sha256': 1, 'assessment_selection_sha256': 1,
                             'course_version': 1, 'manifest_sha256': 1, 'rubric_id': 1, 'artifact_sha256': 1}
RECOVERY_SUMMARY_FIELDS = {'uuid': 1, 'state': 1, 'request_sha256': 1, 'review_sha256': 1, 'result_sha256': 1}


REVIEW_SUMMARY_FIELDS = {'uuid': 1, 'module_id': 1, 'state': 1, 'record_sha256': 1,
                         'result_sha256': 1, 'worker_id': 1}

def fingerprint(value):
    # Canonical BSON encoding retains ObjectIds/dates and the write fence.
    return encode({'bson': json_util.dumps(value, sort_keys=True)})[1]


def without_owned_write(selection, progress, user_id, enrollment_id):
    """Remove only this caller's verified guard when comparing reviewed work."""
    from .writes import require_lease
    lease = require_lease(user_id, enrollment_id)
    marker = (selection or {}).get('active_write') or {}
    if (not selection or selection.get('active_enrollment_id') != enrollment_id
            or selection.get('in_flight_writes') != 1 or marker.get('id') != lease.write_id
            or marker.get('enrollment_id') != enrollment_id or 'previous_fence' not in marker
            or not progress or str(progress['_id']) != lease.progress_id
            or progress.get('_certification_write_fence') != lease.write_id):
        raise EnrollmentConflict('This operation no longer owns the reviewed course boundary')
    selection, progress = deepcopy(selection), deepcopy(progress)
    selection['in_flight_writes'] = 0
    selection.pop('active_write', None)
    if marker['previous_fence'] is None:
        progress.pop('_certification_write_fence', None)
    else:
        progress['_certification_write_fence'] = marker['previous_fence']
    return selection, progress


def decision_basis(state, source, target, credential):
    """Guard rotation alone is not changed work; actual data/revisions are."""
    state = deepcopy(state)
    state['selection'].pop('active_write', None)
    state['progress'].pop('_certification_write_fence', None)
    return fingerprint({'state': state, 'source_enrollment': source.model_dump(mode='json'),
                        'target_version': target.manifest.release_id, 'target_manifest': target.manifest_sha256,
                        'credential': credential.model_dump(mode='json') if credential else None})


class TransitionPreview:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()

    async def inspect(self, user_id: str, source_id: str, target_version: str, *, _held_write=False):
        repo = self.repository
        selection = await repo.selections.find_one({'user_id': user_id})
        if not selection or selection['active_enrollment_id'] != source_id:
            raise EnrollmentConflict('Review the currently selected course before planning an upgrade')
        source = await repo._enrollment(user_id, source_id)
        if target_version == source.course_version:
            raise EnrollmentConflict('The upgrade must target a different course')
        target = repo.catalog.load(target_version, preview=True)
        contract = package_outcomes(target)
        if contract is None:
            raise EnrollmentConflict('The target course needs an explicit outcome contract before credit can be previewed')
        query = {'_id': ObjectId(source.progress_id), 'user_id': user_id}
        raw_progress = await repo.progress.find_one(query)
        progress = await repo.read_progress(user_id, source_id)
        if _held_write:
            selection, raw_progress = without_owned_write(selection, raw_progress, user_id, source_id)
        pending_query = {'user_id': user_id, 'enrollment_id': source_id, 'state': {'$in': ['evaluating', 'graded']}}
        attempts = await CertificationAttempt.get_motor_collection().find(pending_query).to_list(None)
        lab_query = {'user_id': user_id, 'enrollment_id': source_id}
        completion_history = await CertificationAttempt.get_motor_collection().find(lab_query, COMPLETION_SUMMARY_FIELDS).sort('uuid', 1).to_list(None)
        recoveries = await CertificationRecoveryRecord.get_motor_collection().find(lab_query, RECOVERY_SUMMARY_FIELDS).sort('uuid', 1).to_list(None)
        labs = await CertificationLabInput.get_motor_collection().find(lab_query, {'uuid': 1, 'module_id': 1, 'record_sha256': 1}).sort('uuid', 1).to_list(None)
        scenarios = await CertificationScenarioAttempt.get_motor_collection().find(lab_query, {'uuid': 1, 'module_id': 1, 'record_sha256': 1}).sort('uuid', 1).to_list(None)
        executions = await CertificationLabExecution.get_motor_collection().find(lab_query, EXECUTION_SUMMARY_FIELDS).sort('uuid', 1).to_list(None)
        reviews = await CertificationReviewAttempt.get_motor_collection().find(lab_query, REVIEW_SUMMARY_FIELDS).sort('uuid', 1).to_list(None)
        decisions = await CertificationLearnerDecision.get_motor_collection().find(lab_query, {'uuid': 1, 'module_id': 1, 'record_sha256': 1}).sort('uuid', 1).to_list(None)
        processes = await CertificationProcessSubmission.get_motor_collection().find(lab_query, {'uuid': 1, 'module_id': 1, 'record_sha256': 1}).sort('uuid', 1).to_list(None)
        designs = await CertificationWorkflowDesignSubmission.get_motor_collection().find(lab_query, {'uuid': 1, 'module_id': 1, 'record_sha256': 1}).sort('uuid', 1).to_list(None)
        credential = await CredentialRepository().for_enrollment(user_id, source_id)
        blockers = [{'code': 'transition_not_enabled', 'message': 'Upgrade activation is not enabled. Your current course remains selected.'},
                    {'code': 'equivalence_not_verified', 'message': 'No assessed-outcome credit transfer has been verified for this course pair.'},
                    {'code': 'external_jobs_not_reconciled', 'message': 'Lab and external-job reconciliation must be implemented before activation.'}]
        if target.entry.state != 'published':
            blockers.append({'code': 'target_not_published', 'message': 'The target is a draft or retired course and cannot accept this enrollment.'})
        if selection.get('in_flight_writes'):
            blockers.append({'code': 'write_in_flight', 'message': 'A course operation is in flight; reconcile it before changing courses.'})
        if attempts:
            blockers.append({'code': 'pending_assessment', 'message': 'Resolve the saved assessment before changing courses.'})
        if any(item['state'] != 'completed' for item in recoveries):
            blockers.append({'code': 'unfinished_recovery', 'message': 'Confirm the original recovery receipt before changing courses.'})
        if labs:
            blockers.append({'code': 'prepared_lab_evidence', 'message': 'Prepared lab evidence needs an explicit disposition before changing courses.'})
        if scenarios:
            blockers.append({'code': 'saved_scenario_evidence', 'message': 'Saved scenario answers need an explicit disposition before changing courses.'})
        if executions:
            blockers.append({'code': 'saved_lab_execution', 'message': 'Saved lab runs need an explicit disposition before changing courses. Inspect running or uncertain work before any retry.'})
        if reviews:
            blockers.append({'code': 'saved_automatic_review', 'message': 'Saved automatic assessments need an explicit disposition before changing courses.'})
        if designs:
            blockers.append({'code': 'saved_workflow_design', 'message': 'Saved workflow approvals need an explicit disposition before changing courses.'})
        if processes:
            blockers.append({'code': 'saved_process_design', 'message': 'Saved process designs need an explicit disposition before changing courses.'})
        if decisions:
            blockers.append({'code': 'saved_learner_decision', 'message': 'Saved learner decisions need an explicit disposition before changing courses.'})
        if progress.pending_credential or (progress.certified and credential is None):
            blockers.append({'code': 'credential_preservation', 'message': 'Preserve the original credential before changing courses.'})
        if any(isinstance(value, dict) and value.get('self_assessment') and not value.get('completed') for value in progress.modules.values()):
            blockers.append({'code': 'unfinished_answers', 'message': 'Saved reflection answers remain in the current course; review unfinished work before deciding.'})
        original_credit = [{
            'module_id': module_id, 'stars': value.get('stars', 0),
            'completed_at': value.get('completed_at'), 'xp_earned': value.get('xp_earned', 0),
        } for module_id, value in progress.modules.items() if isinstance(value, dict) and value.get('completed')]
        # Names, XP, completion and even a legacy credential are not evidence
        # of new supervision outcomes. Never manufacture equivalence here.
        modules = [{
            'module_id': module.module_id,
            'title': next(item.title for item in target.manifest.modules if item.id == module.module_id),
            'outcomes': [{
                'outcome_id': outcome.id, 'statement': outcome.statement,
                'disposition': 'requires_assessment',
                'reason': 'No verified outcome-equivalence rule and assessed evidence are available for this transfer.',
            } for outcome in module.outcomes],
        } for module in contract.modules]
        # Detect writes or selection changes while assembling the view. The
        # retained fence catches writes that start AND finish between reads.
        current_selection = await repo.selections.find_one({'user_id': user_id})
        current_progress = await repo.progress.find_one(query)
        if _held_write:
            current_selection, current_progress = without_owned_write(current_selection, current_progress, user_id, source_id)
        current_attempts = await CertificationAttempt.get_motor_collection().find(pending_query).to_list(None)
        current_completion_history = await CertificationAttempt.get_motor_collection().find(lab_query, COMPLETION_SUMMARY_FIELDS).sort('uuid', 1).to_list(None)
        current_recoveries = await CertificationRecoveryRecord.get_motor_collection().find(lab_query, RECOVERY_SUMMARY_FIELDS).sort('uuid', 1).to_list(None)
        current_labs = await CertificationLabInput.get_motor_collection().find(lab_query, {'uuid': 1, 'module_id': 1, 'record_sha256': 1}).sort('uuid', 1).to_list(None)
        current_scenarios = await CertificationScenarioAttempt.get_motor_collection().find(lab_query, {'uuid': 1, 'module_id': 1, 'record_sha256': 1}).sort('uuid', 1).to_list(None)
        current_executions = await CertificationLabExecution.get_motor_collection().find(lab_query, EXECUTION_SUMMARY_FIELDS).sort('uuid', 1).to_list(None)
        current_reviews = await CertificationReviewAttempt.get_motor_collection().find(lab_query, REVIEW_SUMMARY_FIELDS).sort('uuid', 1).to_list(None)
        current_decisions = await CertificationLearnerDecision.get_motor_collection().find(lab_query, {'uuid': 1, 'module_id': 1, 'record_sha256': 1}).sort('uuid', 1).to_list(None)
        current_processes = await CertificationProcessSubmission.get_motor_collection().find(lab_query, {'uuid': 1, 'module_id': 1, 'record_sha256': 1}).sort('uuid', 1).to_list(None)
        current_designs = await CertificationWorkflowDesignSubmission.get_motor_collection().find(lab_query, {'uuid': 1, 'module_id': 1, 'record_sha256': 1}).sort('uuid', 1).to_list(None)
        current_credential = await CredentialRepository().for_enrollment(user_id, source_id)
        if (fingerprint(selection) != fingerprint(current_selection)
                or fingerprint(raw_progress) != fingerprint(current_progress)
                or fingerprint(attempts) != fingerprint(current_attempts)
                or fingerprint(completion_history) != fingerprint(current_completion_history)
                or fingerprint(recoveries) != fingerprint(current_recoveries)
                or fingerprint(labs) != fingerprint(current_labs)
                or fingerprint(scenarios) != fingerprint(current_scenarios)
                or fingerprint(executions) != fingerprint(current_executions)
                or fingerprint(reviews) != fingerprint(current_reviews)
                or fingerprint(decisions) != fingerprint(current_decisions)
                or fingerprint(designs) != fingerprint(current_designs)
                or fingerprint(processes) != fingerprint(current_processes)
                or credential != current_credential):
            raise EnrollmentConflict('Course work changed during the preview; refresh before reviewing it')
        result = {
            'mode': 'preparation_only', 'policy': 'optional', 'can_activate': False,
            'source': {
                'enrollment_id': source.uuid, 'course_version': source.course_version,
                'manifest_sha256': source.manifest_sha256, 'provenance': source.provenance,
                'total_xp': progress.total_xp, 'certified': progress.certified,
                'preserved_module_credit': original_credit,
                'credential_id': credential.credential_id if credential else None,
                'learning_position': progress.learning_position,
            },
            'target': {**target.summary(), 'state': target.entry.state, 'rubric_id': contract.rubric_id,
                       'contract_id': contract.contract_id, 'required_outcome_count': len(contract.required_outcomes()),
                       'transferred_outcome_count': 0, 'modules': modules},
            'pending_assessments': [{'attempt_id': attempt['uuid'], 'module_id': attempt['module_id'], 'state': attempt['state']} for attempt in attempts],
            'saved_completion_history': [{'attempt_id': item['uuid'], 'module_id': item['module_id'], 'state': item['state']}
                for item in completion_history if item['state'] not in ('evaluating', 'graded')],
            'saved_recovery_history': [{'recovery_id': item['uuid'], 'module_id': 'course', 'state': item['state']} for item in recoveries],
            'prepared_labs': [{'input_snapshot_id': lab['uuid'], 'module_id': lab['module_id']} for lab in labs],
            'saved_scenarios': [{'attempt_id': item['uuid'], 'module_id': item['module_id']} for item in scenarios],
            'saved_lab_runs': [{'run_id': item['uuid'], 'module_id': item['module_id'],
                                'input_snapshot_id': item['input_snapshot_id'], 'state': item['state']} for item in executions],
            'saved_automatic_reviews': [{'attempt_id': item['uuid'], 'module_id': item['module_id'], 'state': item['state']} for item in reviews],
            'saved_workflow_designs': [{'submission_id': item['uuid'], 'module_id': item['module_id']} for item in designs],
            'saved_process_designs': [{'submission_id': item['uuid'], 'module_id': item['module_id']} for item in processes],
            'saved_learner_decisions': [{'decision_id': item['uuid'], 'module_id': item['module_id']} for item in decisions],
            'blockers': blockers,
            'choice': 'Keeping your current course preserves its earned credit, saved place and original credential. Previewing another course changes nothing.',
            'source_snapshot_sha256': fingerprint({'selection': selection, 'progress': raw_progress, 'attempts': attempts, 'labs': labs, 'scenarios': scenarios, 'executions': executions, 'reviews': reviews, 'decisions': decisions, 'processes': processes, 'designs': designs, 'completion_history': completion_history, 'recoveries': recoveries}),
        }
        from .transition_disposition import preservation_plan
        result['preservation_plan'] = preservation_plan(result, module_titles={module.id: module.title
            for module in repo.catalog.load(source.course_version).manifest.modules})
        result['equivalence_plan'] = equivalence_plan(repo.catalog.load(source.course_version), target, progress)
        result['decision_basis_sha256'] = decision_basis(
            {'selection': selection, 'progress': raw_progress, 'attempts': attempts, 'labs': labs,
             'scenarios': scenarios, 'executions': executions, 'reviews': reviews, 'decisions': decisions,
             'processes': processes, 'designs': designs, 'completion_history': completion_history, 'recoveries': recoveries}, source, target, credential)
        result['preview_sha256'] = encode(result)[1]
        return result
