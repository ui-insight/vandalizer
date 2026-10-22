"""The authored legacy review explains, per 5.0 outcome, why nothing transfers."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
from app.services.certification_versions.credit_equivalence import assessment_basis, equivalence_plan
from app.services.certification_versions.outcomes import package_outcomes
from tests import test_certification_credit_equivalence as fixtures

candidate = fixtures.candidate
SUPERVISION_OUTCOMES = {'workflow_design.approval_boundary', 'output_delivery.release_decision',
                        'batch_processing.targeted_recovery', 'foundations.verified_values', 'governance.capstone_supervision'}


def legacy_graduate():
    source = CourseCatalog(CATALOG_ROOT).load('legacy-2026-10-02.1', preview=True)
    modules = {m.id: {'completed': True, 'stars': 3, 'xp_earned': m.base_xp + 75, 'completed_at': '2025-03-01',
                      'self_assessment': {'q1': 'Original reflection'}} for m in source.manifest.modules}
    progress = SimpleNamespace(user_id='legacy-graduate', enrollment_id='a' * 32, course_version=source.manifest.release_id,
                               modules=modules, total_xp=sum(item['xp_earned'] for item in modules.values()))
    return source, progress


def test_every_new_outcome_requires_assessment_with_an_authored_reason(candidate):
    source, progress = legacy_graduate()
    plan = equivalence_plan(source, candidate.package, progress)
    contract = package_outcomes(candidate.package)
    assert plan['review_id'] == 'legacy-2026-10-02.1-to-5.0-outcomes.1'
    assert plan['eligible_outcome_count'] == 0 and plan['required_outcome_count'] == len(contract.required_outcomes()) == 33
    assert plan['xp_awarded'] == 0 and plan['credit_transferred'] is False and plan['can_apply'] is False
    rows = {row['outcome_id']: row for row in plan['outcomes']}
    assert all(row['status'] == 'requires_assessment' and row['rule_id'] is None
               and 'no_outcome_level_source_evidence' in row['reason_codes'] and len(row['reason']) > 80 for row in rows.values())
    for outcome in SUPERVISION_OUTCOMES:
        assert 'new_agent_supervision_competency' in rows[outcome]['reason_codes']
        assert 'matching module title does not establish it' in rows[outcome]['reason']
    reflection = [row for row in rows.values() if row['module_id'] in ('ai_literacy', 'process_mapping', 'workflow_design')]
    assert len(reflection) == 9 and all('source_assessed_reflection_only' in row['reason_codes'] for row in reflection)


def test_matching_titles_full_stars_and_xp_do_not_transfer_supervision_outcomes(candidate):
    source, progress = legacy_graduate()
    titles = {m.id: m.title for m in source.manifest.modules}
    shared = [m.id for m in candidate.package.manifest.modules if titles.get(m.id) == m.title]
    assert len(shared) >= 5  # Same module identities and titles exist in both courses.
    plan = equivalence_plan(source, candidate.package, progress)
    assert not [row for row in plan['outcomes'] if row['module_id'] in shared and row['status'] != 'requires_assessment']


def test_legacy_source_cannot_be_given_a_transfer_rule(candidate):
    source, progress = legacy_graduate()
    assert assessment_basis(source) is None
    policy = {'schema_version': 1, 'policy_id': 'title-match.1', 'source_version': source.manifest.release_id,
              'source_manifest_sha256': source.manifest_sha256, 'target_version': candidate.package.manifest.release_id,
              'assessment_basis_sha256': '0' * 64,
              'rules': [{'rule_id': 'title', 'outcome_id': 'governance.capstone_supervision',
                         'reason': 'Both modules are called Collaboration & Governance.'}]}
    target = fixtures.changed(candidate.package, assets={'credit-equivalence.json': policy})
    with pytest.raises(CourseCatalogError):
        equivalence_plan(source, target, progress)


@pytest.mark.parametrize('mutation', ['omit_outcome', 'grant_transfer', 'other_contract', 'short_reason', 'unknown_code'])
def test_incomplete_or_permissive_review_is_rejected(candidate, mutation):
    source, progress = legacy_graduate()
    review = candidate.package.json('legacy-equivalence-review.json')
    row = review['determinations'][0]
    if mutation == 'omit_outcome':
        review['determinations'].pop()
    elif mutation == 'grant_transfer':
        row['decision'] = 'eligible_for_transfer'
    elif mutation == 'other_contract':
        review['target_contract_id'] = 'another-contract'
    elif mutation == 'short_reason':
        row['reason'] = 'Titles differ.'
    else:
        row['reason_codes'] = ['title_matches']
    target = fixtures.changed(candidate.package, assets={'legacy-equivalence-review.json': review})
    with pytest.raises((CourseCatalogError, ValidationError)):
        equivalence_plan(source, target, progress)


def test_review_for_another_source_manifest_is_not_applied(candidate):
    source, progress = legacy_graduate()
    review = candidate.package.json('legacy-equivalence-review.json')
    review['source_manifest_sha256'] = 'f' * 64
    plan = equivalence_plan(source, fixtures.changed(candidate.package, assets={'legacy-equivalence-review.json': review}), progress)
    assert plan['review_id'] is None and plan['eligible_outcome_count'] == 0
    assert {row['reason'] for row in plan['outcomes']} == {'No authored equivalence rule applies to this source course and outcome.'}


def test_review_is_presentation_and_does_not_change_the_assessment_basis(candidate):
    review = candidate.package.json('legacy-equivalence-review.json')
    review['basis'] = review['basis'] + ' Editorial clarification only.'
    changed = fixtures.changed(candidate.package, assets={'legacy-equivalence-review.json': review})
    assert assessment_basis(changed) == assessment_basis(candidate.package)
