"""Fence a new completion against the credit counter the learner reviewed."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.certification import CertificationProgress

from .enrollments import EnrollmentConflict


class CompletionChanged(EnrollmentConflict):
    def __init__(self) -> None:
        super().__init__('Module completion changed in another request. Refresh your course and review its saved result before starting another completion')
        self.detail = {'code': 'CERTIFICATION_COMPLETION_CHANGED', 'message': str(self)}


class CompletionReviewRequired(EnrollmentConflict):
    def __init__(self) -> None:
        super().__init__('Reload the app and review your course’s latest saved result before starting a new completion')
        self.detail = {'code': 'CERTIFICATION_COMPLETION_REVIEW_REQUIRED', 'message': str(self)}


def check_completion_counter(progress: CertificationProgress, module_id: str, expected_attempts, *, required: bool=False) -> None:
    if expected_attempts is None:
        if required:
            raise CompletionReviewRequired()
        return
    if type(expected_attempts) is not int or expected_attempts < 0:
        raise EnrollmentConflict('Completion requires the original nonnegative module attempt counter')
    actual = progress.modules.get(module_id, {}).get('attempts', 0)
    if type(actual) is not int or actual != expected_attempts:
        raise CompletionChanged()
