"""Explicit whole-module credit transfer through the completion journal.

The original enrollment is read only. A target module is eligible only when
every required outcome has an authored equivalence and original passing credit.
Carried XP contributes to target-course progress; no new base reward is earned.
"""
from copy import deepcopy
from types import SimpleNamespace
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from .attempts import AttemptRepository, encode, progress_digest
from .catalog import CourseCatalog, CourseCatalogError
from .credit_equivalence import equivalence_plan
from .enrollments import EnrollmentConflict, EnrollmentRepository
from .outcomes import ContractModel


class CreditTransferRequest(ContractModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    source_enrollment_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    target_enrollment_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    module_id: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
    preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    consent: Literal['transfer_reviewed_module_credit_preserve_original_no_new_xp_reward']


def verify_transfer_credit(package, progress, module_id, credit, *, depth=0):
    """Revalidate frozen original evidence, including before credential issuance."""
    from .outcome_credit import verified_credit_snapshot
    try:
        if depth >= 12 or package.catalog_root is None:
            raise ValueError('Original course catalog is unavailable or transfer chain is too long')
        request = CreditTransferRequest.model_validate(AttemptRepository.payload(credit, 'transfer_request'))
        validation = AttemptRepository.payload(credit, 'validation')
        proof = validation['credit_transfer']
        if (request.request_id != credit['attempt_id'] or request.target_enrollment_id != progress.enrollment_id
                or request.module_id != module_id or proof['user_id'] != progress.user_id
                or request.source_enrollment_id != proof['source_enrollment_id']
                or request.source_enrollment_id == request.target_enrollment_id
                or validation['assessment_kind'] != 'transferred_outcome_validation'
                or validation['passed'] is not True or validation['stars'] != 1
                or validation['credit_awarded'] is not False or validation['staff_review_required'] is not False
                or validation['course_version'] != package.manifest.release_id
                or validation['manifest_sha256'] != package.manifest_sha256
                or validation['rubric_id'] != package.manifest.rubric_id
                or proof['policy_sha256'] != package.manifest.artifacts.get('credit-equivalence.json')
                or proof['xp_earned'] != 0):
            raise ValueError('Transfer identity or requirements differ')
        source = CourseCatalog(package.catalog_root).load(proof['source_version'])
        if source.manifest_sha256 != proof['source_manifest_sha256']:
            raise ValueError('Original course requirements changed')
        saved = proof['source_module']
        original_progress = SimpleNamespace(user_id=progress.user_id, enrollment_id=proof['source_enrollment_id'],
            course_version=source.manifest.release_id, modules={module_id: saved})
        original = verified_credit_snapshot(source, original_progress, module_id, saved['outcome_credit'],
            expected_attempt_id=saved['completion_attempt_id'], _transfer_depth=depth + 1)
        # Avoid recursing twice through older transfers while checking the
        # current policy. Equivalence itself still verifies its supplied credit.
        plan = equivalence_plan(source, package, original_progress, _verified_snapshots={module_id: original})
        rows = [row for row in plan['outcomes'] if row['module_id'] == module_id]
        if not rows or any(row['status'] != 'eligible_for_transfer' for row in rows):
            raise ValueError('Not every required outcome is equivalent')
        if proof['outcomes'] != rows or proof['source_assessment_sha256'] != encode(original)[1]:
            raise ValueError('Original assessed outcomes differ from the transfer')
        module = next(item for item in package.manifest.modules if item.id == module_id)
        if proof['xp_carried'] != module.base_xp:
            raise ValueError('Carried XP differs from the target course')
        required = {row['outcome_id'] for row in rows}
        checks = validation['checks']
        if (len(checks) != len(required) or {row['id'] for row in checks} != required
                or any(row['passed'] is not True or row['role'] != 'required' for row in checks)):
            raise ValueError('Transfer checks are incomplete')
        return {'assessment_kind': 'transferred_outcomes', 'enrollment_id': progress.enrollment_id,
            'course_version': package.manifest.release_id, 'manifest_sha256': package.manifest_sha256,
            'module_id': module_id, 'rubric_id': package.manifest.rubric_id,
            'outcomes': rows, 'selected_receipts': original['selected_receipts'],
            'source_assessment': original, 'source_enrollment_id': proof['source_enrollment_id'],
            'source_completion_attempt_id': saved['completion_attempt_id'],
            'policy_sha256': proof['policy_sha256'], 'transfer_request_id': request.request_id,
            'xp_carried': proof['xp_carried'], 'xp_earned': 0}
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration) as exc:
        raise CourseCatalogError('Transferred credit requires valid original evidence and explicit unchanged-outcome equivalence') from exc


