"""Tests for app.services.access_control."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.library import LibraryScope
from app.services.access_control import (
    TeamAccessContext,
    can_manage_automation,
    can_manage_document,
    can_manage_folder,
    can_manage_knowledge_base,
    can_manage_library,
    can_manage_library_folder,
    can_manage_search_set,
    can_manage_workflow,
    can_view_automation,
    can_view_document,
    can_view_folder,
    can_view_knowledge_base,
    can_view_library,
    can_view_library_folder,
    can_view_search_set,
    can_view_workflow,
    get_authorized_document,
    get_authorized_folder,
    get_authorized_search_set,
    get_authorized_workflow,
    get_team_access_context,
)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_user(user_id="user1", is_admin=False):
    u = MagicMock()
    u.user_id = user_id
    u.is_admin = is_admin
    return u


def _make_folder(user_id="user1", team_id=None):
    f = MagicMock()
    f.user_id = user_id
    f.team_id = team_id
    f.uuid = "folder-uuid"
    return f


def _make_document(user_id="user1", team_id=None):
    d = MagicMock()
    d.user_id = user_id
    d.team_id = team_id
    d.uuid = "doc-uuid"
    return d


def _make_workflow(user_id="user1", team_id=None):
    w = MagicMock()
    w.user_id = user_id
    w.team_id = team_id
    return w


def _make_search_set(user_id="user1", is_global=False):
    ss = MagicMock()
    ss.user_id = user_id
    ss.is_global = is_global
    ss.uuid = "ss-uuid"
    return ss


def _make_automation(user_id="user1", team_id=None, shared_with_team=False):
    auto = MagicMock()
    auto.user_id = user_id
    auto.team_id = team_id
    auto.shared_with_team = shared_with_team
    return auto


def _make_knowledge_base(
    user_id="user1",
    team_id=None,
    shared_with_team=False,
    verified=False,
    organization_ids=None,
):
    kb = MagicMock()
    kb.user_id = user_id
    kb.team_id = team_id
    kb.shared_with_team = shared_with_team
    kb.verified = verified
    kb.organization_ids = organization_ids or []
    return kb


def _make_library(scope=LibraryScope.PERSONAL, owner_user_id="user1", team=None):
    lib = MagicMock()
    lib.scope = scope
    lib.owner_user_id = owner_user_id
    lib.team = team
    return lib


def _make_library_folder(
    scope=LibraryScope.PERSONAL,
    owner_user_id="user1",
    team=None,
):
    folder = MagicMock()
    folder.scope = scope
    folder.owner_user_id = owner_user_id
    folder.team = team
    folder.uuid = "library-folder-uuid"
    return folder


def _team_access(team_uuids=None, roles=None, team_object_ids=None, object_roles=None):
    return TeamAccessContext(
        team_uuids=team_uuids or set(),
        team_object_ids=team_object_ids or set(),
        roles_by_uuid=roles or {},
        roles_by_object_id=object_roles or {},
    )


# ---------------------------------------------------------------------------
# TestCanViewFolder
# ---------------------------------------------------------------------------


class TestCanViewFolder:
    def test_owner_can_view_personal_folder(self):
        user = _make_user("owner1")
        folder = _make_folder("owner1", team_id=None)
        access = _team_access()
        assert can_view_folder(folder, user, access) is True

    def test_non_owner_cannot_view_personal_folder(self):
        user = _make_user("other")
        folder = _make_folder("owner1", team_id=None)
        access = _team_access()
        assert can_view_folder(folder, user, access) is False

    def test_team_member_can_view_team_folder(self):
        user = _make_user("member1")
        folder = _make_folder("owner1", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "member"},
        )
        assert can_view_folder(folder, user, access) is True

    def test_non_member_cannot_view_team_folder(self):
        user = _make_user("outsider")
        folder = _make_folder("owner1", team_id="team-abc")
        access = _team_access()  # no teams
        assert can_view_folder(folder, user, access) is False

    def test_admin_bypass(self):
        user = _make_user("admin1", is_admin=True)
        folder = _make_folder("someone_else", team_id="team-xyz")
        access = _team_access()  # not a member of team-xyz
        # Without allow_admin, admin cannot bypass
        assert can_view_folder(folder, user, access, allow_admin=False) is False
        # With allow_admin, admin bypasses
        assert can_view_folder(folder, user, access, allow_admin=True) is True


# ---------------------------------------------------------------------------
# TestCanManageFolder
# ---------------------------------------------------------------------------


class TestCanManageFolder:
    def test_owner_can_manage_personal_folder(self):
        user = _make_user("owner1")
        folder = _make_folder("owner1", team_id=None)
        access = _team_access()
        assert can_manage_folder(folder, user, access) is True

    def test_non_owner_cannot_manage_personal_folder(self):
        user = _make_user("other")
        folder = _make_folder("owner1", team_id=None)
        access = _team_access()
        assert can_manage_folder(folder, user, access) is False

    def test_team_admin_can_manage_team_folder(self):
        user = _make_user("admin-member")
        folder = _make_folder("owner1", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "admin"},
        )
        assert can_manage_folder(folder, user, access) is True

    def test_team_owner_can_manage_team_folder(self):
        user = _make_user("team-owner")
        folder = _make_folder("creator", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "owner"},
        )
        assert can_manage_folder(folder, user, access) is True

    def test_team_member_cannot_manage_team_folder(self):
        user = _make_user("member1")
        folder = _make_folder("owner1", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "member"},
        )
        assert can_manage_folder(folder, user, access) is False

    def test_admin_bypass(self):
        user = _make_user("admin1", is_admin=True)
        folder = _make_folder("someone_else", team_id="team-xyz")
        access = _team_access()
        assert can_manage_folder(folder, user, access, allow_admin=False) is False
        assert can_manage_folder(folder, user, access, allow_admin=True) is True


# ---------------------------------------------------------------------------
# TestCanViewDocument
# ---------------------------------------------------------------------------


class TestCanViewDocument:
    def test_owner_can_view(self):
        user = _make_user("owner1")
        doc = _make_document("owner1")
        access = _team_access()
        assert can_view_document(doc, user, access) is True

    def test_team_member_can_view_team_doc(self):
        user = _make_user("member1")
        doc = _make_document("owner1", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "member"},
        )
        assert can_view_document(doc, user, access) is True

    def test_non_member_cannot_view_team_doc(self):
        user = _make_user("outsider")
        doc = _make_document("owner1", team_id="team-abc")
        access = _team_access()
        assert can_view_document(doc, user, access) is False

    def test_non_owner_cannot_view_personal_doc(self):
        user = _make_user("other")
        doc = _make_document("owner1", team_id=None)
        access = _team_access()
        assert can_view_document(doc, user, access) is False

    def test_admin_bypass(self):
        user = _make_user("admin1", is_admin=True)
        doc = _make_document("someone_else", team_id="team-xyz")
        access = _team_access()
        assert can_view_document(doc, user, access, allow_admin=False) is False
        assert can_view_document(doc, user, access, allow_admin=True) is True


# ---------------------------------------------------------------------------
# TestCanManageDocument
# ---------------------------------------------------------------------------


class TestCanManageDocument:
    def test_owner_can_manage(self):
        user = _make_user("owner1")
        doc = _make_document("owner1", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "member"},
        )
        assert can_manage_document(doc, user, access) is True

    def test_team_admin_can_manage(self):
        user = _make_user("team-admin")
        doc = _make_document("owner1", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "admin"},
        )
        assert can_manage_document(doc, user, access) is True

    def test_team_member_cannot_manage(self):
        user = _make_user("member1")
        doc = _make_document("owner1", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "member"},
        )
        assert can_manage_document(doc, user, access) is False

    def test_admin_bypass(self):
        user = _make_user("admin1", is_admin=True)
        doc = _make_document("someone_else", team_id="team-xyz")
        access = _team_access()
        assert can_manage_document(doc, user, access, allow_admin=False) is False
        assert can_manage_document(doc, user, access, allow_admin=True) is True


# ---------------------------------------------------------------------------
# TestCanViewWorkflow
# ---------------------------------------------------------------------------


class TestCanViewWorkflow:
    def test_owner_can_view(self):
        user = _make_user("owner1")
        wf = _make_workflow("owner1")
        access = _team_access()
        assert can_view_workflow(wf, user, access) is True

    def test_team_member_can_view(self):
        user = _make_user("member1")
        wf = _make_workflow("owner1", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "member"},
        )
        assert can_view_workflow(wf, user, access) is True

    def test_non_member_cannot_view(self):
        user = _make_user("outsider")
        wf = _make_workflow("owner1", team_id="team-abc")
        access = _team_access()
        assert can_view_workflow(wf, user, access) is False

    def test_admin_bypass(self):
        user = _make_user("admin1", is_admin=True)
        wf = _make_workflow("someone_else", team_id="team-xyz")
        access = _team_access()
        assert can_view_workflow(wf, user, access, allow_admin=False) is False
        assert can_view_workflow(wf, user, access, allow_admin=True) is True

    def test_team_object_id_membership_allows_view(self):
        user = _make_user("member1")
        wf = _make_workflow("owner1", team_id="team-obj-1")
        access = _team_access(
            team_object_ids={"team-obj-1"},
            object_roles={"team-obj-1": "member"},
        )
        assert can_view_workflow(wf, user, access) is True


# ---------------------------------------------------------------------------
# TestCanManageWorkflow
# ---------------------------------------------------------------------------


class TestCanManageWorkflow:
    def test_owner_can_manage(self):
        user = _make_user("owner1")
        wf = _make_workflow("owner1", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "member"},
        )
        assert can_manage_workflow(wf, user, access) is True

    def test_team_admin_can_manage(self):
        user = _make_user("team-admin")
        wf = _make_workflow("owner1", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "admin"},
        )
        assert can_manage_workflow(wf, user, access) is True

    def test_team_member_cannot_manage(self):
        user = _make_user("member1")
        wf = _make_workflow("owner1", team_id="team-abc")
        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "member"},
        )
        assert can_manage_workflow(wf, user, access) is False

    def test_admin_bypass(self):
        user = _make_user("admin1", is_admin=True)
        wf = _make_workflow("someone_else", team_id="team-xyz")
        access = _team_access()
        assert can_manage_workflow(wf, user, access, allow_admin=False) is False
        assert can_manage_workflow(wf, user, access, allow_admin=True) is True

    def test_team_object_id_admin_role_allows_manage(self):
        user = _make_user("team-admin")
        wf = _make_workflow("owner1", team_id="team-obj-1")
        access = _team_access(
            team_object_ids={"team-obj-1"},
            object_roles={"team-obj-1": "admin"},
        )
        assert can_manage_workflow(wf, user, access) is True


# ---------------------------------------------------------------------------
# TestAutomationAccess
# ---------------------------------------------------------------------------


class TestAutomationAccess:
    def test_owner_can_view_and_manage(self):
        user = _make_user("owner1")
        auto = _make_automation(user_id="owner1")
        access = _team_access()
        assert can_view_automation(auto, user, access) is True
        assert can_manage_automation(auto, user, access) is True

    def test_team_member_can_view_shared_automation(self):
        user = _make_user("member1")
        auto = _make_automation(
            user_id="owner1",
            team_id="team-obj-1",
            shared_with_team=True,
        )
        access = _team_access(
            team_object_ids={"team-obj-1"},
            object_roles={"team-obj-1": "member"},
        )
        assert can_view_automation(auto, user, access) is True
        assert can_manage_automation(auto, user, access) is False

    def test_team_admin_can_manage_shared_automation(self):
        user = _make_user("admin1")
        auto = _make_automation(
            user_id="owner1",
            team_id="team-obj-1",
            shared_with_team=True,
        )
        access = _team_access(
            team_object_ids={"team-obj-1"},
            object_roles={"team-obj-1": "admin"},
        )
        assert can_manage_automation(auto, user, access) is True


# ---------------------------------------------------------------------------
# TestKnowledgeBaseAccess
# ---------------------------------------------------------------------------


class TestKnowledgeBaseAccess:
    def test_owner_can_view_and_manage(self):
        user = _make_user("owner1")
        kb = _make_knowledge_base(user_id="owner1")
        access = _team_access()
        assert can_view_knowledge_base(kb, user, access) is True
        assert can_manage_knowledge_base(kb, user, access) is True

    def test_verified_kb_requires_org_visibility_when_scoped(self):
        user = _make_user("viewer")
        kb = _make_knowledge_base(
            user_id="owner1",
            verified=True,
            organization_ids=["org-a"],
        )
        access = _team_access()
        assert can_view_knowledge_base(
            kb,
            user,
            access,
            user_org_ancestry=["org-a", "org-b"],
        ) is True
        assert can_view_knowledge_base(
            kb,
            user,
            access,
            user_org_ancestry=["org-b"],
        ) is False

    def test_team_admin_can_manage_shared_kb(self):
        user = _make_user("team-admin")
        kb = _make_knowledge_base(
            user_id="owner1",
            team_id="team-obj-1",
            shared_with_team=True,
        )
        access = _team_access(
            team_object_ids={"team-obj-1"},
            object_roles={"team-obj-1": "admin"},
        )
        assert can_manage_knowledge_base(kb, user, access) is True


# ---------------------------------------------------------------------------
# TestLibraryAccess
# ---------------------------------------------------------------------------


class TestLibraryAccess:
    def test_owner_can_view_and_manage_personal_library(self):
        user = _make_user("owner1")
        lib = _make_library(owner_user_id="owner1")
        access = _team_access()
        assert can_view_library(lib, user, access) is True
        assert can_manage_library(lib, user, access) is True

    def test_team_member_can_view_but_not_manage_team_library(self):
        user = _make_user("member1")
        lib = _make_library(scope=LibraryScope.TEAM, owner_user_id="owner1", team="team-obj-1")
        access = _team_access(
            team_object_ids={"team-obj-1"},
            object_roles={"team-obj-1": "member"},
        )
        assert can_view_library(lib, user, access) is True
        assert can_manage_library(lib, user, access) is False

    def test_team_admin_can_manage_team_library(self):
        user = _make_user("admin1")
        lib = _make_library(scope=LibraryScope.TEAM, owner_user_id="owner1", team="team-obj-1")
        access = _team_access(
            team_object_ids={"team-obj-1"},
            object_roles={"team-obj-1": "admin"},
        )
        assert can_manage_library(lib, user, access) is True

    def test_any_authenticated_user_can_view_verified_library(self):
        user = _make_user("viewer")
        lib = _make_library(scope=LibraryScope.VERIFIED, owner_user_id="system")
        access = _team_access()
        assert can_view_library(lib, user, access) is True
        assert can_manage_library(lib, user, access) is False


class TestLibraryFolderAccess:
    def test_owner_can_manage_personal_library_folder(self):
        user = _make_user("owner1")
        folder = _make_library_folder(owner_user_id="owner1")
        access = _team_access()
        assert can_view_library_folder(folder, user, access) is True
        assert can_manage_library_folder(folder, user, access) is True

    def test_team_member_can_view_team_library_folder(self):
        user = _make_user("member1")
        folder = _make_library_folder(scope=LibraryScope.TEAM, owner_user_id="owner1", team="team-obj-1")
        access = _team_access(
            team_object_ids={"team-obj-1"},
            object_roles={"team-obj-1": "member"},
        )
        assert can_view_library_folder(folder, user, access) is True
        assert can_manage_library_folder(folder, user, access) is False

    def test_team_admin_can_manage_team_library_folder(self):
        user = _make_user("admin1")
        folder = _make_library_folder(scope=LibraryScope.TEAM, owner_user_id="owner1", team="team-obj-1")
        access = _team_access(
            team_object_ids={"team-obj-1"},
            object_roles={"team-obj-1": "admin"},
        )
        assert can_manage_library_folder(folder, user, access) is True


# ---------------------------------------------------------------------------
# TestCanViewSearchSet
# ---------------------------------------------------------------------------


class TestCanViewSearchSet:
    def test_owner_can_view(self):
        user = _make_user("owner1")
        ss = _make_search_set("owner1")
        assert can_view_search_set(ss, user) is True

    def test_global_set_viewable_by_anyone(self):
        user = _make_user("random-user")
        ss = _make_search_set("owner1", is_global=True)
        assert can_view_search_set(ss, user) is True

    def test_non_owner_cannot_view_non_global(self):
        user = _make_user("other")
        ss = _make_search_set("owner1", is_global=False)
        assert can_view_search_set(ss, user) is False

    def test_admin_bypass(self):
        user = _make_user("admin1", is_admin=True)
        ss = _make_search_set("someone_else", is_global=False)
        assert can_view_search_set(ss, user, allow_admin=False) is False
        assert can_view_search_set(ss, user, allow_admin=True) is True


# ---------------------------------------------------------------------------
# TestCanManageSearchSet
# ---------------------------------------------------------------------------


class TestCanManageSearchSet:
    def test_owner_can_manage(self):
        user = _make_user("owner1")
        ss = _make_search_set("owner1")
        assert can_manage_search_set(ss, user) is True

    def test_non_owner_cannot_manage_even_global(self):
        user = _make_user("other")
        ss = _make_search_set("owner1", is_global=True)
        assert can_manage_search_set(ss, user) is False

    def test_admin_bypass(self):
        user = _make_user("admin1", is_admin=True)
        ss = _make_search_set("someone_else", is_global=True)
        assert can_manage_search_set(ss, user, allow_admin=False) is False
        assert can_manage_search_set(ss, user, allow_admin=True) is True


# ---------------------------------------------------------------------------
# TestGetTeamAccessContext
# ---------------------------------------------------------------------------


class TestGetTeamAccessContext:
    async def test_user_with_no_teams(self):
        user = _make_user("lonely")

        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=[])

        with patch(
            "app.services.access_control.TeamMembership"
        ) as MockTM:
            MockTM.find.return_value = mock_find
            MockTM.user_id = "user_id"  # attribute used in query expression

            result = await get_team_access_context(user)

        assert result.team_uuids == set()
        assert result.roles_by_uuid == {}

    async def test_user_with_one_team(self):
        user = _make_user("member1")

        membership = MagicMock()
        membership.team = "team-obj-id-1"
        membership.role = "member"

        team = MagicMock()
        team.id = "team-obj-id-1"
        team.uuid = "team-uuid-1"

        mock_membership_find = MagicMock()
        mock_membership_find.to_list = AsyncMock(return_value=[membership])

        mock_team_find = MagicMock()
        mock_team_find.to_list = AsyncMock(return_value=[team])

        with (
            patch("app.services.access_control.TeamMembership") as MockTM,
            patch("app.services.access_control.Team") as MockTeam,
        ):
            MockTM.find.return_value = mock_membership_find
            MockTM.user_id = "user_id"
            MockTeam.find.return_value = mock_team_find

            result = await get_team_access_context(user)

        assert result.team_uuids == {"team-uuid-1"}
        assert result.team_object_ids == {"team-obj-id-1"}
        assert result.roles_by_uuid == {"team-uuid-1": "member"}
        assert result.roles_by_object_id == {"team-obj-id-1": "member"}

    async def test_user_with_multiple_teams(self):
        user = _make_user("busy-user")

        m1 = MagicMock()
        m1.team = "team-obj-id-1"
        m1.role = "owner"

        m2 = MagicMock()
        m2.team = "team-obj-id-2"
        m2.role = "member"

        m3 = MagicMock()
        m3.team = "team-obj-id-3"
        m3.role = "admin"

        t1 = MagicMock()
        t1.id = "team-obj-id-1"
        t1.uuid = "team-uuid-1"

        t2 = MagicMock()
        t2.id = "team-obj-id-2"
        t2.uuid = "team-uuid-2"

        t3 = MagicMock()
        t3.id = "team-obj-id-3"
        t3.uuid = "team-uuid-3"

        mock_membership_find = MagicMock()
        mock_membership_find.to_list = AsyncMock(return_value=[m1, m2, m3])

        mock_team_find = MagicMock()
        mock_team_find.to_list = AsyncMock(return_value=[t1, t2, t3])

        with (
            patch("app.services.access_control.TeamMembership") as MockTM,
            patch("app.services.access_control.Team") as MockTeam,
        ):
            MockTM.find.return_value = mock_membership_find
            MockTM.user_id = "user_id"
            MockTeam.find.return_value = mock_team_find

            result = await get_team_access_context(user)

        assert result.team_uuids == {"team-uuid-1", "team-uuid-2", "team-uuid-3"}
        assert result.team_object_ids == {"team-obj-id-1", "team-obj-id-2", "team-obj-id-3"}
        assert result.roles_by_uuid == {
            "team-uuid-1": "owner",
            "team-uuid-2": "member",
            "team-uuid-3": "admin",
        }
        assert result.roles_by_object_id == {
            "team-obj-id-1": "owner",
            "team-obj-id-2": "member",
            "team-obj-id-3": "admin",
        }


# ---------------------------------------------------------------------------
# TestGetAuthorizedFolder
# ---------------------------------------------------------------------------


class TestGetAuthorizedFolder:
    async def test_not_found_returns_none(self):
        user = _make_user("user1")

        with patch(
            "app.services.access_control.SmartFolder"
        ) as MockFolder:
            MockFolder.find_one = AsyncMock(return_value=None)
            MockFolder.uuid = "uuid"

            result = await get_authorized_folder("missing-uuid", user)

        assert result is None

    async def test_unauthorized_returns_none(self):
        user = _make_user("outsider")
        folder = _make_folder("owner1", team_id="team-abc")

        access = _team_access()  # no team membership

        with patch(
            "app.services.access_control.SmartFolder"
        ) as MockFolder:
            MockFolder.find_one = AsyncMock(return_value=folder)
            MockFolder.uuid = "uuid"

            result = await get_authorized_folder(
                "folder-uuid", user, team_access=access
            )

        assert result is None

    async def test_authorized_returns_folder(self):
        user = _make_user("owner1")
        folder = _make_folder("owner1", team_id=None)

        access = _team_access()

        with patch(
            "app.services.access_control.SmartFolder"
        ) as MockFolder:
            MockFolder.find_one = AsyncMock(return_value=folder)
            MockFolder.uuid = "uuid"

            result = await get_authorized_folder(
                "folder-uuid", user, team_access=access
            )

        assert result is folder

    async def test_manage_mode_checks_manage_permission(self):
        """A team member can view but not manage; manage=True should deny."""
        user = _make_user("member1")
        folder = _make_folder("owner1", team_id="team-abc")

        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "member"},
        )

        with patch(
            "app.services.access_control.SmartFolder"
        ) as MockFolder:
            MockFolder.find_one = AsyncMock(return_value=folder)
            MockFolder.uuid = "uuid"

            # View should succeed
            result_view = await get_authorized_folder(
                "folder-uuid", user, team_access=access
            )
            assert result_view is folder

            # Manage should fail (member role)
            result_manage = await get_authorized_folder(
                "folder-uuid", user, manage=True, team_access=access
            )
            assert result_manage is None


# ---------------------------------------------------------------------------
# TestGetAuthorizedDocument
# ---------------------------------------------------------------------------


class TestGetAuthorizedDocument:
    async def test_not_found_returns_none(self):
        user = _make_user("user1")

        with patch(
            "app.services.access_control.SmartDocument"
        ) as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=None)
            MockDoc.uuid = "uuid"

            result = await get_authorized_document("missing-uuid", user)

        assert result is None

    async def test_unauthorized_returns_none(self):
        user = _make_user("outsider")
        doc = _make_document("owner1", team_id="team-abc")

        access = _team_access()

        with patch(
            "app.services.access_control.SmartDocument"
        ) as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=doc)
            MockDoc.uuid = "uuid"

            result = await get_authorized_document(
                "doc-uuid", user, team_access=access
            )

        assert result is None

    async def test_authorized_returns_document(self):
        user = _make_user("owner1")
        doc = _make_document("owner1")

        access = _team_access()

        with patch(
            "app.services.access_control.SmartDocument"
        ) as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=doc)
            MockDoc.uuid = "uuid"

            result = await get_authorized_document(
                "doc-uuid", user, team_access=access
            )

        assert result is doc

    async def test_manage_mode_checks_manage_permission(self):
        """A team member can view but not manage a team document."""
        user = _make_user("member1")
        doc = _make_document("owner1", team_id="team-abc")

        access = _team_access(
            team_uuids={"team-abc"},
            roles={"team-abc": "member"},
        )

        with patch(
            "app.services.access_control.SmartDocument"
        ) as MockDoc:
            MockDoc.find_one = AsyncMock(return_value=doc)
            MockDoc.uuid = "uuid"

            result_view = await get_authorized_document(
                "doc-uuid", user, team_access=access
            )
            assert result_view is doc

            result_manage = await get_authorized_document(
                "doc-uuid", user, manage=True, team_access=access
            )
            assert result_manage is None


# ---------------------------------------------------------------------------
# TestGetAuthorizedWorkflow
# ---------------------------------------------------------------------------


class TestGetAuthorizedWorkflow:
    async def test_not_found_returns_none(self):
        user = _make_user("user1")

        with patch(
            "app.services.access_control.get_team_access_context",
            new_callable=AsyncMock,
        ) as mock_ctx:
            mock_ctx.return_value = _team_access()

            with (
                patch(
                    "app.models.workflow.Workflow"
                ) as MockWF,
                patch(
                    "beanie.PydanticObjectId",
                    side_effect=lambda x: x,
                ),
            ):
                MockWF.get = AsyncMock(return_value=None)

                result = await get_authorized_workflow("nonexistent-id", user)

        assert result is None

    async def test_unauthorized_returns_none(self):
        user = _make_user("outsider")
        wf = _make_workflow("owner1", team_id="team-abc")

        access = _team_access()

        with (
            patch("app.models.workflow.Workflow") as MockWF,
            patch("beanie.PydanticObjectId", side_effect=lambda x: x),
        ):
            MockWF.get = AsyncMock(return_value=wf)

            result = await get_authorized_workflow(
                "wf-id", user, team_access=access
            )

        assert result is None

    async def test_authorized_returns_workflow(self):
        user = _make_user("owner1")
        wf = _make_workflow("owner1", team_id=None)

        access = _team_access()

        with (
            patch("app.models.workflow.Workflow") as MockWF,
            patch("beanie.PydanticObjectId", side_effect=lambda x: x),
        ):
            MockWF.get = AsyncMock(return_value=wf)

            result = await get_authorized_workflow(
                "wf-id", user, team_access=access
            )

        assert result is wf

    async def test_verified_library_access_can_authorize_workflow(self):
        user = _make_user("viewer")
        wf = _make_workflow("owner1", team_id=None)
        wf.id = "workflow-oid"

        with (
            patch("app.models.workflow.Workflow") as MockWF,
            patch("beanie.PydanticObjectId", side_effect=lambda x: x),
            patch(
                "app.services.access_control.has_library_backed_object_access",
                new_callable=AsyncMock,
            ) as mock_library_access,
        ):
            MockWF.get = AsyncMock(return_value=wf)
            mock_library_access.return_value = True

            result = await get_authorized_workflow("wf-id", user, team_access=_team_access())

        assert result is wf

    async def test_invalid_id_returns_none(self):
        """If PydanticObjectId raises, the function catches and returns None."""
        user = _make_user("user1")

        with (
            patch(
                "app.models.workflow.Workflow"
            ) as MockWF,
            patch(
                "beanie.PydanticObjectId",
                side_effect=Exception("invalid id"),
            ),
        ):
            MockWF.get = AsyncMock()

            result = await get_authorized_workflow("bad-id", user)

        assert result is None


# ---------------------------------------------------------------------------
# TestGetAuthorizedSearchSet
# ---------------------------------------------------------------------------


class TestGetAuthorizedSearchSet:
    async def test_not_found_returns_none(self):
        user = _make_user("user1")

        with patch(
            "app.models.search_set.SearchSet"
        ) as MockSS:
            MockSS.find_one = AsyncMock(return_value=None)
            MockSS.uuid = "uuid"

            result = await get_authorized_search_set("missing-uuid", user)

        assert result is None

    async def test_unauthorized_returns_none(self):
        user = _make_user("outsider")
        ss = _make_search_set("owner1", is_global=False)

        with (
            patch("app.models.search_set.SearchSet") as MockSS,
            patch(
                "app.services.access_control.get_team_access_context",
                new_callable=AsyncMock,
            ) as mock_ctx,
        ):
            mock_ctx.return_value = _team_access()
            MockSS.find_one = AsyncMock(return_value=ss)
            MockSS.uuid = "uuid"

            result = await get_authorized_search_set("ss-uuid", user)

        assert result is None

    async def test_authorized_returns_search_set(self):
        user = _make_user("owner1")
        ss = _make_search_set("owner1")

        with patch(
            "app.models.search_set.SearchSet"
        ) as MockSS:
            MockSS.find_one = AsyncMock(return_value=ss)
            MockSS.uuid = "uuid"

            result = await get_authorized_search_set("ss-uuid", user)

        assert result is ss

    async def test_global_search_set_viewable_by_non_owner(self):
        user = _make_user("random-user")
        ss = _make_search_set("owner1", is_global=True)

        with patch(
            "app.models.search_set.SearchSet"
        ) as MockSS:
            MockSS.find_one = AsyncMock(return_value=ss)
            MockSS.uuid = "uuid"

            result = await get_authorized_search_set("ss-uuid", user)

        assert result is ss

    async def test_global_search_set_not_manageable_by_non_owner(self):
        user = _make_user("random-user")
        ss = _make_search_set("owner1", is_global=True)

        with (
            patch("app.models.search_set.SearchSet") as MockSS,
            patch(
                "app.services.access_control.get_team_access_context",
                new_callable=AsyncMock,
            ) as mock_ctx,
        ):
            mock_ctx.return_value = _team_access()
            MockSS.find_one = AsyncMock(return_value=ss)
            MockSS.uuid = "uuid"

            result = await get_authorized_search_set(
                "ss-uuid", user, manage=True
            )

        assert result is None

    async def test_library_backed_access_can_authorize_search_set(self):
        user = _make_user("viewer")
        ss = _make_search_set("owner1", is_global=False)
        ss.id = "search-set-oid"

        with (
            patch("app.models.search_set.SearchSet") as MockSS,
            patch(
                "app.services.access_control.get_team_access_context",
                new_callable=AsyncMock,
            ) as mock_ctx,
            patch(
                "app.services.access_control.has_library_backed_object_access",
                new_callable=AsyncMock,
            ) as mock_library_access,
        ):
            mock_ctx.return_value = _team_access()
            MockSS.find_one = AsyncMock(return_value=ss)
            MockSS.uuid = "uuid"
            mock_library_access.return_value = True

            result = await get_authorized_search_set("ss-uuid", user)

        assert result is ss
