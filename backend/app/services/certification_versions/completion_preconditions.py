"""Fence a new completion against the credit counter the learner reviewed."""
from .enrollments import EnrollmentConflict


class CompletionChanged(EnrollmentConflict):
    def __init__(self):
        super().__init__('Module completion changed in another request. Refresh your course and review its saved result before starting another completion')
        self.detail = {'code': 'CERTIFICATION_COMPLETION_CHANGED', 'message': str(self)}


def check_completion_counter(progress, module_id, expected_attempts):
    if expected_attempts is None:
        return
    if type(expected_attempts) is not int or expected_attempts < 0:
        raise EnrollmentConflict('Completion requires the original nonnegative module attempt counter')
    actual = progress.modules.get(module_id, {}).get('attempts', 0)
    if type(actual) is not int or actual != expected_attempts:
        raise CompletionChanged()
