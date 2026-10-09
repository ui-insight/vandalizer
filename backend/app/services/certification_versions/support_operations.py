"""Bounded, read-only operation summaries with no source text or provider errors."""
import re

from app.models.certification import CertificationEnrollmentSelection
from .catalog import CourseCatalogError
from .lab_execution import LabExecutionRepository
from .outcomes import package_outcomes
from .review_attempts import ReviewAttemptRepository
from .review_delivery import ReviewDelivery

REVIEW_STEPS = {
    'prepared': 'The saved automatic review has not started. The learner can open that request in the original course.',
    'evaluating': 'The automatic review has no final result. Inspect that same request; do not create a duplicate review.',
    'requirements_supported': 'The saved review supports its assessed requirements. Module credit still requires the learner’s explicit evidence selection and completion.',
    'revision_required': 'Open the original feedback and revise the identified evidence. A new review preserves this original result.',
    'grading_unavailable': 'Automatic grading was unavailable. This is not a learner failure. Use the learner’s technical recovery or retry for the same saved evidence; staff grading is not required.',
}
RUN_STEPS = {
    'prepared': 'A run plan is saved but execution is not confirmed. The learner should review its scope and approval in the original course.',
    'executing': 'The run has no final receipt. Inspect the original run and its saved stages before retrying anything.',
    'completed': 'An execution receipt is saved. Execution alone does not prove that the required outcomes passed.',
    'failed': 'The run ended without completion. Inspect the original result: it may be a controlled failure exercise or an execution problem. Preserve successful stages before retrying.',
    'uncertain': 'The run outcome is uncertain. Check saved results and stage receipts before any retry to avoid duplicate work.',
}


def reference(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise CourseCatalogError('Original operation reference needs reconciliation')
    return value


def run_decoder(module_id):
    # Each workflow owns additional evidence checks beyond the common envelope.
    from .advanced_workflow_preparation import AdvancedWorkflowPreparation
    from .batch_preparation import BatchPreparation
    from .connected_workflow_preparation import ConnectedWorkflowPreparation
    from .governance_preparation import GovernancePreparation
    from .output_workflow_preparation import OutputWorkflowPreparation
    from .validation_preparation import ValidationPreparation
    return {
        'foundations': LabExecutionRepository, 'extraction_engine': LabExecutionRepository,
        'multi_step': ConnectedWorkflowPreparation, 'advanced_nodes': AdvancedWorkflowPreparation,
        'output_delivery': OutputWorkflowPreparation, 'validation_qa': ValidationPreparation,
        'batch_processing': BatchPreparation, 'governance': GovernancePreparation,
    }.get(module_id)


async def bounded_records(collection, identity, pending_states):
    # Show pending requests even when newer completed work fills the recent list.
    pending = await collection.find({**identity, 'state': {'$in': pending_states}}, {'_id': 1}).sort('_id', -1).limit(6).to_list(6)
    recent = await collection.find(identity, {'_id': 1}).sort('_id', -1).limit(6).to_list(6)
    seen, rows = set(), []
    for row in pending[:5] + recent[:5]:
        if row['_id'] not in seen:
            seen.add(row['_id'])
            rows.append(row)
    return rows, len(pending) > 5, len(recent) > 5


async def support_operations(enrollment, package):
    identity = {'user_id': enrollment.user_id, 'enrollment_id': enrollment.uuid}
    modules = {module.id: module for module in package.manifest.modules}
    contract = package_outcomes(package)
    selection = await CertificationEnrollmentSelection.get_motor_collection().find_one({'user_id': enrollment.user_id})
    selected = bool(selection and selection.get('active_enrollment_id') == enrollment.uuid)
    in_flight = selection.get('in_flight_writes') if selected else 0
    result = {'worker_marked_in_flight': type(in_flight) is int and in_flight > 0,
              'course_change_pending': bool(selected and selection.get('pending_transition_id')),
              'groups': []}
    for kind, journal, pending, steps in (
        ('automatic_review', ReviewAttemptRepository(), ['prepared', 'evaluating', 'unavailable'], REVIEW_STEPS),
        ('lab_run', LabExecutionRepository(), ['prepared', 'executing', 'uncertain'], RUN_STEPS),
    ):
        rows, more_pending, more_recent = await bounded_records(journal.records, identity, pending)
        group = {'kind': kind, 'records': [], 'more_pending': more_pending, 'more_recent': more_recent}
        for marker in rows:
            try:
                row = await journal.records.find_one({**identity, '_id': marker['_id']})
                request_id = reference(row.get('uuid'))
                module_id = row.get('module_id')
                if (module_id not in modules or any(row.get(key) != value for key, value in {
                        **identity, 'course_version': enrollment.course_version, 'manifest_sha256': package.manifest_sha256}.items())):
                    raise CourseCatalogError('Original operation course needs reconciliation')
                refs, failed = {}, []
                if kind == 'automatic_review':
                    if contract is None:
                        raise CourseCatalogError('Original automatic review contract is unavailable')
                    public = ReviewDelivery.public(journal.decode(row), enrollment, contract)
                    state = public['status']
                    for key in ('run_id', 'parent_attempt_id', 'process_submission_id', 'workflow_design_submission_id',
                                'connected_review_submission_id', 'budget_review_submission_id', 'output_review_submission_id',
                                'validation_review_submission_id', 'batch_review_submission_id', 'governance_review_submission_id'):
                        if public.get(key) is not None:
                            refs[key] = reference(public[key])
                    if state == 'revision_required':
                        failed = [{'outcome_id': outcome['outcome_id'], 'statement': outcome['statement']}
                                  for outcome in public['outcomes'] if outcome['verdict'] in ('contradicted', 'unclear')]
                else:
                    decoder = run_decoder(module_id)
                    if decoder is None:
                        raise CourseCatalogError('Original lab executor is unavailable')
                    saved = decoder.decode(row)
                    state = saved['state']
                    refs['input_snapshot_id'] = reference(saved['plan']['input_snapshot_id'])
                group['records'].append({'request_id': request_id, 'module_id': module_id,
                    'module_title': modules[module_id].title, 'state': state, 'next_step': steps[state],
                    'references': refs, 'failed_required_outcomes': failed})
            except (CourseCatalogError, KeyError, TypeError, ValueError, AttributeError):
                group['records'].append({'state': 'unavailable',
                    'next_step': 'This original operation needs reconciliation. No result, evidence or safe retry is inferred.'})
        result['groups'].append(group)
    from .support_handoffs import support_handoffs
    result['groups'].append(await support_handoffs(enrollment, package))
    return result
