"""Read-only release comparison; never infer credit equivalence or rollout consent."""
import hashlib
import json
from datetime import datetime, timezone

from app.services.certificate_pdf import render_certificate_pdf

from .catalog import CourseCatalogError
from .grading import load_rubric
from .outcomes import package_outcomes
from .progression_policy import package_progression_policy


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def differences(before, after):
    return {
        'added': sorted(after.keys() - before.keys()),
        'removed': sorted(before.keys() - after.keys()),
        'changed': sorted(key for key in before.keys() & after.keys() if before[key] != after[key]),
        'unchanged': sorted(key for key in before.keys() & after.keys() if before[key] == after[key]),
    }


def lesson_index(package):
    return {lesson['id']: {'module_id': module_id, **lesson}
            for module_id, module in package.json('lessons.json').items()
            for lesson in module['lessons']}


def outcome_index(contract):
    return {outcome.id: outcome.model_dump(mode='json')
            for module in contract.modules for outcome in module.outcomes} if contract else {}


def cohort_summary(report):
    """Accept only the aggregate inventory format; omit arbitrary extra payloads."""
    if (not isinstance(report, dict) or type(report.get('schema_version')) is not int
            or report.get('schema_version') != 1):
        raise CourseCatalogError('Provide a schema-1 certification cohort inventory')
    def counts(value):
        if not isinstance(value, dict) or any(not isinstance(k, str) or type(v) is not int or v < 0
                                              for k, v in value.items()):
            raise CourseCatalogError('Cohort inventory counts must be nonnegative integers')
        return dict(sorted(value.items()))
    cohorts = counts(report.get('cohorts'))
    if set(cohorts) != {'unstarted_record', 'active', 'completed', 'inconsistent'}:
        raise CourseCatalogError('Cohort inventory must include all four cohort categories')
    users = report.get('users_with_certification_records')
    if type(users) is not int or users < 0 or sum(cohorts.values()) != users:
        raise CourseCatalogError('Cohort inventory totals do not reconcile')
    metadata = report.get('metadata_sha256')
    if not isinstance(metadata, str) or len(metadata) != 64 or any(c not in '0123456789abcdef' for c in metadata):
        raise CourseCatalogError('Cohort inventory must identify its inspected metadata')
    if report.get('consistency') != 'equal_metadata_in_two_reads_not_a_transactional_snapshot':
        raise CourseCatalogError('Cohort inventory must come from the double-read inspection')
    from datetime import datetime
    try:
        start = datetime.fromisoformat(report['observation_started_at'])
        finish = datetime.fromisoformat(report['observation_finished_at'])
        if start.tzinfo is None or finish.tzinfo is None or finish < start:
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise CourseCatalogError('Cohort inventory needs valid ordered observation timestamps') from exc
    return {'users_with_certification_records': users, 'cohorts': cohorts,
            'selected_course_counts': counts(report.get('selected_course_counts')),
            'flags_distinct_users': counts(report.get('flags_distinct_users')),
            'records_with_missing_owner': counts(report.get('records_with_missing_owner')),
            'metadata_sha256': metadata, 'consistency': report['consistency'],
            'observation_started_at': start.isoformat(), 'observation_finished_at': finish.isoformat(),
            'interpretation': 'Observed aggregates only; not current membership, integrity verification or permission to migrate.'}


