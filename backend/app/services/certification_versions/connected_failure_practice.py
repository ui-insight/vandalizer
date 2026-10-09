"""Disclosed training rejection, distinct from a provider error or authored run."""
from .enrollments import EnrollmentConflict

PRACTICE_CONSENT = 'prepare_controlled_failure_rehearsal'
STOP_MARKER = 'controlled_training_rejection_before_reasoning_provider'


class ControlledTrainingStop(Exception):
    """The approved practice deliberately stopped before the reasoning call."""


def is_failure_practice(plan):
    return plan.get('request', {}).get('consent') == PRACTICE_CONSENT


def approval_question(public_case, consent):
    question = next(item for item in public_case['questions'] if item['id'] == 'scope_approval')
    if consent != PRACTICE_CONSENT:
        return question
    practice = public_case.get('controlled_failure_practice')
    if not practice:
        raise EnrollmentConflict('This original course does not include a controlled failure rehearsal')
    return {**question, 'prompt': question['prompt'] + '\n\n' + practice['notice']}


def stopped_stage_result():
    # This is an actual executor rejection before dispatch, not invented model
    # output. Its marker must be carried into every display and recovery choice.
    return {'step_name': 'Prompt', 'output': None, 'training_stop': STOP_MARKER,
            'provider_dispatched': False,
            'error': 'Disclosed training rejection before reasoning dispatch. The successful extraction is preserved; Formatter did not start.'}
