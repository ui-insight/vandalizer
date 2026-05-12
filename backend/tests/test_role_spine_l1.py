"""Unit tests for Role Spine Layer 1 — org-tree walk-up + role_segment validation.

End-to-end SAML / register flows that touch MongoDB live in tier-2 integration tests.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.organization import VALID_ROLE_SEGMENTS
from app.schemas.auth import RegisterRequest


def test_valid_role_segments_constant():
    assert "research_admin" in VALID_ROLE_SEGMENTS
    assert "pi" in VALID_ROLE_SEGMENTS
    assert "sponsored_programs" in VALID_ROLE_SEGMENTS
    assert "compliance" in VALID_ROLE_SEGMENTS
    assert "it" in VALID_ROLE_SEGMENTS
    assert "other" in VALID_ROLE_SEGMENTS


def test_register_request_accepts_valid_role():
    req = RegisterRequest(email="a@b.com", password="Password1!", role_segment="compliance")
    assert req.role_segment == "compliance"


def test_register_request_rejects_unknown_role():
    with pytest.raises(Exception):
        RegisterRequest(email="a@b.com", password="Password1!", role_segment="wizard")


def test_register_request_normalizes_empty_string_to_none():
    req = RegisterRequest(email="a@b.com", password="Password1!", role_segment="")
    assert req.role_segment is None


def test_register_request_role_segment_is_optional():
    req = RegisterRequest(email="a@b.com", password="Password1!")
    assert req.role_segment is None


# ---------------------------------------------------------------------------
# Walk-up resolver — exercises traversal without a real MongoDB.
# ---------------------------------------------------------------------------

class _FakeOrg:
    def __init__(self, uuid: str, parent_id: str | None, role_segment: str | None):
        self.uuid = uuid
        self.parent_id = parent_id
        self.role_segment = role_segment


def _patch_orgs(orgs: list[_FakeOrg]):
    """Patch Organization.find_all() to return the given list."""
    chain = AsyncMock()
    chain.to_list = AsyncMock(return_value=orgs)
    return patch("app.services.organization_service.Organization.find_all", return_value=chain)


async def test_walk_up_returns_direct_role_when_set():
    from app.services.organization_service import resolve_role_segment_for_org

    orgs = [_FakeOrg("unit-x", "dept-y", "compliance")]
    with _patch_orgs(orgs):
        result = await resolve_role_segment_for_org("unit-x")
    assert result == "compliance"


async def test_walk_up_inherits_from_parent():
    from app.services.organization_service import resolve_role_segment_for_org

    orgs = [
        _FakeOrg("unit-x", "dept-y", None),
        _FakeOrg("dept-y", "college-z", "sponsored_programs"),
        _FakeOrg("college-z", None, None),
    ]
    with _patch_orgs(orgs):
        result = await resolve_role_segment_for_org("unit-x")
    assert result == "sponsored_programs"


async def test_walk_up_returns_none_when_no_ancestor_declares():
    from app.services.organization_service import resolve_role_segment_for_org

    orgs = [
        _FakeOrg("unit-x", "dept-y", None),
        _FakeOrg("dept-y", "college-z", None),
        _FakeOrg("college-z", None, None),
    ]
    with _patch_orgs(orgs):
        result = await resolve_role_segment_for_org("unit-x")
    assert result is None


async def test_walk_up_handles_missing_org():
    from app.services.organization_service import resolve_role_segment_for_org

    with _patch_orgs([]):
        result = await resolve_role_segment_for_org("ghost-uuid")
    assert result is None


async def test_walk_up_returns_none_for_empty_input():
    from app.services.organization_service import resolve_role_segment_for_org

    result = await resolve_role_segment_for_org("")
    assert result is None


async def test_walk_up_does_not_loop_on_cyclic_parent():
    """Defensive: bad data with a cycle should not infinite-loop."""
    from app.services.organization_service import resolve_role_segment_for_org

    orgs = [
        _FakeOrg("a", "b", None),
        _FakeOrg("b", "a", None),  # cycle
    ]
    with _patch_orgs(orgs):
        result = await resolve_role_segment_for_org("a")
    assert result is None


# ---------------------------------------------------------------------------
# _derive_role_segment_from_org — mutation helper used in SAML login
# ---------------------------------------------------------------------------

async def test_derive_role_segment_skips_when_user_has_explicit_role():
    """If the user already has a role, the helper must NOT overwrite it."""
    from unittest.mock import MagicMock

    from app.services.auth_service import _derive_role_segment_from_org

    user = MagicMock()
    user.role_segment = "pi"
    user.organization_id = "some-org"

    with patch("app.services.organization_service.resolve_role_segment_for_org",
               new=AsyncMock(return_value="compliance")):
        await _derive_role_segment_from_org(user)

    assert user.role_segment == "pi"  # unchanged


async def test_derive_role_segment_skips_when_user_has_no_org():
    from unittest.mock import MagicMock

    from app.services.auth_service import _derive_role_segment_from_org

    user = MagicMock()
    user.role_segment = None
    user.organization_id = None

    # Should not even hit the resolver
    with patch("app.services.organization_service.resolve_role_segment_for_org",
               new=AsyncMock(side_effect=AssertionError("should not be called"))):
        await _derive_role_segment_from_org(user)

    assert user.role_segment is None


async def test_derive_role_segment_inherits_when_unset():
    from unittest.mock import MagicMock

    from app.services.auth_service import _derive_role_segment_from_org

    user = MagicMock()
    user.role_segment = None
    user.organization_id = "some-org"

    with patch("app.services.organization_service.resolve_role_segment_for_org",
               new=AsyncMock(return_value="compliance")):
        await _derive_role_segment_from_org(user)

    assert user.role_segment == "compliance"
