"""Explicitly finalize a complete saved suite without repeating provider work."""
import datetime
from typing import Literal

from .attempts import encode
from .enrollments import EnrollmentConflict
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel
from .validation_execution import MAX_TERMINAL_BYTES
from .validation_preparation import ValidationPreparation
from .validation_runtime import complete_result
from .validation_suites import Digest, Identity


class ValidationFinalizationRequest(ContractModel):
    run_id: Identity
    plan_sha256: Digest
    authorization_sha256: Digest
    case_events_sha256: Digest
    consent: Literal['finalize_saved_validation_results_without_reexecution']


class ValidationRecovery(ValidationPreparation):
    async def finalize(self, operation, body, *, actor_user_id):
        body = ValidationFinalizationRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can finalize this saved suite')
        run = await self.get(actor_user_id, body.run_id)
        if run is None:
            raise EnrollmentConflict('The original validation suite is unavailable')
        lease = self.check_operation(operation, run['plan'])
        if (run['plan_sha256'] != body.plan_sha256 or run['authorization'] is None
                or encode(run['authorization'])[1] != body.authorization_sha256
                or encode(run['case_events'])[1] != body.case_events_sha256):
            raise EnrollmentConflict('The saved plan, approval or exact case results changed')
        if run['state'] == 'completed':
            return run
        if (run['state'] != 'executing' or len(run['case_events']) != 4
                or any(item['receipt']['result']['status'] != 'completed' for item in run['case_events'][1::2])):
            raise EnrollmentConflict('Only a complete saved two-case suite without a terminal receipt can be finalized')
        result = {**complete_result(run['plan'], [item['receipt']['result'] for item in run['case_events'][1::2]]),
            'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'], 'authorization_sha256': body.authorization_sha256,
            'case_events_sha256': body.case_events_sha256, 'case_event_count': 4, 'started_at': None, 'finished_at': None,
            'completion_mode': 'finalized_from_saved_case_receipts', 'finalization_request': body.model_dump(mode='json'),
            'finalization_actor_user_id': actor_user_id,
            'receipt_finalized_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(result)
        if len(serialized.encode()) > MAX_TERMINAL_BYTES:
            raise EnrollmentConflict('The complete saved result exceeds its terminal storage limit')
        await LabInputRepository._check_lease(lease)
        updated = await self.records.update_one({'uuid': run['run_id'], 'user_id': actor_user_id, 'state': 'executing',
            'plan_sha256': body.plan_sha256, 'authorization_sha256': body.authorization_sha256,
            'case_events_sha256': body.case_events_sha256, 'case_event_count': 4, 'result_json': None},
            {'$set': {'state': 'completed', 'checkpoint_closed': True, 'result_json': serialized, 'result_sha256': digest}})
        if updated.modified_count != 1:
            latest = await self.get(actor_user_id, body.run_id)
            if latest and latest['state'] == 'completed':
                return latest
            raise EnrollmentConflict('The saved suite changed before its terminal receipt could be finalized')
        return await self.get(actor_user_id, body.run_id)
