from types import SimpleNamespace

import pytest

from app.services.certification_versions.enrollments import EnrollmentConflict
from app.services.certification_versions.upgrade_targets import initial_level


def package(levels):
    return SimpleNamespace(json=lambda _: {'levels': levels}, manifest=SimpleNamespace(modules=[SimpleNamespace(base_xp=100)]))


def test_target_initial_level_comes_from_its_pinned_structure():
    assert initial_level(package([{'name': 'starting', 'xp': 0}, {'name': 'complete', 'xp': 100}])) == 'starting'


@pytest.mark.parametrize('levels', [None, [], [None], [{'name': 'missing'}], [{'name': 'wrong', 'xp': True}],
    [{'name': 'late', 'xp': 1}], [{'name': 'start', 'xp': 0}, {'name': 'unreachable', 'xp': 101}],
    [{'name': 'same', 'xp': 0}, {'name': 'same', 'xp': 100}],
    [{'name': 'start', 'xp': 0}, {'name': 'high', 'xp': 100}, {'name': 'lower', 'xp': 50}]])
def test_invalid_or_unreachable_progression_cannot_prepare_an_enrollment(levels):
    with pytest.raises(EnrollmentConflict, match='pinned zero-XP progression'):
        initial_level(package(levels))
