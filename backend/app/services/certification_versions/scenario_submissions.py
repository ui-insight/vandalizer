"""Persist a learner's explicit scenario choices before linking the result.

Scenario recognition is separate from practical evidence and earned credit.
There is no automatic completion, XP award or agent self-assessment fallback.
"""
import datetime
import hashlib
import json
import re

from pymongo.errors import DuplicateKeyError
from bson import ObjectId

from app.models.certification import CertificationEnrollment, CertificationProgress, CertificationScenarioAttempt
from .attempts import encode
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .outcomes import package_outcomes
from .scenario_assessment import ScenarioBank
from .writes import require_lease, save_progress


def module_bank(package, module_id):
    if module_id not in {module.id for module in package.manifest.modules}:
        raise EnrollmentConflict('This module is not part of the selected course')
    path = f'assessments/{module_id}.json'
    if path not in package.manifest.artifacts:
        raise EnrollmentConflict('This course does not have a scenario assessment for that module')
    try:
        contract = package_outcomes(package)
        if contract is None:
            raise ValueError('Missing outcome contract')
        bank = ScenarioBank.model_validate_json(package.read(path))
        if bank.module_id != module_id:
            raise ValueError('Wrong assessment module')
        bank.verify_contract(contract)
        return bank
    except ValueError as exc:
        raise CourseCatalogError('The scenario bank does not match this course’s outcome contract') from exc


def answers_digest(record):
    """Exact deterministic assessment inputs, excluding a browser request UUID."""
    return encode({key: record[key] for key in (
        'user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256',
        'bank_sha256', 'answers', 'submission_channel')})[1]


