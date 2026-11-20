"""Who may edit or delete a Skill, formatter or extraction (#1164).

Team membership alone used to be enough, and so was bookmarking the item into
your own library. Manage is now the creator, an owner/admin of the item's
team, or a site admin; everyone who can see it can still open and run it.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.library import LibraryScope
from app.services import access_control as ac
from app.services import chat_tools, library_service

OID = "64b000000000000000000001"


def _find(result):
    query = MagicMock()
    query.to_list = AsyncMock(return_value=result)
    return query


def _user(user_id="member", is_admin=False):
    return SimpleNamespace(user_id=user_id, is_admin=is_admin, is_examiner=False, current_team=None)


def _search_set(**kw):
    base = dict(id=OID, uuid="ss-1", user_id="owner1", team_id="team-1", is_global=False, verified=False)
    return SimpleNamespace(**{**base, **kw})


def _access(role):
    return ac.TeamAccessContext(team_uuids={"team-1"}, roles_by_uuid={"team-1": role})


async def _authorized(user, ss, access, library, *, manage, by_id=False):
    SS = MagicMock()
    SS.find_one = AsyncMock(return_value=ss)
    SS.get = AsyncMock(return_value=ss)
    items = MagicMock()
    items.find = MagicMock(return_value=_find([SimpleNamespace(id="li")] if library else []))
    libraries = MagicMock()
    libraries.find = MagicMock(return_value=_find([library] if library else []))
    with (
        patch("app.models.search_set.SearchSet", SS),
        patch.object(ac, "LibraryItem", items),
        patch.object(ac, "Library", libraries),
        patch.object(ac, "get_team_access_context", AsyncMock(return_value=access)),
        patch.object(ac, "has_open_verification_review_access", AsyncMock(return_value=False)),
    ):
        if by_id:
            return await ac.get_authorized_search_set_by_id(OID, user, manage=manage)
        return await ac.get_authorized_search_set("ss-1", user, manage=manage)


PERSONAL = SimpleNamespace(scope=LibraryScope.PERSONAL, owner_user_id="member", team=None, items=["li"])
TEAM = SimpleNamespace(scope=LibraryScope.TEAM, owner_user_id="owner1", team="team-1", items=["li"])


@pytest.mark.asyncio
@pytest.mark.parametrize("by_id", [False, True])
@pytest.mark.parametrize("library", [None, PERSONAL, TEAM], ids=["no bookmark", "own bookmark", "team library"])
async def test_a_member_cannot_manage_a_teammates_item_however_it_is_reached(library, by_id):
    ss = _search_set()
    assert await _authorized(_user(), ss, _access("member"), library, manage=True, by_id=by_id) is None


@pytest.mark.asyncio
async def test_a_member_can_still_open_it():
    ss = _search_set()
    assert await _authorized(_user(), ss, _access("member"), None, manage=False) is ss


@pytest.mark.asyncio
@pytest.mark.parametrize("by_id", [False, True])
@pytest.mark.parametrize("who,access", [
    (_user("owner1"), _access("member")),
    (_user("lead"), _access("admin")),
    (_user("lead"), _access("owner")),
])
async def test_the_creator_and_team_admins_can_manage_it(who, access, by_id):
    ss = _search_set()
    assert await _authorized(who, ss, access, None, manage=True, by_id=by_id) is ss


@pytest.mark.asyncio
async def test_a_bookmark_of_a_verified_item_does_not_make_it_yours():
    ss = _search_set(user_id="system", team_id=None, verified=True)
    assert await _authorized(_user(), ss, _access("member"), PERSONAL, manage=True) is None


def _chat(user_id, role):
    deps = SimpleNamespace(user=_user(user_id), user_id=user_id, team_id="team-1")
    return SimpleNamespace(deps=deps), AsyncMock(return_value=_access(role))


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id,role,allowed", [
    ("owner1", "member", True), ("lead", "admin", True), ("member", "member", False),
])
async def test_chat_tunes_an_extraction_only_for_its_creator_or_a_team_admin(user_id, role, allowed):
    ctx, team_context = _chat(user_id, role)
    ss = _search_set(title="Award terms")
    model = MagicMock()
    model.uuid = "uuid"
    model.find_one = AsyncMock(return_value=ss)
    with patch.object(chat_tools, "SearchSet", model), patch.object(ac, "get_team_access_context", team_context):
        item, title, err = await chat_tools._get_optimizable_item(ctx, "search_set", "ss-1")
    if allowed:
        assert (item, title, err) == (ss, "Award terms", None)
    else:
        assert item is None and "creator or a team admin" in err["error"]


@pytest.mark.asyncio
async def test_a_row_returned_after_pinning_keeps_the_creators_edit_rights():
    """Pin, favorite and tag return the row that replaces the listed one."""
    user = _user("owner1")
    item = SimpleNamespace(id="li")
    deref = AsyncMock(return_value={"can_edit_underlying": True})
    access = _access("member")
    with (
        patch.object(library_service, "_dereference_item", deref),
        patch.object(library_service.access_control, "get_team_access_context", AsyncMock(return_value=access)),
    ):
        row = await library_service._dereference_for(item, user)
    assert row == {"can_edit_underlying": True}
    deref.assert_awaited_once_with(item, user, access)
