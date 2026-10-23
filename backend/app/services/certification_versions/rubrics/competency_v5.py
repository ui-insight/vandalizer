"""All-required-outcome validation from explicitly selected original receipts.

This runner never dispatches a model or writes credit. Installing it does not
publish a course: a supported package must pin these bytes, verified outcomes
and a single completion threshold with no legacy star enrichment.
"""
from pathlib import Path
import re

from ..attempts import encode, normalize_assessment_selection
from ..catalog import CourseCatalogError
from ..outcomes import package_outcomes

RUBRIC_ID = 'v5.0-competency-draft.1'


def verify_package(package):
    from ..progression_policy import package_progression_policy
    try:
        package_progression_policy(package)
    except ValueError as exc:
        raise CourseCatalogError('The pinned progression policy does not match the credit course') from exc
    contract = package_outcomes(package)
    if contract is None or contract.state != 'release_candidate' or contract.rubric_id != RUBRIC_ID:
        raise CourseCatalogError('Outcome credit requires a verified release-candidate contract')
    if package.read('rubric.py') != Path(__file__).read_bytes():
        raise CourseCatalogError('Installed outcome rubric differs from the pinned course package')
    if package.manifest.maximum_stars != 1 or package.manifest.star_bonus_xp != 0:
        raise CourseCatalogError('Required outcomes use one completion threshold without star enrichment')
    return contract


async def validate_module(user_id, module_id, *, assessment_selection=None):
    from ..grading import pinned_package, pinned_progress
    from ..module_readiness import ModuleReadiness
    from ..review_delivery import SavedReviewUnavailable
    from ..enrollments import EnrollmentConflict
    package, progress = pinned_package(), pinned_progress(user_id)
    contract = verify_package(package)
    selected = normalize_assessment_selection(assessment_selection) or {}
    if not progress.enrollment_id:
        raise CourseCatalogError('Selected outcomes require an explicit enrollment')
    required = next((module for module in contract.modules if module.module_id == module_id), None)
    if required is None:
        raise CourseCatalogError('The selected module has no competency outcomes')
    try:
        snapshot = await ModuleReadiness().preview(user_id, progress.enrollment_id, module_id, **selected)
    except SavedReviewUnavailable as exc:
        raise EnrollmentConflict('The selected assessment is unavailable for this enrollment and module') from exc
    if (snapshot['enrollment_id'] != progress.enrollment_id
            or snapshot['course_version'] != package.manifest.release_id
            or snapshot['manifest_sha256'] != package.manifest_sha256
            or snapshot['module_id'] != module_id or snapshot['rubric_id'] != contract.rubric_id
            or snapshot['assessment_kind'] != 'module_readiness_draft'
            or snapshot['contract_sha256'] != encode(contract.model_dump(mode='json'))[1]):
        raise CourseCatalogError('The selected evidence no longer matches the pinned course')
    original = {outcome.id: outcome for outcome in required.outcomes}
    if (len(snapshot['outcomes']) != len(original)
            or {outcome['outcome_id'] for outcome in snapshot['outcomes']} != set(original)):
        raise CourseCatalogError('The selected result does not cover every required outcome')
    for outcome in snapshot['outcomes']:
        authored = original[outcome['outcome_id']]
        reference = selected.get('scenario_attempt_id' if authored.method == 'scenario_choice' else 'review_attempt_id')
        if (outcome['method'] != authored.method or outcome['statement'] != authored.statement
                or outcome['attempt_id'] != reference or (outcome['state'] != 'selection_required' and reference is None)):
            raise CourseCatalogError('An outcome result differs from its selected original evidence')
    receipts = snapshot['selected_receipts']
    expected_receipts = {('automatic_review' if key == 'review_attempt_id' else 'scenario_recognition', value)
                         for key, value in selected.items()}
    if (len(receipts) != len(expected_receipts)
            or {(item['kind'], item['attempt_id']) for item in receipts} != expected_receipts
            or any(not re.fullmatch(r'[a-f0-9]{64}', item['record_sha256']) for item in receipts)):
        raise CourseCatalogError('Original selected assessment receipts are incomplete')
    if any(outcome['state'] in ('assessment_pending', 'grading_unavailable') for outcome in snapshot['outcomes']):
        raise CourseCatalogError('Selected evidence has no available final assessment; wait or resolve its technical failure before completing')
    details = {'supported': 'Supported by the explicitly selected saved evidence.',
               'revision_required': 'Read the original saved feedback and address the required revision.',
               'selection_required': 'Explicitly select the original assessment required for this outcome.'}
    if any(outcome['state'] not in details for outcome in snapshot['outcomes']):
        raise CourseCatalogError('The selected assessment has an unsupported outcome state')
    if any(not isinstance(item['result_sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', item['result_sha256']) for item in receipts):
        raise CourseCatalogError('An original selected final result is unavailable')
    checks = [{'id': outcome['outcome_id'], 'name': outcome['statement'], 'role': 'required',
               'passed': outcome['state'] == 'supported', 'detail': details[outcome['state']]}
              for outcome in snapshot['outcomes']]
    supported = all(check['passed'] for check in checks)
    if (snapshot['all_required_outcomes_supported'] is not supported
            or (snapshot['status'] == 'requirements_supported') is not supported
            or snapshot['credit_awarded'] is not False or snapshot['module_completion_eligible'] is not False
            or snapshot['staff_review_required'] is not False or snapshot['read_only'] is not True):
        raise CourseCatalogError('The selected assessment summary is inconsistent')
    module = next(item for item in package.manifest.modules if item.id == module_id)
    for prerequisite in module.prerequisites:
        checks.append({'id': 'prerequisite:' + prerequisite, 'name': 'Required earlier module: ' + prerequisite,
                       'role': 'required', 'passed': progress.modules.get(prerequisite, {}).get('completed') is True,
                       'detail': 'Completion must be recorded in this same enrollment.'})
    passed = all(check['passed'] for check in checks)
    return {'passed': passed, 'stars': 1 if passed else 0, 'checks': checks,
            'assessment_kind': 'selected_outcome_validation', 'assessment_selection': selected,
            'assessment_snapshot': snapshot, 'assessment_snapshot_sha256': encode(snapshot)[1],
            'credit_awarded': False, 'staff_review_required': False}
