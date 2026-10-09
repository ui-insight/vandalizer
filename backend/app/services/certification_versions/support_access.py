"""Access-only administrator changes, recorded atomically with their effect."""
import datetime

from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument

from app.models.certification import CertificationProgress
from .enrollments import EnrollmentConflict

JOURNAL = '_certification_access_changes'


class AccessChangeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    unlocked: bool = Field(strict=True)
    reason: str = Field(min_length=5, max_length=1000)


async def apply_access_change(repository, progress, request, actor_user_id, access_filter):
    """The audit event and flag share one Mongo write; earned fields are untouched.

    This private journal is outside the learner progress model. Ordinary model
    serialization cannot expose administrator reasons to learner APIs, and
    fenced progress saves use $set without erasing this append-only history.
    """
    if not isinstance(actor_user_id, str) or not actor_user_id.strip():
        raise EnrollmentConflict('An authenticated administrator is required for an access change')
    identity = {'_id': progress.id, 'user_id': progress.user_id}

    async def replay():
        current = await repository.progress.find_one(identity)
        events = current.get(JOURNAL, []) if current else []
        if not isinstance(events, list):
            raise EnrollmentConflict('The access history needs reconciliation before another change')
        existing = [entry for entry in events if isinstance(entry, dict) and entry.get('request_id') == request.request_id]
        if not existing:
            return None
        if len(existing) != 1 or any(existing[0].get(key) != value for key, value in {
            'actor_user_id': actor_user_id, 'unlocked': request.unlocked, 'reason': request.reason,
            'enrollment_id': progress.enrollment_id, 'course_version': progress.course_version,
        }.items()):
            raise EnrollmentConflict('This access request already belongs to a different change')
        return CertificationProgress.model_validate(current)

    existing = await replay()
    if existing is not None:
        return existing
    now = datetime.datetime.now(datetime.timezone.utc)
    event = {**request.model_dump(), 'actor_user_id': actor_user_id,
             'previous_unlocked': progress.unlocked, 'recorded_at': now,
             'enrollment_id': progress.enrollment_id, 'course_version': progress.course_version,
             'credit_effect': 'none'}
    saved = await repository.progress.find_one_and_update(
        {**identity, **access_filter, f'{JOURNAL}.request_id': {'$ne': request.request_id}},
        {'$set': {'unlocked': request.unlocked, 'updated_at': now}, '$push': {JOURNAL: event}},
        return_document=ReturnDocument.AFTER,
    )
    if saved is None:
        existing = await replay()
        if existing is not None:
            return existing
        raise EnrollmentConflict('The reviewed access or course binding changed; refresh before changing prerequisites')
    return CertificationProgress.model_validate(saved)


async def access_history(repository, progress):
    raw = await repository.progress.find_one(
        {'_id': progress.id, 'user_id': progress.user_id}, {'user_id': 1, JOURNAL: {'$slice': -11}})
    events = raw.get(JOURNAL, []) if raw else []
    result = {'state': 'not_recorded', 'changes': [], 'older_available': False,
              'historical_unlocked': progress.unlocked}
    if not isinstance(events, list):
        return {**result, 'state': 'unavailable'}
    try:
        for event in reversed(events[-10:]):
            request = AccessChangeRequest.model_validate({key: event[key] for key in ('request_id', 'unlocked', 'reason')})
            if (not isinstance(event['actor_user_id'], str) or not event['actor_user_id'].strip()
                    or type(event['previous_unlocked']) is not bool or event['credit_effect'] != 'none'
                    or not isinstance(event['recorded_at'], datetime.datetime)):
                raise ValueError('Invalid access event')
            result['changes'].append({**request.model_dump(), 'actor_user_id': event['actor_user_id'],
                                      'previous_unlocked': event['previous_unlocked'],
                                      'recorded_at': event['recorded_at'].isoformat(), 'credit_effect': 'none'})
    except (KeyError, TypeError, ValueError):
        return {**result, 'state': 'unavailable', 'changes': []}
    return {**result, 'state': 'recorded' if events else 'not_recorded', 'older_available': len(events) > 10}
