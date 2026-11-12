"""Transferred credit never earns base XP or a credential twice; totals stay explainable."""
from bson import ObjectId

from app.models.certification import CertificationProgress
from app.services.certification_versions.credentials import CredentialRepository
from app.services.certification_versions.reward_ledger import load_user_rewards
from tests import test_certification_credit_equivalence as fixtures
from tests.integration import test_certification_credit_transfer as transfer
from tests.integration import test_certification_enrollments as persisted

repo = persisted.repo
candidate = fixtures.candidate
pytestmark = persisted.pytestmark


async def test_full_transfer_counts_each_base_reward_once_and_issues_one_new_credential(repo, candidate, monkeypatch):
    f = await transfer.setup(repo, candidate, monkeypatch)
    base = {module.id: module.base_xp for module in f.package.manifest.modules}
    await repo.progress.update_one({'_id': ObjectId(f.source.progress_id)},
        {'$set': {f'modules.{mid}.xp_earned': xp for mid, xp in base.items()}})
    before = await load_user_rewards(repo, f.user)
    assert before['lifetime_earned_xp'] == sum(base.values()) and before['explained'] is True
    for module_id in base:
        request = await transfer.request_for(f, module_id)
        await f.service.apply(f.user, request)
        await f.service.apply(f.user, request)  # A replay returns the original receipt.
    after = await load_user_rewards(repo, f.user)
    source, target = after['enrollments']
    assert source == before['enrollments'][0]
    assert target['earned_xp'] == target['base_xp_earned'] == target['star_bonus_xp'] == 0
    assert target['carried_xp'] == target['recorded_total_xp'] == sum(base.values())
    assert all(row['credit_origin'] == 'transferred' and row['xp_carried'] == base[row['module_id']] for row in target['modules'])
    assert after['lifetime_earned_xp'] == before['lifetime_earned_xp'] == sum(base.values())
    assert after['carried_xp_shown_in_target_courses'] == sum(base.values())
    assert after['credentials'] == [f.credential.credential_id, target['credential_id']]
    assert after['duplicate_credentials'] is False and after['explained'] is True
    assert await CredentialRepository().records.count_documents({'user_id': f.user}) == 2


async def test_legacy_stars_stay_legacy_and_unexplained_totals_are_reported_not_rewritten(repo):
    legacy = CertificationProgress(user_id='legacy-stars', total_xp=50 + 75 + 100 + 25 + 40, modules={
        'ai_literacy': {'completed': True, 'stars': 3, 'xp_earned': 125, 'completed_at': '2025-02-01'},
        'foundations': {'completed': True, 'stars': 1, 'xp_earned': 125},
        'process_mapping': {'completed': False, 'self_assessment': {'q': 'Unfinished'}},
    })
    await legacy.insert()
    source = await repo.ensure_initial('legacy-stars')
    raw = await repo.progress.find_one({'_id': legacy.id})
    summary = await load_user_rewards(repo, 'legacy-stars')
    (row,) = summary['enrollments']
    assert row['provenance'] == 'legacy_version_unknown' and row['enrollment_id'] == source.uuid
    assert row['stars'] == 4 and row['base_xp_earned'] == 150 and row['star_bonus_xp'] == 100
    assert {m['module_id']: m['credit_origin'] for m in row['modules'] if m['completed']} == {
        'ai_literacy': 'legacy_module_credit', 'foundations': 'legacy_module_credit'}
    assert row['unexplained_xp'] == 40 and row['explained'] is False and summary['explained'] is False
    assert await repo.progress.find_one({'_id': legacy.id}) == raw
