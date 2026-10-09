"""Freeze validated original outcomes for a module's earned-credit record."""
import re

from .attempts import AttemptRepository, encode, normalize_assessment_selection
from .catalog import CourseCatalogError
from .enrollments import EnrollmentConflict
from .outcomes import package_outcomes


def verified_credit_snapshot(package, progress, module_id, credit, *, expected_attempt_id, _transfer_depth=0):
    """Validate an internal journal snapshot, never a client-supplied verdict."""
    try:
        if (not isinstance(credit, dict) or credit['attempt_id'] != expected_attempt_id
                or not re.fullmatch(r'[a-f0-9]{32}', credit['attempt_id'])):
            raise ValueError('Invalid completion identity')
        validation = AttemptRepository.payload(credit, 'validation')
        if validation.get('assessment_kind') == 'transferred_outcome_validation':
            from .credit_transfer import verify_transfer_credit
            return verify_transfer_credit(package, progress, module_id, credit, depth=_transfer_depth)
        contract = package_outcomes(package)
        required = next(module for module in contract.modules if module.module_id == module_id)
        authored = {item.id: item for item in required.outcomes}
        snapshot = validation['assessment_snapshot']
        selected = normalize_assessment_selection(validation['assessment_selection'])
        if (not selected or AttemptRepository.assessment_selection(credit) != selected
                or validation['passed'] is not True or validation['stars'] != 1
                or validation['assessment_kind'] != 'selected_outcome_validation'
                or validation['course_version'] != package.manifest.release_id
                or validation['manifest_sha256'] != package.manifest_sha256
                or validation['rubric_id'] != contract.rubric_id
                or validation['credit_awarded'] is not False or validation['staff_review_required'] is not False
                or encode(snapshot)[1] != validation['assessment_snapshot_sha256']):
            raise ValueError('Invalid original outcome validation')
        if (snapshot['enrollment_id'] != progress.enrollment_id or snapshot['module_id'] != module_id
                or snapshot['course_version'] != package.manifest.release_id
                or snapshot['manifest_sha256'] != package.manifest_sha256
                or snapshot['rubric_id'] != contract.rubric_id
                or snapshot['contract_sha256'] != encode(contract.model_dump(mode='json'))[1]
                or snapshot['assessment_kind'] != 'module_readiness_draft'
                or snapshot['status'] != 'requirements_supported' or snapshot['all_required_outcomes_supported'] is not True
                or snapshot['read_only'] is not True or snapshot['credit_awarded'] is not False
                or snapshot['module_completion_eligible'] is not False or snapshot['staff_review_required'] is not False):
            raise ValueError('Invalid original outcome snapshot')
        if (len(snapshot['outcomes']) != len(authored)
                or {item['outcome_id'] for item in snapshot['outcomes']} != set(authored)):
            raise ValueError('Incomplete required outcomes')
        for item in snapshot['outcomes']:
            outcome = authored[item['outcome_id']]
            reference = selected.get('scenario_attempt_id' if outcome.method == 'scenario_choice' else 'review_attempt_id')
            if (not reference or item['attempt_id'] != reference or item['state'] != 'supported'
                    or item['method'] != outcome.method or item['statement'] != outcome.statement):
                raise ValueError('Unsupported original outcome')
        expected_receipts = {('automatic_review' if key == 'review_attempt_id' else 'scenario_recognition', value)
                             for key, value in selected.items()}
        receipts = snapshot['selected_receipts']
        if (len(receipts) != len(expected_receipts)
                or {(item['kind'], item['attempt_id']) for item in receipts} != expected_receipts
                or any(not re.fullmatch(r'[a-f0-9]{64}', item[key]) for item in receipts
                       for key in ('record_sha256', 'result_sha256'))):
            raise ValueError('Incomplete original receipt identities')
        module = next(item for item in package.manifest.modules if item.id == module_id)
        required_checks = set(authored) | {'prerequisite:' + item for item in module.prerequisites}
        checks = validation['checks']
        if (len(checks) != len(required_checks) or {item['id'] for item in checks} != required_checks
                or any(item['passed'] is not True or item['role'] != 'required' for item in checks)):
            raise ValueError('Incomplete required validation checks')
        return snapshot
    except CourseCatalogError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError, StopIteration, EnrollmentConflict) as exc:
        raise CourseCatalogError('Competency credit requires complete original outcome evidence') from exc


def freeze_credit(package, progress, module_id, attempt):
    credit = {'attempt_id': attempt['uuid'], 'validation_json': attempt['validation_json'],
              'validation_sha256': attempt['validation_sha256'],
              'assessment_selection_json': attempt.get('assessment_selection_json'),
              'assessment_selection_sha256': attempt.get('assessment_selection_sha256')}
    if attempt.get('transfer_request_json') is not None:
        credit.update(transfer_request_json=attempt['transfer_request_json'], transfer_request_sha256=attempt['transfer_request_sha256'])
    verified_credit_snapshot(package, progress, module_id, credit, expected_attempt_id=attempt['uuid'])
    return credit


def repeats_earned_outcomes(package, progress, module_id, credit):
    """A new request receipt need not replace credit for the same saved work."""
    module = progress.modules.get(module_id, {})
    previous = module.get('outcome_credit')
    if not module.get('completed') or previous is None:
        return False
    original = verified_credit_snapshot(package, progress, module_id, previous,
                                        expected_attempt_id=module.get('completion_attempt_id'))
    current = verified_credit_snapshot(package, progress, module_id, credit,
                                       expected_attempt_id=credit['attempt_id'])
    if AttemptRepository.assessment_selection(previous) != AttemptRepository.assessment_selection(credit):
        return False
    def receipts(snapshot):
        return sorted((row['kind'], row['attempt_id'], row['record_sha256'], row['result_sha256'])
                      for row in snapshot['selected_receipts'])
    if receipts(original) != receipts(current):
        raise CourseCatalogError('Saved assessment evidence changed after its original completion')
    return True
