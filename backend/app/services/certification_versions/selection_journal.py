"""Confirm one committed selection without repeating or replacing it."""
from .attempts import AttemptRepository, encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict


class SelectionJournal:
    receipt_id_field = 'activation_id'

    async def resume_receipt(self, raw):
        self.decode(raw)
        if raw['state'] == 'applied':
            result = AttemptRepository.payload(raw, 'result')
            await self.clear_pending(raw, result)
            return result
        selection = await self.repository.selections.find_one({'user_id': raw['user_id']})
        result = (selection or {}).get('last_transition') or {}
        if result.get(self.receipt_id_field) != raw['uuid']:
            return None
        self.verify_receipt(raw, result)
        if (selection['active_enrollment_id'] != result['target_enrollment_id']
                or selection.get('pending_transition_id') != raw['uuid']
                or selection['revision'] != result['revision']):
            raise EnrollmentConflict('The unconfirmed selection no longer matches its original switch receipt')
        return await self.finalize(raw, result)

    async def finalize(self, raw, result):
        self.decode(raw)
        self.verify_receipt(raw, result)
        selected = await self.repository.selections.find_one({'user_id': raw['user_id'],
            'active_enrollment_id': result['target_enrollment_id'], 'revision': result['revision'],
            'pending_transition_id': raw['uuid'], 'last_transition': result})
        if selected is None:
            raise EnrollmentConflict('An original committed selection receipt is required before confirming a switch')
        payload, digest = encode(result)
        await self.records.update_one({'uuid': raw['uuid'], 'user_id': raw['user_id'],
            'state': 'prepared', 'record_sha256': raw['record_sha256']},
            {'$set': {'state': 'applied', 'result_json': payload, 'result_sha256': digest}})
        saved = await self.records.find_one({'uuid': raw['uuid'], 'user_id': raw['user_id']})
        if saved is None or saved['state'] != 'applied':
            raise EnrollmentConflict('Confirm the original switch receipt before starting new course work')
        self.decode(saved)
        if AttemptRepository.payload(saved, 'result') != result:
            raise CourseCatalogError('The original switch already has a different recorded result')
        await self.clear_pending(saved, result)
        return result

    async def clear_pending(self, raw, result):
        # A later selection or active worker is never cleared by old replay.
        query = {'user_id': raw['user_id'],
            'active_enrollment_id': result['target_enrollment_id'], 'revision': result['revision'],
            'pending_transition_id': raw['uuid'], 'in_flight_writes': 0, 'active_write': None}
        selected = await self.repository.selections.find_one(query)
        if selected is None:
            return
        # Canonical journal JSON sorts keys; Mongo embedded-document equality
        # also compares key order. Compare values, then CAS the actual stored
        # document so replay survives serialization without weakening identity.
        if selected.get('last_transition') != result:
            raise CourseCatalogError('The pending switch differs from its original confirmed receipt')
        await self.repository.selections.update_one({**query, 'last_transition': selected['last_transition']},
            {'$unset': {'pending_transition_id': ''}})
