"""Impact reports expose gaps and never treat synthetic readiness flags as proof."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
from app.services.certification_versions.release_impact import cohort_summary, digest, publication_impact
from tests import test_certification_outcome_rubric as rubric_fixtures

candidate = rubric_fixtures.candidate

spec = importlib.util.spec_from_file_location('impact_script', Path(__file__).resolve().parents[2] / 'scripts/inspect_certification_release_impact.py')
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


def inventory():
    return {'schema_version': 1, 'users_with_certification_records': 3,
            'cohorts': {'unstarted_record': 1, 'active': 1, 'completed': 1, 'inconsistent': 0},
            'selected_course_counts': {'legacy_unversioned': 3}, 'flags_distinct_users': {},
            'records_with_missing_owner': {}, 'metadata_sha256': 'a' * 64,
            'observation_started_at': '2026-10-07T12:00:00+00:00',
            'observation_finished_at': '2026-10-07T12:00:01+00:00',
            'consistency': 'equal_metadata_in_two_reads_not_a_transactional_snapshot'}


def source():
    return CourseCatalog(CATALOG_ROOT).load('legacy-2026-10-02.1', preview=True)


def test_complete_comparison_does_not_infer_transfer_or_runtime_readiness(candidate):
    original = source()
    observed = inventory()
    observed['private_extra'] = {'email': 'must-not-appear@example.test'}
    before = deepcopy(observed)
    result = publication_impact(original, candidate.package, inventory=observed)
    assert len(result['outcomes']['added']) == 33
    assert len(result['outcomes_requiring_compatibility_review']) == 33
    assert len(result['lessons']['changed']) == 74
    assert result['lessons']['changed_without_new_revision'] == []
    assert result['compatibility']['target_rubric']['status'] == 'installed_runner_matches_pinned_package'
    assert result['compatibility']['credential_rendering']['status'] == 'course_metadata_rendered'
    assert result['compatibility']['changed_lab_assets']
    assert result['grading_policy']['source']['maximum_stars'] == 3
    assert result['grading_policy']['target']['maximum_stars'] == 1
    assert result['credit_mapping']['transferred_outcomes'] == []
    assert len(result['credit_mapping']['new_required_outcomes']) == 33
    assert result['publication_ready'] is result['rollout_authorized'] is False
    codes = {item['code'] for item in result['blocking_findings']}
    assert {'source_not_supported', 'runtime_compatibility_evidence_required', 'rollout_evidence_required'} <= codes
    assert 'cohort_inventory_missing' not in codes
    assert 'private_extra' not in json.dumps(result) and 'must-not-appear' not in json.dumps(result)
    assert observed == before
    assert all(result['learner_effects'][key] is False for key in
        ('current_enrollments_changed', 'earned_credentials_changed', 'selected_course_changed',
         'default_changed', 'new_enrollment_created', 'notification_sent'))


def test_changed_content_with_reused_revision_is_visible(candidate):
    lessons = json.loads((candidate.folder / 'lessons.json').read_text())
    lesson = lessons['foundations']['lessons'][0]
    lesson['revision'] = 1
    (candidate.folder / 'lessons.json').write_text(json.dumps(lessons))
    # Keep both authored renderers coherent while testing revision policy.
    panel = json.loads((candidate.folder / 'panel-modules.json').read_text())
    for module in panel:
        for item in module['lessons']:
            if item['id'] == lesson['id']:
                item['revision'] = 1
    (candidate.folder / 'panel-modules.json').write_text(json.dumps(panel))
    result = publication_impact(source(), candidate.reload())
    assert lesson['id'] in result['lessons']['changed_without_new_revision']
    assert 'changed_lesson_revision_not_advanced' in {i['code'] for i in result['blocking_findings']}


@pytest.mark.parametrize('field,reason', [
    ('credential_promise', 'Credential promise exceeds'),
    ('title', 'Course title exceeds'),
])
def test_valid_package_with_unrenderable_certificate_is_blocked(candidate, field, reason):
    if field == 'credential_promise':
        contract = json.loads((candidate.folder / 'outcomes.json').read_text())
        contract[field] = 'This authored promise cannot fit in the certificate. ' * 100
        (candidate.folder / 'outcomes.json').write_text(json.dumps(contract))
        target = candidate.reload()
    else:
        target = candidate.reload(lambda manifest: manifest.update(title='A long course title ' * 100))
    before = (candidate.folder.parent / 'registry.json').read_bytes()
    result = publication_impact(source(), target)
    rendering = result['compatibility']['credential_rendering']
    assert rendering['status'] == 'unavailable'
    assert reason in rendering['reason']
    assert 'target_certificate_unrenderable' in {i['code'] for i in result['blocking_findings']}
    assert result['publication_ready'] is False
    assert (candidate.folder.parent / 'registry.json').read_bytes() == before


def test_legacy_package_can_preflight_without_inventing_a_scope():
    package = source()
    result = publication_impact(package, package)
    assert result['compatibility']['credential_rendering']['status'] == 'course_metadata_rendered'
    assert result['shared_outcome_rules']['target'] is None


def test_same_outcome_text_does_not_hide_changed_lab_requirements(candidate):
    original = candidate.package
    exercises = json.loads((candidate.folder / 'exercises.json').read_text())
    exercises['foundations']['overview'] += ' A revised lab needs compatibility review.'
    (candidate.folder / 'exercises.json').write_text(json.dumps(exercises))
    result = publication_impact(original, candidate.reload())
    assert len(result['outcomes']['unchanged']) == 33
    assert len(result['outcomes_requiring_compatibility_review']) == 33


@pytest.mark.parametrize('field', ['credential_promise', 'agent_assistance', 'exclusions', 'evidence_policy'])
def test_shared_scope_and_evidence_rules_require_review_without_changed_outcome_rows(candidate, field):
    original = candidate.package
    contract = json.loads((candidate.folder / 'outcomes.json').read_text())
    if isinstance(contract[field], list):
        contract[field].append('A changed shared requirement needs compatibility review.')
    else:
        contract[field] += ' A changed shared requirement needs compatibility review.'
    (candidate.folder / 'outcomes.json').write_text(json.dumps(contract))
    result = publication_impact(original, candidate.reload())
    assert len(result['outcomes']['unchanged']) == 33
    assert result['outcomes']['changed'] == []
    assert len(result['outcomes_requiring_compatibility_review']) == 33
    assert result['shared_outcome_rules']['changed'] is True
    assert result['shared_outcome_rules']['source'][field] != result['shared_outcome_rules']['target'][field]


def test_module_only_outcome_edit_does_not_change_the_shared_scope(candidate):
    original = candidate.package
    contract = json.loads((candidate.folder / 'outcomes.json').read_text())
    changed = contract['modules'][0]['outcomes'][0]
    changed['statement'] += ' A revised outcome-specific requirement.'
    (candidate.folder / 'outcomes.json').write_text(json.dumps(contract))
    result = publication_impact(original, candidate.reload())
    assert result['outcomes']['changed'] == [changed['id']]
    assert result['outcomes_requiring_compatibility_review'] == [changed['id']]
    assert result['shared_outcome_rules']['changed'] is False


def test_changed_source_with_stale_case_binding_is_rejected_before_inspection(candidate):
    document = candidate.folder / 'documents/nsf-proposal-alpine-ecology.pdf'
    document.write_bytes(document.read_bytes() + b'\n% synthetic changed source revision\n')
    with pytest.raises(CourseCatalogError):
        candidate.reload()  # A stale source binding fails before impact review.


def test_new_source_asset_requires_conservative_compatibility_review(candidate):
    original = candidate.package
    name = 'documents/synthetic-addendum.pdf'
    (candidate.folder / name).write_bytes(original.read('documents/nsf-proposal-alpine-ecology.pdf'))
    target = candidate.reload(lambda manifest: manifest['artifacts'].update({name: '0' * 64}))
    result = publication_impact(original, target)
    assert result['artifacts']['added'] == [name]
    assert result['artifacts']['changed'] == []
    assert len(result['outcomes']['unchanged']) == 33
    assert len(result['outcomes_requiring_compatibility_review']) == 33


@pytest.mark.parametrize('change', ['negative', 'boolean', 'missing_cohort', 'total', 'digest', 'missing_time', 'naive_time', 'reversed_time', 'single_read'])
def test_malformed_inventory_is_not_silently_reported_as_safe(change):
    report = inventory()
    if change == 'negative':
        report['flags_distinct_users']['unknown'] = -1
    elif change == 'boolean':
        report['cohorts']['active'] = True
    elif change == 'missing_cohort':
        del report['cohorts']['inconsistent']
    elif change == 'total':
        report['users_with_certification_records'] = 4
    elif change == 'digest':
        report['metadata_sha256'] = 'missing'
    elif change == 'missing_time':
        del report['observation_started_at']
    elif change == 'naive_time':
        report['observation_started_at'] = '2026-10-07T12:00:00'
    elif change == 'reversed_time':
        report['observation_started_at'] = '2026-10-08T12:00:00+00:00'
    else:
        report['consistency'] = 'one_read'
    with pytest.raises(CourseCatalogError):
        cohort_summary(report)


def test_inconsistent_cohorts_and_missing_inventory_are_explicit(candidate):
    missing = publication_impact(source(), candidate.package)
    assert missing['cohorts'] is None
    assert 'cohort_inventory_missing' in {i['code'] for i in missing['blocking_findings']}
    observed = inventory()
    observed['cohorts'].update(active=0, inconsistent=1)
    observed['records_with_missing_owner'] = {'attempts': 1}
    result = publication_impact(source(), candidate.package, inventory=observed)
    assert 'cohort_reconciliation_required' in {i['code'] for i in result['blocking_findings']}


def test_read_only_script_binds_exact_packages_and_registries(candidate):
    target = CourseCatalog(candidate.folder.parent)
    paths = [CATALOG_ROOT / 'registry.json', candidate.folder.parent / 'registry.json', candidate.folder / 'manifest.json']
    before = [p.read_bytes() for p in paths]
    result = script.inspect(CourseCatalog(CATALOG_ROOT), 'legacy-2026-10-02.1', target, candidate.package.manifest.release_id)
    assert result['target']['manifest_sha256'] == candidate.package.manifest_sha256
    assert result['registry_context']['source_sha256'] == hashlib.sha256(before[0]).hexdigest()
    assert result['registry_context']['target_sha256'] == hashlib.sha256(before[1]).hexdigest()
    report_hash = result.pop('report_sha256')
    assert report_hash == digest(result)
    assert before == [p.read_bytes() for p in paths]


def test_registry_change_during_inspection_is_rejected(candidate, monkeypatch):
    target = CourseCatalog(candidate.folder.parent)
    registry = target.registry()
    calls = 0
    original = target.registry
    def changing():
        nonlocal calls
        calls += 1
        return original() if calls < 3 else {**registry, 'transition_policy': 'changed'}
    monkeypatch.setattr(target, 'registry', changing)
    with pytest.raises(CourseCatalogError, match='changed during inspection'):
        script.inspect(CourseCatalog(CATALOG_ROOT), 'legacy-2026-10-02.1', target, candidate.package.manifest.release_id)


@pytest.mark.parametrize('field', ['title', 'content', 'objective', 'variant', 'diagram', 'knowledge_check'])
@pytest.mark.parametrize('advance_revision', [False, True])
def test_every_teaching_change_requires_a_new_revision_even_when_chat_and_panel_agree(candidate, field, advance_revision):
    original = candidate.package
    original_bytes = original.read('lessons.json')
    lessons = original.json('lessons.json')
    panel = original.json('panel-modules.json')
    module_id, lesson = next((mid, item) for mid, module in lessons.items() for item in module['lessons']
                             if field != 'knowledge_check' or item.get('knowledge_check'))
    if field == 'knowledge_check':
        value = deepcopy(lesson[field])
        value['options'][0]['explanation'] += ' Revised practice feedback.'
    elif field == 'variant':
        value = 'insight' if lesson[field] != 'insight' else 'concept'
    elif field == 'diagram':
        value = 'flowchart LR\n  Evidence --> Verification'
    else:
        value = lesson.get(field, '') + ' Revised teaching.'
    lesson[field] = value
    if advance_revision:
        lesson['revision'] += 1
    target_panel = next(item for module in panel for item in module['lessons'] if item['id'] == lesson['id'])
    target_panel['knowledgeCheck' if field == 'knowledge_check' else field] = deepcopy(value)
    target_panel['revision'] = lesson['revision']
    for filename, content in (('lessons.json', lessons), ('panel-modules.json', panel)):
        (candidate.folder / filename).write_text(json.dumps(content))
    result = publication_impact(original, candidate.reload())
    assert result['lessons']['changed'] == [lesson['id']]
    assert result['lessons']['changed_without_new_revision'] == ([] if advance_revision else [lesson['id']])
    assert ('changed_lesson_revision_not_advanced' in {row['code'] for row in result['blocking_findings']}) is not advance_revision
    assert original.read('lessons.json') == original_bytes


def test_pure_lesson_reordering_retains_ids_and_does_not_require_rewriting_lesson_revisions(candidate):
    original = candidate.package
    lessons = original.json('lessons.json')
    panel = original.json('panel-modules.json')
    module_id = original.manifest.modules[0].id
    lessons[module_id]['lessons'].reverse()
    next(module for module in panel if module['id'] == module_id)['lessons'].reverse()
    for filename, content in (('lessons.json', lessons), ('panel-modules.json', panel)):
        (candidate.folder / filename).write_text(json.dumps(content))
    def reorder(manifest):
        next(module for module in manifest['modules'] if module['id'] == module_id)['lesson_ids'].reverse()
    result = publication_impact(original, candidate.reload(reorder))
    assert result['lessons']['changed'] == result['lessons']['changed_without_new_revision'] == []
    assert len(result['lessons']['unchanged']) == 74
    assert module_id in result['modules']['changed']
