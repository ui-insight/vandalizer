"""Plain update status: only a published offer for the pinned course counts."""
import json
import shutil
from types import SimpleNamespace

import pytest

from app.services.certification_versions.catalog import CATALOG_ROOT
from app.services.certification_versions.course_updates import optional_update_available
from app.services.certification_versions.tool_results import Result

SOURCE = 'legacy-2026-10-02.1'


def package(root, release_id=SOURCE):
    return SimpleNamespace(catalog_root=root, manifest=SimpleNamespace(release_id=release_id))


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / 'courses'
    shutil.copytree(CATALOG_ROOT, root)
    registry = json.loads((root / 'registry.json').read_text())
    entry = registry['releases'][SOURCE]
    registry['releases']['course-5.0.0'] = {**entry, 'state': 'draft'}

    def write(*, offers, target_state='draft'):
        registry['releases']['course-5.0.0'].update(state=target_state, supported_for_existing=target_state == 'published')
        registry['optional_upgrade_offers'] = offers
        (root / 'registry.json').write_text(json.dumps(registry))
        return root
    return write


def test_no_offer_means_no_update(catalog):
    assert optional_update_available(package(catalog(offers={}))) is False


def test_an_unpublished_offer_is_not_announced(catalog):
    assert optional_update_available(package(catalog(offers={SOURCE: ['course-5.0.0']}))) is False


def test_a_published_offer_for_the_pinned_course_is_announced(catalog):
    root = catalog(offers={SOURCE: ['course-5.0.0']}, target_state='published')
    assert optional_update_available(package(root)) is True
    # The offer belongs to its source course only.
    assert optional_update_available(package(root, 'course-5.0.0')) is False


def test_an_unreadable_registry_is_unknown_not_no_update(tmp_path):
    assert optional_update_available(package(tmp_path)) is None


def test_chat_contract_accepts_only_a_boolean_or_unknown_update_status():
    identity = {'enrollment_id': 'a' * 32, 'course_version': 'v', 'course_title': 'T', 'manifest_sha256': 'b' * 64}
    assert Result.model_validate({**identity, 'optional_update_available': True}).optional_update_available is True
    assert Result.model_validate(identity).optional_update_available is None
    with pytest.raises(ValueError):
        Result.model_validate({**identity, 'optional_update_available': 'yes'})
