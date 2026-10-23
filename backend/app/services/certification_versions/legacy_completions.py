"""Immutable results for explicitly identified unversioned completion requests.

The latest result is saved atomically with progress before being copied to its
insert-only receipt collection. Losing that copy or its response is recoverable
without evaluating changed learner answers or workspace artifacts again.
"""
import datetime
import hashlib
import json
import re

from pymongo.errors import DuplicateKeyError

from app.models.certification import CertificationProgress
from .attempts import AttemptRepository, encode
from .enrollments import EnrollmentConflict

COLLECTION = 'certification_legacy_completion_receipts'
KIND = 'legacy_completion.1'


def validate_request_id(request_id):
    if not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9]{32}', request_id):
        raise EnrollmentConflict('Completion requires a valid original request reference')


def records():
    return CertificationProgress.get_motor_collection().database[COLLECTION]


def record_id(user_id, progress_id, request_id):
    return hashlib.sha256(json.dumps([user_id, progress_id, request_id], separators=(',', ':')).encode()).hexdigest()


def payload(progress, receipt, module_id=None, request_id=None):
    if (not isinstance(receipt, dict) or receipt.get('kind') != KIND
            or receipt.get('user_id') != progress.user_id or receipt.get('progress_id') != str(progress.id)
            or not isinstance(receipt.get('module_id'), str) or not receipt['module_id']
            or not isinstance(receipt.get('recorded_at'), str)):
        raise EnrollmentConflict('The saved legacy completion belongs to a different progress record or is invalid')
    validate_request_id(receipt.get('request_id'))
    if ((module_id is not None and receipt['module_id'] != module_id)
            or (request_id is not None and receipt['request_id'] != request_id)):
        raise EnrollmentConflict('This completion reference belongs to a different module or request')
    result = AttemptRepository.payload(receipt, 'result')
    if result.get('module_id') != receipt['module_id'] or result.get('attempt_id') != receipt['request_id']:
        raise EnrollmentConflict('The saved completion result does not match its original request')
    return result


async def persist_pending(progress):
    receipt = progress.completion_receipt
    if not isinstance(receipt, dict) or receipt.get('kind') != KIND:
        return
    payload(progress, receipt)
    key = record_id(progress.user_id, str(progress.id), receipt['request_id'])
    try:
        await records().insert_one({'_id': key, **receipt})
    except DuplicateKeyError:
        existing = await records().find_one({'_id': key})
        if existing != {'_id': key, **receipt}:
            raise EnrollmentConflict('The original completion receipt changed; do not repeat this assessment')


async def previous(progress, module_id, request_id):
    validate_request_id(request_id)
    await persist_pending(progress)
    receipt = await records().find_one({'_id': record_id(progress.user_id, str(progress.id), request_id)})
    return payload(progress, receipt, module_id, request_id) if receipt else None


def prepare(progress, module_id, request_id, result):
    validate_request_id(request_id)
    result = {**result, 'module_id': module_id, 'attempt_id': request_id}
    serialized, digest = encode(result)
    progress.completion_receipt = {
        'kind': KIND, 'user_id': progress.user_id, 'progress_id': str(progress.id),
        'module_id': module_id, 'request_id': request_id,
        'recorded_at': datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        'result_json': serialized, 'result_sha256': digest,
    }
    return result