def publication_impact(source, target, *, inventory=None):
    """Compare already verified packages without database access or mutations.

    This is preparation evidence. Compatibility of live models/tools and actual
    cohort reconciliation cannot be inferred from package hashes or test flags.
    """
    source_contract, target_contract = package_outcomes(source), package_outcomes(target)
    policy = package_progression_policy(target)
    before, after = lesson_index(source), lesson_index(target)
    lessons = differences(before, after)
    stale_revisions = [key for key in lessons['changed']
                       if after[key].get('revision', 1) <= before[key].get('revision', 1)]
    modules = differences({m.id: m.model_dump(mode='json') for m in source.manifest.modules},
                          {m.id: m.model_dump(mode='json') for m in target.manifest.modules})
    outcomes = differences(outcome_index(source_contract), outcome_index(target_contract))
    artifacts = differences(source.manifest.artifacts, target.manifest.artifacts)
    findings = []
    def block(code, action):
        findings.append({'code': code, 'action': action})
    if source.manifest.release_id == target.manifest.release_id:
        block('same_release_identity', 'Use a separate release identity for a material course change.')
    if source.entry.state == 'draft' or not source.entry.supported_for_existing:
        block('source_not_supported', 'Verify the original course is supported before offering an optional upgrade.')
    if target.entry.state != 'draft':
        block('target_not_draft', 'Prepare and review a new draft; do not rewrite a published release.')
    if stale_revisions:
        block('changed_lesson_revision_not_advanced', 'Advance revisions or use new identities for changed lessons: ' + ', '.join(stale_revisions))
    if target_contract and target_contract.state != 'release_candidate':
        block('outcomes_unverified', 'Finish required teaching, assessment and calibration evidence before marking outcomes verified.')
    if policy and policy.state != 'release_candidate':
        block('progression_policy_unreviewed', 'Review the pinned progression, credit, retry and accommodation policy.')
    try:
        load_rubric(target)
        runner = {'status': 'installed_runner_matches_pinned_package'}
    except CourseCatalogError as exc:
        runner = {'status': 'unavailable', 'reason': str(exc)}
        block('target_rubric_unavailable', 'Install and verify the exact target rubric: ' + str(exc))
    # Exercise the actual download renderer before a course can reach issuance.
    # Course metadata can be valid JSON yet exceed the fixed certificate areas.
    # Do not hash the PDF: ReportLab includes volatile document metadata.
    try:
        render_certificate_pdf(
            name='Synthetic Certificate Preflight', level='architect',
            certified_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            credential_id='CERT-PREFLIGHT', course_title=target.manifest.title,
            course_version=target.manifest.release_id,
            module_count=len(target.manifest.modules),
            credential_promise=target_contract.credential_promise if target_contract else None,
        )
        credential_rendering = {'status': 'course_metadata_rendered',
                                'basis': 'Actual PDF renderer with exact target title, version and promise; synthetic learner identity. Not a visual or arbitrary-learner-name acceptance check.'}
    except (ValueError, OSError) as exc:
        credential_rendering = {'status': 'unavailable', 'reason': str(exc)}
        block('target_certificate_unrenderable', 'Repair the target certificate metadata or renderer before publication: ' + str(exc))
    observed = cohort_summary(inventory) if inventory is not None else None
    if observed is None:
        block('cohort_inventory_missing', 'Attach the aggregate read-only inventory from the authorized deployment; synthetic cohorts do not establish actual rollout impact.')
    elif observed['cohorts']['inconsistent'] or any(observed['records_with_missing_owner'].values()):
        block('cohort_reconciliation_required', 'Reconcile or explicitly exclude inconsistent and unowned records before preparing recipient choices.')
    # No release-readiness claim follows from toggling manifest readiness flags.
    block('runtime_compatibility_evidence_required', 'Verify the complete course and grading calibration with the supported deployment models/tools; local hashes and stubbed providers are insufficient.')
    block('rollout_evidence_required', 'Review actual cohort preservation, accessibility/learner evidence and the authorized release/communication plan before rollout.')
    changed_paths = sorted(set(artifacts['added'] + artifacts['removed'] + artifacts['changed']))
    source_rules = source_contract.model_dump(mode='json', exclude={'modules'}) if source_contract else None
    target_rules = target_contract.model_dump(mode='json', exclude={'modules'}) if target_contract else None
    shared_outcome_rules_changed = source_rules != target_rules
    # Shared runtime/exercise changes can affect every outcome even when the
    # outcome's own text did not change. Keep this conservative review scope
    # distinct from the exact semantic contract diff above.
    shared_change = (shared_outcome_rules_changed
                     or bool(set(changed_paths) & {'rubric.py', 'exercises.json', 'progression-policy.json'})
                     or any(path.startswith('documents/') for path in changed_paths))
    changed_lessons = set(lessons['added'] + lessons['changed'] + lessons['removed'])
    required_review = set(outcomes['added'] + outcomes['changed'] + outcomes['removed'])
    if target_contract:
        for module in target_contract.modules:
            module_assets_changed = any(path.endswith('/' + module.module_id + '.json') for path in changed_paths)
            for outcome in module.outcomes:
                if shared_change or module_assets_changed or set(outcome.lesson_ids) & changed_lessons:
                    required_review.add(outcome.id)
    return {
        'schema_version': 1, 'kind': 'certification_publication_impact_preparation',
        'source': source.summary(), 'target': target.summary(),
        'modules': modules, 'lessons': {**lessons, 'changed_without_new_revision': stale_revisions},
        'outcomes': outcomes, 'artifacts': artifacts,
        'outcomes_requiring_compatibility_review': sorted(required_review),
        'shared_outcome_rules': {'changed': shared_outcome_rules_changed, 'source': source_rules, 'target': target_rules},
        'compatibility_review_basis': 'Changed outcome definitions, referenced lessons and module assets; shared credential promise, assistance, evidence rules, source, exercise, rubric or policy changes conservatively include every target outcome.',
        'grading_policy': {
            'source': {'rubric_id': source.manifest.rubric_id, 'maximum_stars': source.manifest.maximum_stars,
                       'star_bonus_xp': source.manifest.star_bonus_xp,
                       'required_outcome_count': len(outcome_index(source_contract))},
            'target': {'rubric_id': target.manifest.rubric_id, 'maximum_stars': target.manifest.maximum_stars,
                       'star_bonus_xp': target.manifest.star_bonus_xp,
                       'required_outcome_count': len(outcome_index(target_contract))},
        },
        'compatibility': {'asset_integrity': 'verified_by_catalog', 'target_rubric': runner,
                          'credential_rendering': credential_rendering,
                          'live_models_and_tools': 'not_verified_by_this_report',
                          'changed_lab_assets': [name for name in changed_paths if name.startswith(('documents/', 'decisions/', 'proposals/', 'assessments/')) or '-cases/' in name or name == 'exercises.json']},
        'cohorts': observed,
        'credit_mapping': {'automatic_transfer': False, 'transferred_outcomes': [],
                          'new_required_outcomes': sorted(outcome_index(target_contract)),
                          'basis': 'No equivalence is inferred from matching names, XP, lesson IDs or historical certificates.'},
        'learner_effects': {'current_enrollments_changed': False, 'earned_credentials_changed': False,
                           'selected_course_changed': False, 'default_changed': False,
                           'new_enrollment_created': False, 'notification_sent': False,
                           'upgrade_policy': 'optional_explicit_choice',
                           'note': 'Inspection and publication alone do not switch existing learners; default selection and authorized learner choice are separate.'},
        'blocking_findings': findings, 'publication_ready': False, 'rollout_authorized': False,
        'limits': ['This report does not execute models, inspect individual learner evidence, publish, select a default or migrate anyone.',
                   'A successful file/runner check is not proof of live practical compatibility or an 8/10 acceptance grade.',
                   'Observation timestamps are retained; no freshness or transactional snapshot claim is inferred.'],
    }


