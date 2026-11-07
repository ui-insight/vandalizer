"""A legacy graduate previews the authored 5.0 package: bridge offered, nothing transferred."""
import json
import shutil

from bson import ObjectId

from app.models.certification import CertificationProgress
from app.services.certification_versions.transition_preview import TransitionPreview
from tests.integration import test_certification_enrollments as persisted
from tests.test_certification_v5_preview import preview

repo = persisted.repo
pytestmark = persisted.pytestmark
TARGET = 'v5-legacy-preview-qa.1'


def install_authored_package(repo, tmp_path):
    root = preview.assemble(tmp_path / 'assembled', TARGET)
    shutil.copytree(root / TARGET, repo.catalog.root / TARGET)
    registry_path = repo.catalog.root / 'registry.json'
    registry = json.loads(registry_path.read_text())
    registry['releases'][TARGET] = json.loads((root / 'registry.json').read_text())['releases'][TARGET]
    registry_path.write_text(json.dumps(registry))


async def test_legacy_graduate_sees_ordered_bridge_and_per_outcome_reasons_without_any_change(repo, tmp_path):
    modules = {m.id: {'completed': True, 'stars': 3, 'xp_earned': m.base_xp + 75, 'completed_at': '2025-04-02',
                      'self_assessment': {'q1': 'Original reflection'}}
               for m in repo.catalog.load(persisted.VERSION).manifest.modules}
    legacy = CertificationProgress(user_id='legacy-graduate', modules=modules, certified=True,
                                   total_xp=sum(item['xp_earned'] for item in modules.values()), level='architect')
    await legacy.insert()
    source = await repo.ensure_initial('legacy-graduate')
    install_authored_package(repo, tmp_path)
    before = await repo.progress.find_one({'_id': ObjectId(source.progress_id)})
    result = await TransitionPreview(repo).inspect(source.user_id, source.uuid, TARGET)
    bridge = result['target']['bridge_path']
    assert [stage['id'] for stage in bridge['stages']] == ['scope', 'verify', 'recover_deliver', 'capstone']
    assert bridge['stages'][-1]['modules'] == [{'module_id': 'governance', 'title': bridge['stages'][-1]['modules'][0]['title'],
                                                'required_outcomes': 3}]
    assert bridge['duration_minutes'] is None and bridge['duration_status'] == 'unmeasured_until_pilot'
    assert bridge['required_outcomes'] == result['target']['required_outcome_count'] == 33
    plan = result['equivalence_plan']
    assert plan['review_id'] == 'legacy-2026-10-02.1-to-5.0-outcomes.1'
    assert plan['eligible_outcome_count'] == 0 and result['target']['transferred_outcome_count'] == 0
    assert all(row['status'] == 'requires_assessment' and row['reason_codes'] for row in plan['outcomes'])
    assert result['source']['provenance'] == 'legacy_version_unknown' and result['source']['certified'] is True
    assert result['can_activate'] is False
    assert await repo.progress.find_one({'_id': ObjectId(source.progress_id)}) == before
