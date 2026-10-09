"""Owner-only confirmation of an already committed course selection.

Reading never repairs data. Confirmation can only finish the exact committed
journal; it cannot prepare, activate, return to or resume another course.
Original receipts remain confirmable when new course delivery is disabled.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .attempts import AttemptRepository
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .saved_course_selection import SavedCourseSelectionRepository
from .upgrade_activation import UpgradeActivationRepository


SelectionKind = Literal['optional_upgrade_selection.1', 'saved_course_selection.1']


class SelectionConfirmation(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    kind: SelectionKind
    receipt_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['confirm_original_committed_course_selection']


class SelectionDelivery:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()

    def journal(self, kind):
        if kind == 'optional_upgrade_selection.1':
            return UpgradeActivationRepository(self.repository)
        if kind == 'saved_course_selection.1':
            return SavedCourseSelectionRepository(self.repository)
        raise CourseCatalogError('The saved course switch has an unknown receipt type')

    async def original(self, user_id, kind, request_id):
        journal = self.journal(kind)
        raw = await journal.records.find_one({'uuid': request_id, 'user_id': user_id})
        if raw is None:
            raise EnrollmentConflict('The original saved course-switch receipt is unavailable')
        journal.decode(raw)
        return journal, raw

    @staticmethod
    def verify(journal, raw, receipt):
        if not isinstance(receipt, dict):
            raise CourseCatalogError('The saved course switch receipt is malformed')
        try:
            return journal.verify_receipt(raw, receipt)
        except (KeyError, TypeError, ValueError) as exc:
            raise CourseCatalogError('The saved course switch receipt failed integrity verification') from exc

    @staticmethod
    def matches_selection(selection, receipt, request_id):
        if (selection.get('pending_transition_id') != request_id
                or selection.get('active_enrollment_id') != receipt.get('target_enrollment_id')
                or selection.get('revision') != receipt.get('revision')
                or selection.get('in_flight_writes') != 0 or selection.get('active_write')):
            raise EnrollmentConflict('The selected course no longer matches this unconfirmed switch')

    @staticmethod
    def summary(receipt, request_id):
        # Allowlist: no original answers, grading payloads or learner identity.
        return {'request_id': request_id, **{key: receipt[key] for key in (
            'kind', 'receipt_sha256', 'source_enrollment_id', 'target_enrollment_id',
            'target_course_version', 'target_manifest_sha256', 'revision', 'selected_at')},
            'action': receipt.get('action', 'activate_optional_upgrade'),
            'credit_transferred': False, 'histories_preserved': True}

    async def status(self, user_id):
        selection = await self.repository.selections.find_one({'user_id': user_id})
        result = {'read_only': True, 'current_enrollment_id': (selection or {}).get('active_enrollment_id'),
                  'pending': None}
        if not selection or not selection.get('pending_transition_id'):
            if selection and selection.get('in_flight_writes'):
                from .selection_preparation_recovery import SelectionPreparationRecovery
                preparation = await SelectionPreparationRecovery(self.repository).delivery_status(user_id, selection)
                if preparation:
                    result['preparation'] = preparation
            return result
        request_id = selection['pending_transition_id']
        receipt = selection.get('last_transition') or {}
        if not isinstance(receipt, dict):
            raise CourseCatalogError('The saved course switch receipt is malformed')
        journal, raw = await self.original(user_id, receipt.get('kind'), request_id)
        self.verify(journal, raw, receipt)
        self.matches_selection(selection, receipt, request_id)
        if raw['state'] == 'applied' and AttemptRepository.payload(raw, 'result') != receipt:
            raise CourseCatalogError('The selected course differs from its original recorded receipt')
        after = await self.repository.selections.find_one({'user_id': user_id})
        if after != selection:
            raise EnrollmentConflict('The course switch changed during confirmation review; refresh its status')
        result['pending'] = self.summary(receipt, request_id)
        return result

    async def confirm(self, user_id, body):
        request = SelectionConfirmation.model_validate(body)
        journal, raw = await self.original(user_id, request.kind, request.request_id)
        if raw['state'] == 'applied':
            receipt = AttemptRepository.payload(raw, 'result')
            selection = await self.repository.selections.find_one({'user_id': user_id})
            if (selection or {}).get('pending_transition_id') == request.request_id:
                self.matches_selection(selection, receipt, request.request_id)
                if selection.get('last_transition') != receipt:
                    raise CourseCatalogError('The pending switch differs from its original confirmed receipt')
        else:
            selection = await self.repository.selections.find_one({'user_id': user_id})
            receipt = (selection or {}).get('last_transition') or {}
            self.verify(journal, raw, receipt)
            self.matches_selection(selection or {}, receipt, request.request_id)
        if receipt['receipt_sha256'] != request.receipt_sha256:
            raise EnrollmentConflict('Confirm the original saved receipt; the reviewed switch has changed')
        # resume_receipt has no activation path. It verifies the committed CAS
        # before finalizing and only clears its own matching pending marker.
        result = await journal.resume_receipt(raw)
        if result is None:
            raise EnrollmentConflict('This course switch has not committed; nothing was selected by confirmation')
        return {'confirmed': True, 'selection_changed': False,
                'receipt': self.summary(result, request.request_id)}
