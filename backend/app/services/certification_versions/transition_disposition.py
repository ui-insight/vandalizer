"""Non-executing preservation proposals for the exact transition inventory.

This classifies saved operation metadata, not grading validity or authorization
for activation. It never transfers credit, resumes a worker or discards work.
"""
from .attempts import encode
from .catalog import CourseCatalogError

GROUPS = (
    ('pending_assessments', 'attempt_id', 'Module completion'),
    ('saved_completion_history', 'attempt_id', 'Original completion result'),
    ('saved_recovery_history', 'recovery_id', 'Recovery record'),
    ('prepared_labs', 'input_snapshot_id', 'Saved lab inputs'),
    ('saved_scenarios', 'attempt_id', 'Scenario answers'),
    ('saved_lab_runs', 'run_id', 'Lab run'),
    ('saved_automatic_reviews', 'attempt_id', 'Automatic assessment'),
    ('saved_workflow_designs', 'submission_id', 'Workflow approval'),
    ('saved_process_designs', 'submission_id', 'Process design'),
    ('saved_learner_decisions', 'decision_id', 'Learner decision'),
)


def preservation_plan(preview, *, module_titles):
    entries = []
    for kind, reference_key, label in GROUPS:
        for record in preview[kind]:
            state = record.get('state', 'saved')
            action = 'retain_saved_work'
            explanation = 'Keep this saved work with its original course. It does not transfer or prove a new required outcome.'
            if kind == 'pending_assessments':
                if state not in ('evaluating', 'graded'):
                    raise CourseCatalogError('The pending completion state needs reconciliation')
                action = 'reconcile_operation'
                explanation = ('Confirm the original completion result before a switch. Preserve any saved grade and earned credit; do not create a replacement attempt.')
            elif kind == 'saved_completion_history':
                if state not in ('applied', 'rejected', 'failed'):
                    raise CourseCatalogError('The saved completion state needs reconciliation')
                action = 'retain_original_result'
                explanation = 'Keep the original completion result, including failed attempts, with this course. This plan does not change earned credit or retry it.'
            elif kind == 'saved_recovery_history':
                if state == 'started':
                    action = 'reconcile_operation'
                    explanation = 'Confirm the original recovery result before a switch. Preserve its receipt; do not start a replacement recovery.'
                elif state == 'completed':
                    action = 'retain_original_result'
                    explanation = 'Keep the completed recovery receipt with its original course and assessment. Do not repeat the recovery.'
                else:
                    raise CourseCatalogError('The saved recovery state needs reconciliation')
            elif kind == 'saved_lab_runs':
                if state in ('executing', 'uncertain'):
                    action = 'reconcile_operation'
                    explanation = 'Resolve the original run and any external effects before a switch. Do not rerun it to discover whether it finished.'
                elif state == 'prepared':
                    action = 'retain_unexecuted_work'
                    explanation = 'Keep the prepared run with its original course. This plan does not approve or execute it.'
                elif state in ('completed', 'failed'):
                    action = 'retain_original_result'
                    explanation = 'Keep the original run result, including failures, with its original course. Do not rerun or transfer it.'
                else:
                    raise CourseCatalogError('The saved lab state needs reconciliation')
            elif kind == 'saved_automatic_reviews':
                if state == 'evaluating':
                    action = 'reconcile_operation'
                    explanation = 'Resolve the original automatic assessment before a switch. Keep its original evidence and do not start another assessment.'
                elif state == 'prepared':
                    action = 'retain_unassessed_work'
                    explanation = 'Keep the prepared evidence with its original course. No final assessment is recorded and this plan does not run one.'
                elif state in ('evaluated', 'unavailable'):
                    action = 'retain_original_result'
                    explanation = 'Keep the original automatic feedback or technical failure with its original course. This does not award or transfer credit.'
                else:
                    raise CourseCatalogError('The saved automatic assessment state needs reconciliation')
            entries.append({'kind': kind, 'label': label, 'record_id': record[reference_key],
                            'module_id': record['module_id'], 'module_title': 'Course recovery' if kind == 'saved_recovery_history' else module_titles.get(record['module_id'], 'Saved module'), 'state': state, 'proposed_action': action,
                            'reconciliation_required': action == 'reconcile_operation', 'explanation': explanation})
    result = {'policy': 'retain_with_original_enrollment', 'source_enrollment_id': preview['source']['enrollment_id'],
              'read_only': True, 'can_activate': False, 'credit_transferred': False,
              'reconciliation_required_count': sum(item['reconciliation_required'] for item in entries),
              'entries': entries}
    result['plan_sha256'] = encode(result)[1]
    return result