def inspect_catalogs(source_catalog, source_id, target_catalog, target_id, *, inventory=None):
    source_bytes = (source_catalog.root / 'registry.json').read_bytes()
    target_bytes = (target_catalog.root / 'registry.json').read_bytes()
    source_registry, target_registry = source_catalog.registry(), target_catalog.registry()
    source = source_catalog.load(source_id, preview=True)
    target = target_catalog.load(target_id, preview=True)
    report = publication_impact(source, target, inventory=inventory)
    if (source_registry != source_catalog.registry() or target_registry != target_catalog.registry()
            or source_bytes != (source_catalog.root / 'registry.json').read_bytes()
            or target_bytes != (target_catalog.root / 'registry.json').read_bytes()):
        raise CourseCatalogError('Registry changed during inspection; rerun the read-only comparison')
    report['registry_context'] = {
        'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
        'target_sha256': hashlib.sha256(target_bytes).hexdigest(), 'hash_basis': 'exact_registry_file_bytes',
        'source_new_enrollment_default': source_registry.get('new_enrollment_default'),
        'target_new_enrollment_default': target_registry.get('new_enrollment_default'),
        'source_legacy_continuation': source_registry.get('legacy_continuation'),
        'target_legacy_continuation': target_registry.get('legacy_continuation'),
    }
    report['report_sha256'] = digest(report)
    return report


def require_publication_impact(catalog, release_id, *, report, source_catalog=None, inventory=None):
    """Bind publication to a fresh comparison; report edits cannot clear gates.

    The current inspector cannot certify the deferred runtime/rollout evidence.
    Consequently competency publication remains closed even for a package with
    readiness flags. Adding an evidence verifier requires a separate reviewed
    implementation, not a CLI force flag or a manually edited report.
    """
    if not isinstance(report, dict):
        raise CourseCatalogError('Publication requires the reviewed publication impact report')
    try:
        body = {key: value for key, value in report.items() if key != 'report_sha256'}
        if report.get('report_sha256') != digest(body):
            raise ValueError('digest')
        source_id = report['source']['course_version']
        if not isinstance(source_id, str) or report['target']['course_version'] != release_id:
            raise ValueError('identity')
    except (KeyError, TypeError, ValueError) as exc:
        raise CourseCatalogError('Publication impact report integrity or release identity is invalid') from exc
    current = inspect_catalogs(source_catalog or catalog, source_id, catalog, release_id, inventory=inventory)
    if report['report_sha256'] != current['report_sha256']:
        raise CourseCatalogError('Publication impact changed; regenerate and review the exact current report')
    if current['blocking_findings'] or not current['publication_ready']:
        reasons = '; '.join(f"{item['code']}: {item['action']}" for item in current['blocking_findings'])
        raise CourseCatalogError('Publication blocked by impact review: ' + (reasons or 'release evidence is incomplete'))
