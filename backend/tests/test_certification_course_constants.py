"""DEF-04: the unversioned course has one definition; no second copy can drift."""
import json

from app.services import certification_service as service
from app.services import engagement_service
from app.services.certification_versions.catalog import CATALOG_ROOT
from app.services.certification_versions.rubrics import legacy_20261002 as legacy


def served_panel():
    return json.loads((CATALOG_ROOT.parent / 'panel-modules.json').read_text())


def test_grading_constants_are_the_preserved_rubric_values():
    assert service.MODULE_XP == legacy.MODULE_XP and service.MODULE_ORDER == legacy.MODULE_ORDER
    assert service.LEVELS == list(legacy.LEVELS) and service.ASSESSMENT_KEYS == legacy.ASSESSMENT_KEYS


def test_titles_order_and_xp_match_the_served_course():
    panel = served_panel()
    assert [module['id'] for module in panel] == service.MODULE_ORDER
    assert {module['id']: module['title'] for module in panel} == service.MODULE_TITLES
    assert {module['id']: module['xp'] for module in panel} == service.MODULE_XP


def test_onboarding_emails_use_the_course_titles_in_course_order():
    drip = engagement_service._DRIP_MODULES
    assert [module['id'] for module in drip] == service.MODULE_ORDER[:len(drip)]
    assert all(module['title'] == service.MODULE_TITLES[module['id']] for module in drip)
