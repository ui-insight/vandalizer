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


def _library_models(library):
    """The LibraryItem, Library and Team lookups behind a library entry.

    A library names its team by ObjectId and an item by uuid or ObjectId; the
    fixtures here use one string for both, so the team's uuid is that string.
    """
    items = MagicMock()
    items.find = MagicMock(return_value=_find([SimpleNamespace(id="li")] if library else []))
    libraries = MagicMock()
    libraries.find = MagicMock(return_value=_find([library] if library else []))
    teams = MagicMock()
    teams.get = AsyncMock(side_effect=lambda team: SimpleNamespace(uuid=TEAM_UUIDS.get(team, team)))
    return items, libraries, teams


async def _authorized(user, ss, access, library, *, manage, by_id=False):
    SS = MagicMock()
    SS.find_one = AsyncMock(return_value=ss)
    SS.get = AsyncMock(return_value=ss)
    items, libraries, teams = _library_models(library)
    with (
        patch("app.models.search_set.SearchSet", SS),
        patch.object(ac, "LibraryItem", items),
        patch.object(ac, "Library", libraries),
        patch.object(ac, "Team", teams),
        patch.object(ac, "get_team_access_context", AsyncMock(return_value=access)),
        patch.object(ac, "has_open_verification_review_access", AsyncMock(return_value=False)),
    ):
        if by_id:
            return await ac.get_authorized_search_set_by_id(OID, user, manage=manage)
        return await ac.get_authorized_search_set("ss-1", user, manage=manage)


async def _authorized_workflow(user, wf, access, library, *, manage):
    WF = MagicMock()
    WF.get = AsyncMock(return_value=wf)
    items, libraries, teams = _library_models(library)
    with (
        patch("app.models.workflow.Workflow", WF),
        patch.object(ac, "LibraryItem", items),
        patch.object(ac, "Library", libraries),
        patch.object(ac, "Team", teams),
        patch.object(ac, "has_open_verification_review_access", AsyncMock(return_value=False)),
    ):
        return await ac.get_authorized_workflow(OID, user, manage=manage, team_access=access)


# Team ObjectId (as a library stores it) -> team uuid (as an item may store it).
TEAM_UUIDS = {"team-1-oid": "team-1"}

PERSONAL = SimpleNamespace(scope=LibraryScope.PERSONAL, owner_user_id="member", team=None, items=["li"])
TEAM = SimpleNamespace(scope=LibraryScope.TEAM, owner_user_id="owner1", team="team-1", items=["li"])


@pytest.mark.asyncio
@pytest.mark.parametrize("by_id", [False, True])
@pytest.mark.parametrize("library", [None, PERSONAL, TEAM], ids=["no bookmark", "own bookmark", "team library"])
async def test_a_member_cannot_manage_a_teammates_item_however_it_is_reached(library, by_id):
    ss = _search_set()
    assert await _authorized(_user(), ss, _access("member"), library, manage=True, by_id=by_id) is None


# A member of the item's team (team-1) who owns a team of their own (team-2)
# and has filed the item in that team's library. Any member can file an item
# they can see into a team library they belong to.
OTHER_TEAM = SimpleNamespace(scope=LibraryScope.TEAM, owner_user_id="member", team="team-2", items=["li"])


def _member_here_owner_elsewhere():
    return ac.TeamAccessContext(
        team_uuids={"team-1", "team-2"},
        roles_by_uuid={"team-1": "member", "team-2": "owner"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("by_id", [False, True])
async def test_filing_it_in_a_team_you_own_does_not_let_you_manage_it(by_id):
    ss = _search_set()
    access = _member_here_owner_elsewhere()
    assert await _authorized(_user(), ss, access, OTHER_TEAM, manage=True, by_id=by_id) is None
    assert await _authorized(_user(), ss, access, OTHER_TEAM, manage=False, by_id=by_id) is ss


@pytest.mark.asyncio
@pytest.mark.parametrize("by_id", [False, True])
@pytest.mark.parametrize("role", ["owner", "admin"])
async def test_an_admin_of_its_own_team_manages_it_from_that_teams_library(role, by_id):
    ss = _search_set()
    assert await _authorized(_user("lead"), ss, _access(role), TEAM, manage=True, by_id=by_id) is ss


@pytest.mark.asyncio
@pytest.mark.parametrize("item_team,library_team,allowed", [
    ("team-1", "team-1", True),        # same team, same spelling
    ("team-1", "team-1-oid", True),    # item names its team by uuid, the library by ObjectId
    ("team-1", "team-2", False),       # another team's library
    (None, "team-2", False),           # an item with no team, filed in a team library
])
async def test_only_the_library_of_the_items_own_team_counts_toward_manage(item_team, library_team, allowed):
    access = ac.TeamAccessContext(
        team_uuids={"team-1", "team-2"},
        team_object_ids={"team-1-oid"},
        roles_by_uuid={"team-1": "admin", "team-2": "owner"},
        roles_by_object_id={"team-1-oid": "admin"},
    )
    library = SimpleNamespace(scope=LibraryScope.TEAM, owner_user_id="x", team=library_team, items=["li"])
    items, libraries, teams = _library_models(library)
    with patch.object(ac, "LibraryItem", items), patch.object(ac, "Library", libraries), patch.object(ac, "Team", teams):
        got = await ac.has_library_backed_object_access(
            "search_set", OID, _user("lead"), access, manage=True, object_team_id=item_team,
        )
        seen = await ac.has_library_backed_object_access(
            "search_set", OID, _user("lead"), access, manage=False, object_team_id=item_team,
        )
    assert got is allowed
    assert seen is True


def _workflow(**kw):
    base = dict(id=OID, user_id="owner1", team_id="team-1", verified=False, share_token=None)
    return SimpleNamespace(**{**base, **kw})


@pytest.mark.asyncio
async def test_filing_a_workflow_in_a_team_you_own_does_not_let_you_manage_it():
    wf = _workflow()
    access = _member_here_owner_elsewhere()
    assert await _authorized_workflow(_user(), wf, access, OTHER_TEAM, manage=True) is None
    assert await _authorized_workflow(_user(), wf, access, OTHER_TEAM, manage=False) is wf


@pytest.mark.asyncio
@pytest.mark.parametrize("who,access,library", [
    (_user("owner1"), _access("member"), None),
    (_user("lead"), _access("admin"), None),
    (_user("lead"), _access("owner"), TEAM),
    (_user("lead"), _access("admin"), TEAM),
], ids=["creator", "team admin", "team owner via team library", "team admin via team library"])
async def test_a_workflows_creator_and_its_team_admins_still_manage_it(who, access, library):
    wf = _workflow()
    assert await _authorized_workflow(who, wf, access, library, manage=True) is wf


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
