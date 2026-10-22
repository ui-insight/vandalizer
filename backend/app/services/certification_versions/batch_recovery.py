"""Explicitly finalize a complete saved batch action without repeating provider work."""
import datetime
from typing import Literal

from .attempts import encode
from .enrollments import EnrollmentConflict
from .lab_inputs import LabInputRepository
from .outcomes import ContractModel
from .batch_execution import MAX_TERMINAL_BYTES
from .batch_preparation import BatchPreparation
from .batch_runtime import complete_result
from .batch_preparation import Digest, Identity


class BatchFinalizationRequest(ContractModel):
    run_id: Identity
    plan_sha256: Digest
    authorization_sha256: Digest
    item_events_sha256: Digest
    consent: Literal['finalize_saved_batch_results_without_reexecution']


class BatchRecovery(BatchPreparation):
    async def finalize(self, operation, body, *, actor_user_id):
        body = BatchFinalizationRequest.model_validate(body)
        if actor_user_id != operation.user_id:
            raise EnrollmentConflict('Only the authenticated learner can finalize this saved batch action')
        run = await self.get(actor_user_id, body.run_id)
        if run is None:
            raise EnrollmentConflict('The original batch action is unavailable')
        lease = self.check_operation(operation, run['plan'])
        if (run['plan_sha256'] != body.plan_sha256 or run['authorization'] is None
                or encode(run['authorization'])[1] != body.authorization_sha256
                or encode(run['item_events'])[1] != body.item_events_sha256):
            raise EnrollmentConflict('The saved plan, approval or exact case results changed')
        if run['state'] == 'completed':
            return run
        count = len(run['plan']['item_plans']) * 2
        if run['state'] != 'executing' or len(run['item_events']) != count:
            raise EnrollmentConflict('Only a complete saved item inventory without a terminal receipt can be finalized')
        result = {**complete_result(run['plan'], [item['receipt']['result'] for item in run['item_events'][1::2]]),
            'run_id': run['run_id'], 'plan_sha256': run['plan_sha256'], 'authorization_sha256': body.authorization_sha256,
            'item_events_sha256': body.item_events_sha256, 'item_event_count': count, 'started_at': None, 'finished_at': None,
            'completion_mode': 'finalized_from_saved_item_receipts', 'finalization_request': body.model_dump(mode='json'),
            'finalization_actor_user_id': actor_user_id,
            'receipt_finalized_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        serialized, digest = encode(result)
        if len(serialized.encode()) > MAX_TERMINAL_BYTES:
            raise EnrollmentConflict('The complete saved result exceeds its terminal storage limit')
        await LabInputRepository._check_lease(lease)
        updated = await self.records.update_one({'uuid': run['run_id'], 'user_id': actor_user_id, 'state': 'executing',
            'plan_sha256': body.plan_sha256, 'authorization_sha256': body.authorization_sha256,
            'item_events_sha256': body.item_events_sha256, 'item_event_count': count, 'result_json': None},
            {'$set': {'state': 'completed', 'checkpoint_closed': True, 'result_json': serialized, 'result_sha256': digest}})
        if updated.modified_count != 1:
            latest = await self.get(actor_user_id, body.run_id)
            if latest and latest['state'] == 'completed':
                return latest
            raise EnrollmentConflict('The saved batch action changed before its terminal receipt could be finalized')
        return await self.get(actor_user_id, body.run_id)
