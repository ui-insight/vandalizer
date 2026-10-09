"""Draft policy cannot drift from course credit, ordering or journey coverage."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.certification_versions import progression_policy as policy_module
from app.services.certification_versions.progression_policy import ProgressionPolicy, package_progression_policy, public_progression_policy
from tests.test_certification_v5_preview import preview


@pytest.fixture
def package(monkeypatch):
    policy = json.loads((preview.DATA / 'drafts/v5.0/progression-policy.json').read_text())
    structure = json.loads((preview.DATA / 'drafts/v5.0/course-structure.json').read_text())
    from app.services.certification_versions import outcomes
    monkeypatch.setattr(outcomes, 'package_outcomes', lambda package: SimpleNamespace(required_outcomes=lambda: tuple(range(33))))
    return SimpleNamespace(manifest=SimpleNamespace(artifacts={'progression-policy.json': 'fixture'},
        modules=[SimpleNamespace(id=key, base_xp=value, prerequisites=[]) for key, value in policy['module_xp'].items()], maximum_stars=1, star_bonus_xp=0),
        entry=SimpleNamespace(state='draft'), read=lambda name: json.dumps(policy).encode(), json=lambda name: deepcopy(structure), policy=policy, structure=structure)


def test_draft_policy_has_exact_credit_and_truthful_journey_groups(package):
    policy = package_progression_policy(package)
    assert policy.learning_order == 'any_order' and sum(policy.module_xp.values()) == 1850
    public = public_progression_policy(package)
    assert (public['required_modules'], public['required_outcomes'], public['base_xp_total']) == (11, 33, 1850)
    assert public['state'] == 'design_draft'
    assert 'staff_queue_enabled' not in public
    assert any('Assessment is automatic' in rule for rule in public['rules'])
    assert policy.staff_queue_enabled is False
    assert any('not additional credentials' in rule for rule in public['rules'])
    for tier in package.structure['tiers']:
        assert 'certified builder' not in tier['celebration'].lower()
        assert "earned your certification" not in tier['celebration'].lower()


@pytest.mark.parametrize('change', ['extra_module', 'xp', 'prerequisite', 'stars', 'bonus', 'unreachable_level', 'duplicate_level', 'missing_tier_module', 'duplicate_tier_module', 'published_draft'])
def test_inconsistent_course_policy_is_rejected(package, change):
    if change == 'extra_module':
        package.manifest.modules.append(SimpleNamespace(id='unreviewed', base_xp=100, prerequisites=[]))
    elif change == 'xp':
        package.manifest.modules[0].base_xp += 1
    elif change == 'prerequisite':
        package.manifest.modules[-1].prerequisites = ['foundations']
    elif change == 'stars':
        package.manifest.maximum_stars = 3
    elif change == 'bonus':
        package.manifest.star_bonus_xp = 25
    elif change == 'unreachable_level':
        package.structure['levels'][-1]['xp'] = 1851
    elif change == 'duplicate_level':
        package.structure['levels'][1]['xp'] = 0
    elif change == 'missing_tier_module':
        package.structure['tiers'][0]['moduleIds'].pop()
    elif change == 'duplicate_tier_module':
        package.structure['tiers'][0]['moduleIds'].append('governance')
    else:
        package.entry.state = 'published'
    with pytest.raises(ValueError):
        package_progression_policy(package)


@pytest.mark.parametrize('field,value', [('staff_queue_enabled', True), ('grading_mode', 'staff_review'), ('maximum_stars', 3), ('time_limit_seconds', 600), ('enrichment_awards_credit', True), ('credit', 'xp_for_reading')])
def test_unsupported_policy_cannot_silently_change_requirements(package, field, value):
    with pytest.raises(ValidationError):
        ProgressionPolicy.model_validate({**package.policy, field: value})


def test_old_immutable_package_has_no_invented_new_policy(package):
    package.manifest.artifacts = {}
    assert policy_module.package_progression_policy(package) is None
    assert public_progression_policy(package) is None


def test_publication_cannot_promote_an_unreviewed_policy(package, monkeypatch, tmp_path):
    from app.services.certification_versions import authoring, outcomes
    from app.services.certification_versions.catalog import CourseCatalogError
    monkeypatch.setattr(outcomes, 'package_outcomes', lambda package: SimpleNamespace(state='release_candidate'))
    package.manifest_sha256 = 'a' * 64
    catalog = SimpleNamespace(root=tmp_path, load=lambda *args, **kwargs: package)
    with pytest.raises(CourseCatalogError, match='reviewed progression policy'):
        authoring.publish(catalog, 'draft-policy', expected_digest=package.manifest_sha256)
    assert not (tmp_path / 'registry.json').exists()