class CreditTransfer:
    def __init__(self, repository=None):
        self.repository = repository or EnrollmentRepository()
        self.journal = AttemptRepository()

    async def saved(self, user_id, request_id):
        from .upgrade_comparison import UpgradeUnavailable
        raw = await self.journal.records.find_one({'uuid': request_id, 'user_id': user_id})
        if raw is None or raw.get('transfer_request_json') is None:
            raise UpgradeUnavailable('The original transfer receipt is unavailable')
        request = CreditTransferRequest.model_validate(self.journal.payload(raw, 'transfer_request'))
        if (request.request_id != raw['uuid'] or request.target_enrollment_id != raw['enrollment_id']
                or request.module_id != raw['module_id']):
            raise CourseCatalogError('The saved transfer identity is inconsistent')
        return {'read_only': True, 'request': request.model_dump(mode='json'), 'state': raw['state'],
                'result': self.journal.payload(raw, 'result') if raw['state'] in ('applied', 'rejected', 'failed') else None}

    async def preview(self, user_id, target_id):
        repo = self.repository
        target = await repo.current(user_id)
        if (target is None or target.uuid != target_id or target.provenance != 'explicit_upgrade'
                or not target.source_enrollment_id or target.state not in ('active', 'completed')):
            raise EnrollmentConflict('Select the saved optional upgrade before reviewing credit transfer')
        source = await repo._enrollment(user_id, target.source_enrollment_id)
        target_package = repo.catalog.load(target.course_version)
        source_package = repo.catalog.load(source.course_version)
        source_progress = await repo.read_progress(user_id, source.uuid)
        target_progress = await repo.read_progress(user_id, target.uuid)
        plan = equivalence_plan(source_package, target_package, source_progress)
        modules = []
        for module in target_package.manifest.modules:
            rows = [row for row in plan['outcomes'] if row['module_id'] == module.id]
            completed = target_progress.modules.get(module.id, {}).get('completed') is True
            eligible = bool(rows) and all(row['status'] == 'eligible_for_transfer' for row in rows) and not completed
            modules.append({'module_id': module.id, 'title': module.title, 'outcome_count': len(rows),
                'eligible': eligible, 'completed': completed, 'xp_carried': module.base_xp if eligible else 0,
                'xp_earned': 0, 'reason': 'Already completed in this course.' if completed else (
                    'All required outcomes have verified equivalent original credit.' if eligible
                    else 'Complete this module’s assessment; not every required outcome has qualifying original evidence.')})
        if (progress_digest(source_progress) != progress_digest(await repo.read_progress(user_id, source.uuid))
                or progress_digest(target_progress) != progress_digest(await repo.read_progress(user_id, target.uuid))
                or (await repo.current(user_id)).uuid != target_id):
            raise EnrollmentConflict('Course work changed during review; refresh the transfer preview')
        result = {'source_enrollment_id': source.uuid, 'source_course_title': source_package.manifest.title,
            'target_enrollment_id': target.uuid, 'target_course_title': target_package.manifest.title,
            'source_manifest_sha256': source.manifest_sha256, 'target_manifest_sha256': target.manifest_sha256,
            'source_progress_sha256': progress_digest(source_progress), 'target_progress_sha256': progress_digest(target_progress),
            'equivalence_plan_sha256': plan['plan_sha256'], 'modules': modules, 'read_only': True,
            'credit_transferred': False, 'xp_earned': 0,
            'explanation': 'Transfer one eligible module at a time. Carried XP counts toward this course’s progress without earning another base reward. Your original course and certificate stay intact.'}
        result['preview_sha256'] = encode(result)[1]
        for module in modules:
            if module['eligible']:
                module['request'] = CreditTransferRequest(
                    request_id=uuid5(NAMESPACE_URL, f'vandalizer:credit-transfer:{user_id}:{target_id}:{module["module_id"]}:{result["preview_sha256"]}').hex,
                    source_enrollment_id=source.uuid, target_enrollment_id=target_id, module_id=module['module_id'],
                    preview_sha256=result['preview_sha256'],
                    consent='transfer_reviewed_module_credit_preserve_original_no_new_xp_reward').model_dump(mode='json')
        return result

    async def apply(self, user_id, body):
        from .runtime import CourseOperation, _operation
        from app.services.certification_service import complete_module
        request = CreditTransferRequest.model_validate(body)
        repo = self.repository
        async with repo.write_boundary(user_id, request.target_enrollment_id, operation='apply_credit_transfer') as progress:
            target = await repo._enrollment(user_id, request.target_enrollment_id)
            if target.source_enrollment_id != request.source_enrollment_id or target.provenance != 'explicit_upgrade':
                raise EnrollmentConflict('Credit transfer must use this optional upgrade’s original source')
            package = repo.catalog.load(target.course_version)
            operation = CourseOperation(user_id, package, progress, True)
            token = _operation.set(operation)
            try:
                existing = await self.journal.records.find_one({'uuid': request.request_id})
                if existing is None:
                    from .grading import load_rubric
                    load_rubric(package)
                    preview = await self.preview(user_id, target.uuid)
                    module = next((row for row in preview['modules'] if row['module_id'] == request.module_id), None)
                    if not module or module.get('request') != request.model_dump(mode='json'):
                        raise EnrollmentConflict('Use the exact request from a current eligible credit preview')
                    source = await repo._enrollment(user_id, request.source_enrollment_id)
                    source_package = repo.catalog.load(source.course_version)
                    original_progress = await repo.read_progress(user_id, source.uuid)
                    plan = equivalence_plan(source_package, package, original_progress)
                    rows = [row for row in plan['outcomes'] if row['module_id'] == request.module_id]
                    original = original_progress.modules[request.module_id]
                    saved = {key: deepcopy(original[key]) for key in ('completed', 'completed_at', 'completion_attempt_id', 'outcome_credit') if key in original}
                    proof = {'user_id': user_id, 'source_enrollment_id': source.uuid,
                        'source_version': source.course_version, 'source_manifest_sha256': source.manifest_sha256,
                        'source_module': saved, 'source_assessment_sha256': rows[0]['source_assessment_sha256'],
                        'policy_sha256': package.manifest.artifacts['credit-equivalence.json'],
                        'outcomes': rows, 'xp_carried': module['xp_carried'], 'xp_earned': 0}
                    validation = {'assessment_kind': 'transferred_outcome_validation',
                        'course_version': package.manifest.release_id, 'manifest_sha256': package.manifest_sha256,
                        'rubric_id': package.manifest.rubric_id, 'passed': True, 'stars': 1,
                        'credit_awarded': False, 'staff_review_required': False, 'credit_transfer': proof,
                        'checks': [{'id': row['outcome_id'], 'name': row['statement'], 'role': 'required',
                                    'passed': True, 'detail': row['reason']} for row in rows]}
                    attempt, _ = await self.journal.begin(operation, request.module_id, request.request_id,
                        transfer_request=request.model_dump(mode='json'))
                    await self.journal.graded(attempt, validation)
                else:
                    if self.journal.payload(existing, 'transfer_request') != request.model_dump(mode='json'):
                        raise EnrollmentConflict('The saved transfer belongs to a different reviewed request')
                return await complete_module(user_id, request.module_id, enrollment_id=target.uuid, request_id=request.request_id)
            finally:
                _operation.reset(token)