class ScenarioSubmissionRepository:
    @property
    def records(self):
        return CertificationScenarioAttempt.get_motor_collection()

    @staticmethod
    def decode(raw):
        try:
            if hashlib.sha256(raw['record_json'].encode()).hexdigest() != raw['record_sha256']:
                raise ValueError('Digest mismatch')
            record = json.loads(raw['record_json'])
            if any(record[key] != raw[key] for key in (
                'uuid', 'user_id', 'enrollment_id', 'module_id', 'course_version', 'manifest_sha256', 'request_sha256',
            )):
                raise ValueError('Identity mismatch')
            if raw.get('answers_sha256') is not None and raw['answers_sha256'] != answers_digest(record):
                raise ValueError('Answer identity mismatch')
            return record
        except (ValueError, TypeError, KeyError) as exc:
            raise CourseCatalogError('The saved scenario submission failed its integrity check') from exc

    async def get(self, user_id, attempt_id):
        raw = await self.records.find_one({'uuid': attempt_id, 'user_id': user_id})
        return self.decode(raw) if raw else None

    async def status(self, user_id, attempt_id):
        """Read a receipt and its current link without grading or repairing it."""
        record = await self.get(user_id, attempt_id)
        if record is None:
            return None
        enrollment = await CertificationEnrollment.get_motor_collection().find_one({
            'uuid': record['enrollment_id'], 'user_id': user_id,
            'course_version': record['course_version'], 'manifest_sha256': record['manifest_sha256'],
        })
        progress = None
        if enrollment and ObjectId.is_valid(enrollment.get('progress_id')):
            progress = await CertificationProgress.get_motor_collection().find_one({
                '_id': ObjectId(enrollment['progress_id']), 'user_id': user_id,
                'enrollment_id': record['enrollment_id'], 'course_version': record['course_version'],
            })
        state = 'unavailable'
        if progress is not None:
            current = progress.get('modules', {}).get(record['module_id'], {}).get('scenario_attempt_id')
            if current == attempt_id:
                state = 'selected'
            elif current == record['previous_attempt_id']:
                state = 'unlinked'
            elif isinstance(current, str) and re.fullmatch(r'[a-f0-9]{32}', current):
                state = 'superseded'
        return {**record, 'progress_link': state, 'read_only': True}

    async def matching_answers(self, identity, digest):
        scope = {key: value for key, value in identity.items() if key != 'uuid'}
        # Historical receipts remain immutable; inspect their original inputs
        # without backfilling an index or regrading their saved result.
        async for raw in self.records.find({**scope, '$or': [
                {'answers_sha256': digest}, {'answers_sha256': None}]}).sort('_id', 1):
            record = self.decode(raw)
            if answers_digest(record) == digest:
                return record
        return None

    async def submit(self, operation, module_id, request_id, bank_sha256, answers, *, actor_user_id):
        progress, package = operation.progress, operation.package
        if not operation.writable or actor_user_id != operation.user_id or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise EnrollmentConflict('Scenario submission requires the authenticated learner and a writable course operation')
        lease = require_lease(actor_user_id, progress.enrollment_id)
        if (progress.user_id != actor_user_id or str(progress.id) != lease.progress_id
                or progress.course_version != package.manifest.release_id):
            raise EnrollmentConflict('The scenario submission does not match this enrollment')
        bank = module_bank(package, module_id)
        if bank_sha256 != bank.digest:
            raise EnrollmentConflict('The scenario definition changed; reload the selected course before submitting')
        identity = {'uuid': request_id, 'user_id': actor_user_id, 'enrollment_id': progress.enrollment_id,
                    'module_id': module_id, 'course_version': package.manifest.release_id,
                    'manifest_sha256': package.manifest_sha256}
        request_sha256 = encode({**identity, 'bank_sha256': bank_sha256, 'answers': answers})[1]
        digest = answers_digest({**identity, 'bank_sha256': bank_sha256, 'answers': answers,
                                 'submission_channel': 'authenticated_learner_request'})
        existing = await self.records.find_one({'uuid': request_id})
        if existing is not None:
            if any(existing.get(key) != value for key, value in identity.items()) or existing.get('request_sha256') != request_sha256:
                raise EnrollmentConflict('This scenario request was already used for different answers or another enrollment')
            record = self.decode(existing)
        else:
            record = await self.matching_answers(identity, digest)
        if existing is None and record is None:
            try:
                result = bank.grade(answers, expected_sha256=bank_sha256)
            except ValueError as exc:
                raise EnrollmentConflict(str(exc)) from exc
            record = {**identity, 'request_sha256': request_sha256, 'bank_sha256': bank_sha256,
                      'answers': answers, 'result': result,
                      'previous_attempt_id': progress.modules.get(module_id, {}).get('scenario_attempt_id'),
                      'submitted_at': datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
                      'submission_channel': 'authenticated_learner_request'}
            serialized, record_digest = encode(record)
            try:
                await self.records.insert_one({**identity, 'request_sha256': request_sha256, 'answers_sha256': digest,
                                               'record_json': serialized, 'record_sha256': record_digest})
            except DuplicateKeyError:
                saved = await self.records.find_one({'uuid': request_id})
                if saved is not None:
                    if saved.get('request_sha256') != request_sha256:
                        raise EnrollmentConflict('This scenario request identity was already claimed')
                    record = self.decode(saved)
                else:
                    record = await self.matching_answers(identity, digest)
                    if record is None:
                        raise EnrollmentConflict('The original scenario result could not be confirmed')
        # A retry may finish an interrupted pointer save. An old request must
        # never replace a newer submission that has since become current.
        module = progress.modules.get(module_id, {})
        current_id = module.get('scenario_attempt_id')
        canonical_id = record['uuid']
        linked = current_id == canonical_id
        if not linked and current_id == record['previous_attempt_id']:
            progress.modules[module_id] = {**module, 'scenario_attempt_id': canonical_id}
            progress.updated_at = datetime.datetime.now(tz=datetime.timezone.utc)
            await save_progress(progress)
            linked = True
        return {'attempt_id': canonical_id, 'reused_existing': canonical_id != request_id, 'module_id': module_id, 'bank_sha256': bank.digest,
                'linked_to_progress': linked, 'result': record['result']}
