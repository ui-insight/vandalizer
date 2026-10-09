"""The bridge shortcuts study navigation, never required assessment evidence."""
import pytest
from pydantic import ValidationError

from app.services.certification_versions.bridge_path import public_bridge_path
from app.services.certification_versions.catalog import CATALOG_ROOT, CourseCatalog, CourseCatalogError
from tests import test_certification_credit_equivalence as fixtures

candidate = fixtures.candidate


def test_bridge_covers_all_outcomes_and_keeps_capstone_without_a_duration_claim(candidate):
    path = public_bridge_path(candidate.package)
    assert path['required_outcomes'] == 33
    assert path['duration_minutes'] is None
    assert path['credit_policy'] == 'same_course_same_required_outcomes'
    rows = [module for stage in path['stages'] for module in stage['modules']]
    assert len(rows) == len({row['module_id'] for row in rows}) == 11
    assert sum(row['required_outcomes'] for row in rows) == 33
    assert path['stages'][-1]['modules'][0]['module_id'] == 'governance'
    assert path['manifest_sha256'] == candidate.package.manifest_sha256


def test_legacy_package_does_not_gain_a_new_study_path():
    package = CourseCatalog(CATALOG_ROOT).load('legacy-2026-10-02.1', preview=True)
    assert public_bridge_path(package) is None


@pytest.mark.parametrize('mutation', ['omit_capstone', 'duplicate_module', 'unknown_module', 'duplicate_stage', 'promise_time', 'waive_credit'])
def test_invalid_or_misleading_bridge_cannot_be_delivered(candidate, mutation):
    path = candidate.package.json('bridge-path.json')
    if mutation == 'omit_capstone':
        path['stages'].pop()
    elif mutation == 'duplicate_module':
        path['stages'][0]['module_ids'].append('governance')
    elif mutation == 'unknown_module':
        path['stages'][0]['module_ids'][0] = 'invented'
    elif mutation == 'duplicate_stage':
        path['stages'][1]['id'] = path['stages'][0]['id']
    elif mutation == 'promise_time':
        path['duration_minutes'] = 15
    else:
        path['credential_policy'] = 'waive_new_outcomes'
    package = fixtures.changed(candidate.package, assets={'bridge-path.json': path})
    with pytest.raises((CourseCatalogError, ValidationError)):
        public_bridge_path(package)
