"""Unit tests for Role Spine Layer 3.1 — briefing kb-news role filter.

Exercises `_item_matches_user_role` against mocked LibraryItem + VerifiedItemMetadata
records without a real MongoDB.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from app.models.library import LibraryItemKind


def _fake_li(item_id: str = "abc", kind: str = "workflow") -> MagicMock:
    """Build a LibraryItem-shaped mock for the matcher."""
    li = MagicMock()
    li.item_id = item_id
    li.kind = MagicMock()
    li.kind.value = kind
    return li


def _fake_user(role_segment: str | None = None) -> MagicMock:
    u = MagicMock()
    u.role_segment = role_segment
    return u


def _patch_meta(meta):
    """Replace VerifiedItemMetadata in briefing_service with a MagicMock.

    We mock the whole class (not just find_one) because Beanie's field
    descriptors (e.g. `VerifiedItemMetadata.item_kind == "workflow"`) require
    Beanie to be initialized — too heavyweight for a unit test. MagicMock
    handles the field-comparison expressions as opaque truthy values that
    find_one accepts.
    """
    klass_mock = MagicMock()
    klass_mock.find_one = AsyncMock(return_value=meta)
    return patch("app.services.briefing_service.VerifiedItemMetadata", new=klass_mock)


async def test_universal_item_matches_any_user():
    """Items with empty role_tags should be visible to everyone."""
    from app.services.briefing_service import _item_matches_user_role

    meta = MagicMock(role_tags=[])
    li = _fake_li()
    with _patch_meta(meta):
        assert await _item_matches_user_role(li, _fake_user("compliance")) is True
        assert await _item_matches_user_role(li, _fake_user(None)) is True


async def test_item_without_metadata_matches_anyone():
    """Verified items without a metadata record are treated as universal."""
    from app.services.briefing_service import _item_matches_user_role

    li = _fake_li()
    with _patch_meta(None):
        assert await _item_matches_user_role(li, _fake_user("compliance")) is True
        assert await _item_matches_user_role(li, _fake_user(None)) is True


async def test_role_tagged_item_matches_overlapping_user():
    """A compliance-tagged item should match a compliance user."""
    from app.services.briefing_service import _item_matches_user_role

    meta = MagicMock(role_tags=["compliance"])
    li = _fake_li()
    with _patch_meta(meta):
        assert await _item_matches_user_role(li, _fake_user("compliance")) is True


async def test_role_tagged_item_does_not_match_other_role():
    """A compliance-tagged item should NOT match a PI user."""
    from app.services.briefing_service import _item_matches_user_role

    meta = MagicMock(role_tags=["compliance"])
    li = _fake_li()
    with _patch_meta(meta):
        assert await _item_matches_user_role(li, _fake_user("pi")) is False


async def test_role_tagged_item_does_not_match_user_with_no_role():
    """Tagged items hide from users who haven't declared a role."""
    from app.services.briefing_service import _item_matches_user_role

    meta = MagicMock(role_tags=["compliance"])
    li = _fake_li()
    with _patch_meta(meta):
        assert await _item_matches_user_role(li, _fake_user(None)) is False


async def test_multi_role_tagged_item_matches_any_listed_role():
    """An item tagged for multiple roles should match any of them."""
    from app.services.briefing_service import _item_matches_user_role

    meta = MagicMock(role_tags=["compliance", "sponsored_programs"])
    li = _fake_li()
    with _patch_meta(meta):
        assert await _item_matches_user_role(li, _fake_user("compliance")) is True
        assert await _item_matches_user_role(li, _fake_user("sponsored_programs")) is True
        assert await _item_matches_user_role(li, _fake_user("pi")) is False


async def test_matcher_invokes_metadata_lookup():
    """Sanity: the matcher must perform a metadata lookup, not short-circuit."""
    from app.services import briefing_service

    li = _fake_li(item_id="xyz", kind=LibraryItemKind.KNOWLEDGE_BASE.value)
    klass_mock = MagicMock()
    klass_mock.find_one = AsyncMock(return_value=MagicMock(role_tags=[]))
    with patch.object(briefing_service, "VerifiedItemMetadata", klass_mock):
        await briefing_service._item_matches_user_role(li, _fake_user("pi"))
    assert klass_mock.find_one.await_count == 1
