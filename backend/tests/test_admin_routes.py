"""Route tests for admin analytics scoping."""

import datetime
import secrets
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _make_user(
    user_id: str = "team-admin",
    *,
    is_admin: bool = False,
    is_examiner: bool = False,
    current_team: str | None = None,
):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.name = "Test User"
    user.is_admin = is_admin
    user.is_staff = False
    user.is_examiner = is_examiner
    user.current_team = current_team
    user.is_demo_user = False
    user.token_version = 0
    user.demo_status = None
    return user


def _auth(user_id: str = "team-admin"):
    token = create_access_token(user_id, _TEST_SETTINGS)
    csrf = secrets.token_urlsafe(32)
    return {"access_token": token, "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


class TestAdminAnalyticsScoping:
    @pytest.mark.asyncio
    async def test_non_admin_rejected(self, client):
        user = _make_user("testuser", is_admin=False)
        cookies, headers = _auth("testuser")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.TeamMembership") as MockTM,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockTM.find_one = AsyncMock(return_value=None)
            resp = await client.get("/api/admin/usage", cookies=cookies, headers=headers)

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_allowed(self, client):
        user = _make_user("testuser", is_admin=True)
        cookies, headers = _auth("testuser")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.ActivityEvent") as MockActivity,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mock_find = MagicMock()
            mock_find.to_list = AsyncMock(return_value=[])
            MockActivity.find = MagicMock(return_value=mock_find)
            MockActivity.find_one = AsyncMock(return_value=None)

            resp = await client.get("/api/admin/usage", cookies=cookies, headers=headers)

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_examiner_cannot_access_admin_dashboard(self, client):
        user = _make_user("testuser", is_examiner=True, is_admin=False)
        cookies, headers = _auth("testuser")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.TeamMembership") as MockTM,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockTM.find_one = AsyncMock(return_value=None)
            resp = await client.get("/api/admin/usage", cookies=cookies, headers=headers)

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_rejected(self, client):
        resp = await client.get("/api/admin/usage")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_examiner_cannot_access_user_leaderboard(self, client):
        user = _make_user("testuser", is_examiner=True, is_admin=False)
        cookies, headers = _auth("testuser")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.TeamMembership") as MockTM,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            MockTM.find_one = AsyncMock(return_value=None)
            resp = await client.get("/api/admin/users", cookies=cookies, headers=headers)

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_team_admin_user_leaderboard_hides_platform_role_flags(self, client):
        team_admin = _make_user("team-admin", current_team="0123456789abcdef01234567")
        cookies, headers = _auth("team-admin")
        team = SimpleNamespace(
            id="0123456789abcdef01234567",
            uuid="team-uuid",
            name="Team One",
        )
        activity_event = SimpleNamespace(
            user_id="member-1",
            tokens_input=5,
            tokens_output=7,
            type="workflow_run",
            started_at=None,
        )
        team_membership = SimpleNamespace(user_id="member-1")
        target_user = SimpleNamespace(
            user_id="member-1",
            name="Member One",
            email="member-1@example.com",
            is_admin=True,
            is_examiner=True,
        )

        activity_find = MagicMock()
        activity_find.to_list = AsyncMock(return_value=[activity_event])
        memberships_find = MagicMock()
        memberships_find.to_list = AsyncMock(return_value=[team_membership])
        users_find = MagicMock()
        users_find.to_list = AsyncMock(return_value=[target_user])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.admin._require_admin_or_team_admin",
                new=AsyncMock(return_value=(team_admin, "0123456789abcdef01234567")),
            ),
            patch("app.routers.admin.Team") as MockTeam,
            patch("app.routers.admin.ActivityEvent") as MockActivityEvent,
            patch("app.routers.admin.TeamMembership") as MockTeamMembership,
            patch("app.routers.admin.User") as MockRouteUser,
        ):
            MockUser.find_one = AsyncMock(return_value=team_admin)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockActivityEvent.find.return_value = activity_find
            MockTeamMembership.find.return_value = memberships_find
            MockRouteUser.find.return_value = users_find

            resp = await client.get("/api/admin/users", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()["items"]
        assert len(data) == 1
        assert data[0]["user_id"] == "member-1"
        assert data[0]["is_admin"] is False
        assert data[0]["is_examiner"] is False

    @pytest.mark.asyncio
    async def test_team_admin_user_detail_scopes_document_count_and_hides_platform_role_flags(self, client):
        team_admin = _make_user("team-admin", current_team="0123456789abcdef01234567")
        cookies, headers = _auth("team-admin")
        target_user = SimpleNamespace(
            user_id="member-1",
            name="Member One",
            email="member-1@example.com",
            is_admin=True,
            is_examiner=True,
        )
        team = SimpleNamespace(id="team-object-id", uuid="team-uuid", name="Team One")

        events_find = MagicMock()
        events_find.to_list = AsyncMock(return_value=[])
        recent_find = MagicMock()
        recent_find.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
        documents_find = MagicMock()
        documents_find.count = AsyncMock(return_value=3)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.admin._require_admin_or_team_admin",
                new=AsyncMock(return_value=(team_admin, "0123456789abcdef01234567")),
            ),
            patch("app.routers.admin.TeamMembership") as MockTeamMembership,
            patch("app.routers.admin.Team") as MockTeam,
            patch("app.routers.admin.User") as MockRouteUser,
            patch("app.routers.admin.ActivityEvent") as MockActivityEvent,
            patch("app.routers.admin.SmartDocument") as MockSmartDocument,
        ):
            MockUser.find_one = AsyncMock(return_value=team_admin)
            MockTeamMembership.find_one = AsyncMock(return_value=SimpleNamespace(user_id="member-1"))
            MockTeam.find_one = AsyncMock(return_value=team)
            MockRouteUser.find_one = AsyncMock(return_value=target_user)
            MockActivityEvent.find.side_effect = [events_find, recent_find]
            MockSmartDocument.find.return_value = documents_find

            resp = await client.get("/api/admin/users/member-1/detail", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_admin"] is False
        assert data["is_examiner"] is False
        assert data["document_count"] == 3
        query = MockSmartDocument.find.call_args.args[0]
        assert query["user_id"] == "member-1"
        assert query["team_id"]["$in"] == [
            "0123456789abcdef01234567",
            "team-object-id",
            "team-uuid",
        ]

    @pytest.mark.asyncio
    async def test_team_detail_counts_only_team_scoped_documents(self, client):
        team_admin = _make_user("team-admin", current_team="0123456789abcdef01234567")
        cookies, headers = _auth("team-admin")
        team = SimpleNamespace(id="team-object-id", uuid="team-uuid", name="Team One")
        team_membership = SimpleNamespace(user_id="member-1", role="admin")
        target_user = SimpleNamespace(user_id="member-1", name="Member One", email="member-1@example.com")

        events_find = MagicMock()
        events_find.to_list = AsyncMock(return_value=[])
        recent_find = MagicMock()
        recent_find.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
        memberships_find = MagicMock()
        memberships_find.to_list = AsyncMock(return_value=[team_membership])
        users_find = MagicMock()
        users_find.to_list = AsyncMock(return_value=[target_user])
        documents_find = MagicMock()
        documents_find.count = AsyncMock(return_value=7)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.admin._require_admin_or_team_admin",
                new=AsyncMock(return_value=(team_admin, "0123456789abcdef01234567")),
            ),
            patch("app.routers.admin.Team") as MockTeam,
            patch("app.routers.admin.TeamMembership") as MockTeamMembership,
            patch("app.routers.admin.User") as MockRouteUser,
            patch("app.routers.admin.ActivityEvent") as MockActivityEvent,
            patch("app.routers.admin.SmartDocument") as MockSmartDocument,
        ):
            MockUser.find_one = AsyncMock(return_value=team_admin)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTeamMembership.find.return_value = memberships_find
            MockRouteUser.find.return_value = users_find
            MockActivityEvent.find.side_effect = [events_find, recent_find]
            MockSmartDocument.find.return_value = documents_find

            resp = await client.get(
                "/api/admin/teams/0123456789abcdef01234567/detail",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["document_count"] == 7
        query = MockSmartDocument.find.call_args.args[0]
        assert query["team_id"]["$in"] == [
            "0123456789abcdef01234567",
            "team-object-id",
            "team-uuid",
        ]

    @pytest.mark.asyncio
    async def test_team_admin_usage_stats_queries_both_team_identifiers(self, client):
        team_admin = _make_user("team-admin", current_team="0123456789abcdef01234567")
        cookies, headers = _auth("team-admin")
        team = SimpleNamespace(
            id="0123456789abcdef01234567",
            uuid="team-uuid",
            name="Team One",
        )
        events_find = MagicMock()
        events_find.to_list = AsyncMock(return_value=[])

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.admin._require_admin_or_team_admin",
                new=AsyncMock(return_value=(team_admin, "0123456789abcdef01234567")),
            ),
            patch("app.routers.admin.Team") as MockTeam,
            patch("app.routers.admin.ActivityEvent") as MockActivityEvent,
        ):
            MockUser.find_one = AsyncMock(return_value=team_admin)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockActivityEvent.find.return_value = events_find

            resp = await client.get("/api/admin/usage", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        query = MockActivityEvent.find.call_args.args[0]
        assert query["team_id"]["$in"] == [
            "0123456789abcdef01234567",
            "team-uuid",
        ]

    @pytest.mark.asyncio
    async def test_team_admin_can_view_own_team_detail_by_uuid(self, client):
        team_admin = _make_user("team-admin", current_team="0123456789abcdef01234567")
        cookies, headers = _auth("team-admin")
        team = SimpleNamespace(
            id="0123456789abcdef01234567",
            uuid="team-uuid",
            name="Team One",
        )
        team_membership = SimpleNamespace(user_id="member-1", role="admin")
        target_user = SimpleNamespace(
            user_id="member-1",
            name="Member One",
            email="member-1@example.com",
        )

        events_find = MagicMock()
        events_find.to_list = AsyncMock(return_value=[])
        recent_find = MagicMock()
        recent_find.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
        memberships_find = MagicMock()
        memberships_find.to_list = AsyncMock(return_value=[team_membership])
        users_find = MagicMock()
        users_find.to_list = AsyncMock(return_value=[target_user])
        documents_find = MagicMock()
        documents_find.count = AsyncMock(return_value=0)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.admin._require_admin_or_team_admin",
                new=AsyncMock(return_value=(team_admin, "0123456789abcdef01234567")),
            ),
            patch("app.routers.admin.Team") as MockTeam,
            patch("app.routers.admin.TeamMembership") as MockTeamMembership,
            patch("app.routers.admin.User") as MockRouteUser,
            patch("app.routers.admin.ActivityEvent") as MockActivityEvent,
            patch("app.routers.admin.SmartDocument") as MockSmartDocument,
        ):
            MockUser.find_one = AsyncMock(return_value=team_admin)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockTeamMembership.find.return_value = memberships_find
            MockRouteUser.find.return_value = users_find
            MockActivityEvent.find.side_effect = [events_find, recent_find]
            MockSmartDocument.find.return_value = documents_find

            resp = await client.get(
                "/api/admin/teams/team-uuid/detail",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        event_query = MockActivityEvent.find.call_args_list[0].args[0]
        recent_query = MockActivityEvent.find.call_args_list[1].args[0]
        assert event_query["team_id"]["$in"] == [
            "0123456789abcdef01234567",
            "team-uuid",
        ]
        assert recent_query["team_id"]["$in"] == [
            "0123456789abcdef01234567",
            "team-uuid",
        ]


class TestAdminListEndpointLimits:
    """Plan 012: the five previously-unbounded admin list endpoints now accept
    a `limit` and report `total`/`capped`. Exercised against the user
    leaderboard (GET /users), which has the richest scoping logic of the five;
    the other four share the same "scope via find(), then slice" shape.
    """

    @pytest.mark.asyncio
    async def test_more_rows_than_limit_caps_and_reports_true_total(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")

        events = [
            SimpleNamespace(user_id="user-1", tokens_input=100, tokens_output=0, type="workflow_run", started_at=None),
            SimpleNamespace(user_id="user-2", tokens_input=50, tokens_output=0, type="workflow_run", started_at=None),
            SimpleNamespace(user_id="user-3", tokens_input=10, tokens_output=0, type="workflow_run", started_at=None),
        ]
        users = [
            SimpleNamespace(user_id=e.user_id, name=e.user_id, email=f"{e.user_id}@example.com", is_admin=False, is_staff=False, is_examiner=False)
            for e in events
        ]

        activity_find = MagicMock()
        activity_find.to_list = AsyncMock(return_value=events)
        users_find = MagicMock()
        users_find.limit.return_value.to_list = AsyncMock(return_value=users)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.ActivityEvent") as MockActivityEvent,
            patch("app.routers.admin.User") as MockRouteUser,
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockActivityEvent.find.return_value = activity_find
            MockRouteUser.find.return_value = users_find

            resp = await client.get("/api/admin/users?limit=2", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["capped"] is True
        assert len(body["items"]) == 2
        # Sorted desc by tokens_total — the two highest survive the cap.
        assert [i["user_id"] for i in body["items"]] == ["user-1", "user-2"]

    @pytest.mark.asyncio
    async def test_fewer_rows_than_limit_not_capped(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")

        events = [
            SimpleNamespace(user_id="user-1", tokens_input=10, tokens_output=0, type="workflow_run", started_at=None),
        ]
        users = [
            SimpleNamespace(user_id="user-1", name="User One", email="user-1@example.com", is_admin=False, is_staff=False, is_examiner=False),
        ]

        activity_find = MagicMock()
        activity_find.to_list = AsyncMock(return_value=events)
        users_find = MagicMock()
        users_find.limit.return_value.to_list = AsyncMock(return_value=users)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.ActivityEvent") as MockActivityEvent,
            patch("app.routers.admin.User") as MockRouteUser,
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockActivityEvent.find.return_value = activity_find
            MockRouteUser.find.return_value = users_find

            resp = await client.get("/api/admin/users", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["capped"] is False
        assert len(body["items"]) == 1
        assert body["items"][0]["user_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_limit_above_max_list_limit_rejected(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            resp = await client.get("/api/admin/users?limit=2001", cookies=cookies, headers=headers)

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_team_scoped_cap_never_widens_visibility_identity_check(self, client):
        """A limit small enough to truncate the response must still only ever
        surface rows the team-scoped caller is entitled to see. Guards against
        a regression where `limit` is applied before (rather than after) the
        team-scope filter — that would be a data-exposure bug, not a perf one.
        """
        team_admin = _make_user("team-admin", current_team="0123456789abcdef01234567")
        cookies, headers = _auth("team-admin")
        team = SimpleNamespace(id="0123456789abcdef01234567", uuid="team-uuid", name="Team One")

        events = [
            SimpleNamespace(user_id="member-1", tokens_input=100, tokens_output=0, type="workflow_run", started_at=None),
            SimpleNamespace(user_id="member-2", tokens_input=10, tokens_output=0, type="workflow_run", started_at=None),
        ]
        team_memberships = [
            SimpleNamespace(user_id="member-1"),
            SimpleNamespace(user_id="member-2"),
        ]
        users = [
            SimpleNamespace(user_id="member-1", name="Member One", email="member-1@example.com", is_admin=False, is_examiner=False),
            SimpleNamespace(user_id="member-2", name="Member Two", email="member-2@example.com", is_admin=False, is_examiner=False),
        ]

        activity_find = MagicMock()
        activity_find.to_list = AsyncMock(return_value=events)
        memberships_find = MagicMock()
        memberships_find.to_list = AsyncMock(return_value=team_memberships)
        users_find = MagicMock()
        users_find.to_list = AsyncMock(return_value=users)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "team-admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch(
                "app.routers.admin._require_admin_or_team_admin",
                new=AsyncMock(return_value=(team_admin, "0123456789abcdef01234567")),
            ),
            patch("app.routers.admin.Team") as MockTeam,
            patch("app.routers.admin.ActivityEvent") as MockActivityEvent,
            patch("app.routers.admin.TeamMembership") as MockTeamMembership,
            patch("app.routers.admin.User") as MockRouteUser,
        ):
            MockUser.find_one = AsyncMock(return_value=team_admin)
            MockTeam.find_one = AsyncMock(return_value=team)
            MockActivityEvent.find.return_value = activity_find
            MockTeamMembership.find.return_value = memberships_find
            MockRouteUser.find.return_value = users_find

            resp = await client.get("/api/admin/users?limit=1", cookies=cookies, headers=headers)

        assert resp.status_code == 200

        # The query issued to ActivityEvent still carries the team scope
        # filter regardless of the limit — the cap never substitutes for it.
        query = MockActivityEvent.find.call_args.args[0]
        assert query["team_id"]["$in"] == ["0123456789abcdef01234567", "team-uuid"]

        body = resp.json()
        assert body["total"] == 2
        assert body["capped"] is True
        assert len(body["items"]) == 1
        # Identity, not just count: the single surviving row must be the
        # in-scope member with the higher token total — never a row that
        # slipped in ahead of, or instead of, the scope filter.
        assert body["items"][0]["user_id"] == "member-1"


class TestUserActivityHistory:
    """The per-user audit drill-down (GET /users/{id}/history)."""

    @staticmethod
    def _activity_query_mock(events):
        find = MagicMock()
        find.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=events)
        return find

    @pytest.mark.asyncio
    async def test_staff_without_admin_rejected(self, client):
        """Super-admin only: is_staff (require_admin elsewhere) must get 403."""
        user = _make_user("staffer", is_admin=False)
        user.is_staff = True
        cookies, headers = _auth("staffer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "staffer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.get("/api/admin/users/member-1/history", cookies=cookies, headers=headers)

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_merges_and_sorts_newest_first(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")

        t1 = datetime.datetime(2026, 1, 1, 9, 0, 0)   # oldest  (activity)
        t2 = datetime.datetime(2026, 1, 1, 10, 0, 0)  # middle  (audit)
        t3 = datetime.datetime(2026, 1, 1, 11, 0, 0)  # newest  (activity)

        audit_entry = SimpleNamespace(
            timestamp=t2, action="user.login", resource_name=None,
            resource_type="user", resource_id="member-1",
            ip_address="10.0.0.1", detail={"method": "password"},
        )
        older_activity = SimpleNamespace(
            started_at=t1, type="conversation", title="Chat A", status="completed",
            id="act-1", tokens_input=1, tokens_output=2, steps_completed=0, steps_total=0, error=None,
        )
        newer_activity = SimpleNamespace(
            started_at=t3, type="workflow_run", title="WF B", status="failed",
            id="act-2", tokens_input=3, tokens_output=4, steps_completed=1, steps_total=2, error="boom",
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.User") as MockRouteUser,
            patch("app.routers.admin.audit_service") as MockAudit,
            patch("app.routers.admin.ActivityEvent") as MockActivity,
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockRouteUser.find_one = AsyncMock(
                return_value=SimpleNamespace(user_id="member-1", name="Member One", email="m1@example.com")
            )
            MockAudit.query_audit_log = AsyncMock(return_value=([audit_entry], 1))
            MockActivity.find.return_value = self._activity_query_mock([newer_activity, older_activity])

            resp = await client.get("/api/admin/users/member-1/history", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert data["capped"] is False
        # Newest-first across both sources.
        assert [it["source"] for it in data["items"]] == ["activity", "audit", "activity"]
        assert data["items"][0]["action"] == "workflow_run"
        assert data["items"][0]["status"] == "failed"
        assert data["items"][1]["action"] == "user.login"
        assert data["items"][1]["ip_address"] == "10.0.0.1"
        # The audit query was scoped to the target user.
        assert MockAudit.query_audit_log.call_args.kwargs["actor_user_id"] == "member-1"

    @pytest.mark.asyncio
    async def test_pagination_slices_merged_feed(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")

        events = [
            SimpleNamespace(
                started_at=datetime.datetime(2026, 1, 1, h, 0, 0), type="conversation",
                title=f"Chat {h}", status="completed", id=f"act-{h}",
                tokens_input=0, tokens_output=0, steps_completed=0, steps_total=0, error=None,
            )
            for h in range(5)
        ]

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.User") as MockRouteUser,
            patch("app.routers.admin.audit_service") as MockAudit,
            patch("app.routers.admin.ActivityEvent") as MockActivity,
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockRouteUser.find_one = AsyncMock(
                return_value=SimpleNamespace(user_id="member-1", name="M", email="m@example.com")
            )
            MockAudit.query_audit_log = AsyncMock(return_value=([], 0))
            MockActivity.find.return_value = self._activity_query_mock(events)

            resp = await client.get(
                "/api/admin/users/member-1/history?skip=2&limit=2", cookies=cookies, headers=headers
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        # Newest-first => hours 4,3,2,1,0; skip=2,limit=2 => hours 2 then 1.
        assert data["items"][0]["title"] == "Chat 2"
        assert data["items"][1]["title"] == "Chat 1"

    @pytest.mark.asyncio
    async def test_missing_user_returns_404(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.User") as MockRouteUser,
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockRouteUser.find_one = AsyncMock(return_value=None)
            resp = await client.get("/api/admin/users/ghost/history", cookies=cookies, headers=headers)

        assert resp.status_code == 404


class TestOcrConnectivityTest:
    """POST /api/admin/config/test-ocr — form-value overrides vs saved config."""

    def _httpx_client_mock(self, status_code=200):
        resp = MagicMock(status_code=status_code)
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx, client

    @pytest.mark.asyncio
    async def test_body_overrides_saved_endpoint_and_key(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        cfg = SimpleNamespace(
            ocr_endpoint="https://saved.example/ocr", ocr_api_key="enc-saved",
            ocr_provider="raw", ocr_async=False,
        )
        ctx, http_client = self._httpx_client_mock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("httpx.AsyncClient", return_value=ctx),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.post(
                "/api/admin/config/test-ocr",
                json={"ocr_endpoint": "https://form.example/ocr", "ocr_api_key": "new-key"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        url, kwargs = http_client.get.call_args[0][0], http_client.get.call_args[1]
        assert url == "https://form.example/ocr"
        assert kwargs["headers"]["Authorization"] == "Bearer new-key"

    @pytest.mark.asyncio
    async def test_masked_key_sentinel_uses_saved_key(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        cfg = SimpleNamespace(
            ocr_endpoint="https://saved.example/ocr", ocr_api_key="enc-saved",
            ocr_provider="raw", ocr_async=False,
        )
        ctx, http_client = self._httpx_client_mock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin.decrypt_value", return_value="saved-plain"),
            patch("httpx.AsyncClient", return_value=ctx),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.post(
                "/api/admin/config/test-ocr",
                json={"ocr_endpoint": "https://form.example/ocr", "ocr_api_key": "***"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert http_client.get.call_args[1]["headers"]["Authorization"] == "Bearer saved-plain"

    @pytest.mark.asyncio
    async def test_no_body_falls_back_to_saved_config(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        cfg = SimpleNamespace(
            ocr_endpoint="https://saved.example/ocr", ocr_api_key="",
            ocr_provider="raw", ocr_async=False,
        )
        ctx, http_client = self._httpx_client_mock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("httpx.AsyncClient", return_value=ctx),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.post(
                "/api/admin/config/test-ocr", cookies=cookies, headers=headers
            )

        assert resp.status_code == 200
        assert http_client.get.call_args[0][0] == "https://saved.example/ocr"
        assert "Authorization" not in http_client.get.call_args[1]["headers"]

    @pytest.mark.asyncio
    async def test_no_endpoint_anywhere_returns_400(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        cfg = SimpleNamespace(ocr_endpoint="", ocr_api_key="", ocr_provider="raw", ocr_async=False)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.post(
                "/api/admin/config/test-ocr", json={}, cookies=cookies, headers=headers
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_docling_probes_health_not_the_convert_path(self, client):
        # docling-serve's convert path only answers POSTs, so a GET against it
        # reports 405 and tells the admin nothing about their config.
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        cfg = SimpleNamespace(
            ocr_endpoint="", ocr_api_key="", ocr_provider="docling", ocr_async=False,
        )
        ctx, http_client = self._httpx_client_mock()

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("httpx.AsyncClient", return_value=ctx),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.post(
                "/api/admin/config/test-ocr",
                json={"ocr_endpoint": "https://docling.example.edu", "ocr_provider": "docling"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert http_client.get.call_args[0][0] == "https://docling.example.edu/health"
        # The message names the URL uploads will actually go to.
        assert "https://docling.example.edu/v1/convert/file" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_docling_unhealthy_probe_reports_warning(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        cfg = SimpleNamespace(
            ocr_endpoint="", ocr_api_key="", ocr_provider="docling", ocr_async=False,
        )
        ctx, _ = self._httpx_client_mock(status_code=404)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("httpx.AsyncClient", return_value=ctx),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.post(
                "/api/admin/config/test-ocr",
                json={"ocr_endpoint": "https://not-docling.example", "ocr_provider": "docling"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "warning"


class TestOcrProviderConfig:
    """PUT /api/admin/config — OCR provider/options validation."""

    def _config_stub(self):
        return SimpleNamespace(
            extraction_config={}, quality_config={}, compliance_config={},
            retention_config={}, ocr_endpoint="", ocr_api_key="", ocr_provider="raw",
            ocr_options={}, ocr_async=False, ocr_timeout_seconds=120,
            llm_endpoint="", default_team_id=None, support_contacts=[],
            updated_at=None, updated_by=None, save=AsyncMock(),
        )

    async def _put(self, client, body, cfg):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin._audit", new_callable=AsyncMock),
            patch("app.routers.admin.clear_agent_caches"),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            return await client.put(
                "/api/admin/config", json=body, cookies=cookies, headers=headers
            )

    @pytest.mark.asyncio
    async def test_docling_provider_and_options_persist(self, client):
        cfg = self._config_stub()
        options = {"do_ocr": True, "ocr_engine": "easyocr", "ocr_lang": ["en", "fr"]}

        resp = await self._put(client, {
            "ocr_provider": "docling", "ocr_options": options,
            "ocr_async": True, "ocr_timeout_seconds": 600,
        }, cfg)

        assert resp.status_code == 200
        assert cfg.ocr_provider == "docling"
        assert cfg.ocr_options == options
        assert cfg.ocr_async is True
        assert cfg.ocr_timeout_seconds == 600

    @pytest.mark.asyncio
    async def test_unknown_provider_is_rejected(self, client):
        cfg = self._config_stub()
        resp = await self._put(client, {"ocr_provider": "tesseract"}, cfg)

        assert resp.status_code == 400
        assert cfg.ocr_provider == "raw"

    @pytest.mark.asyncio
    async def test_out_of_range_timeout_is_rejected(self, client):
        cfg = self._config_stub()
        resp = await self._put(client, {"ocr_timeout_seconds": 5}, cfg)

        assert resp.status_code == 400
        assert cfg.ocr_timeout_seconds == 120


class TestUpdateAuthMethods:
    """PUT /api/admin/config/auth/methods must never persist an empty list —
    that disables every login path with no recovery except direct DB access.
    """

    @pytest.mark.asyncio
    async def test_empty_methods_rejected_and_config_unchanged(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        cfg = SimpleNamespace(auth_methods=["password"], save=AsyncMock())

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin._audit", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.put(
                "/api/admin/config/auth/methods",
                json={"methods": []},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 400
        assert cfg.auth_methods == ["password"]
        cfg.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_methods_persisted(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        cfg = SimpleNamespace(auth_methods=["password", "oauth"], save=AsyncMock())

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin._audit", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.put(
                "/api/admin/config/auth/methods",
                json={"methods": ["password"]},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert resp.json()["auth_methods"] == ["password"]
        assert cfg.auth_methods == ["password"]
        cfg.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_method_rejected(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            resp = await client.put(
                "/api/admin/config/auth/methods",
                json={"methods": ["telepathy"]},
                cookies=cookies,
                headers=headers,
            )

        assert 400 <= resp.status_code < 500

    @pytest.mark.asyncio
    async def test_non_superadmin_rejected_before_empty_check(self, client):
        """A non-superadmin sending an empty list must still get 403, not 400 —
        proving `_require_superadmin` runs before the new empty-list guard."""
        staffer = _make_user("staffer", is_admin=False)
        cookies, headers = _auth("staffer")

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "staffer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
        ):
            MockUser.find_one = AsyncMock(return_value=staffer)
            resp = await client.put(
                "/api/admin/config/auth/methods",
                json={"methods": []},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403


def _model(name: str, model_id: str | None = None, **overrides) -> dict:
    """Build a minimal available_models entry for tests."""
    entry = {
        "id": model_id,
        "name": name,
        "tag": name,
        "external": False,
        "thinking": False,
        "endpoint": "",
        "api_protocol": "",
        "api_key": "",
        "speed": "",
        "tier": "",
        "privacy": "",
        "supports_structured": True,
        "multimodal": False,
        "supports_pdf": False,
        "context_window": 128000,
        "request_timeout_seconds": None,
        "response_reserve_tokens": None,
        "cost_per_1m_input": None,
        "cost_per_1m_output": None,
    }
    entry.update(overrides)
    return entry


def _get_config_cfg(available_models: list[dict], oauth_providers: list[dict] | None = None) -> SimpleNamespace:
    """Build a fake SystemConfig with every attribute GET /config touches."""
    return SimpleNamespace(
        available_models=available_models,
        oauth_providers=oauth_providers or [],
        default_model="",
        auth_methods=["password"],
        ocr_endpoint="",
        ocr_api_key="",
        ocr_provider="raw",
        ocr_options={},
        ocr_async=False,
        ocr_timeout_seconds=120,
        llm_endpoint="",
        highlight_color="#eab308",
        ui_radius="12px",
        default_team_id="",
        support_contacts=[],
        get_extraction_config=lambda: {},
        get_quality_config=lambda: {},
        get_compliance_config=lambda: {},
        get_retention_config=lambda: {},
        save=AsyncMock(),
    )


class TestModelsAddressedById:
    """PUT/DELETE /api/admin/config/models/{model_id} — stable-id addressing.

    Regression coverage for the bug this plan fixes: the old routes addressed
    models by array position, so a shift in the list (e.g. another delete)
    could make a client's stale index land on the wrong model.
    """

    @pytest.mark.asyncio
    async def test_delete_by_id_survives_a_position_shift(self, client):
        """Seed three models, delete a different one first (shifting
        positions), then delete a specific model BY ID — the intended model
        must be gone and the other two must remain untouched. Under the old
        index scheme, deleting the second model after a prior delete removed
        whichever model happened to now sit at that position, not the one the
        admin actually clicked delete on."""
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        models = [
            _model("alpha", "id-alpha"),
            _model("bravo", "id-bravo"),
            _model("charlie", "id-charlie"),
        ]
        cfg = SimpleNamespace(
            available_models=models,
            oauth_providers=[],
            default_model="",
            save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin._audit", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)

            # Another admin (or tab) deletes "alpha" first — bravo/charlie
            # shift from positions 1/2 down to 0/1.
            resp1 = await client.delete(
                "/api/admin/config/models/id-alpha", cookies=cookies, headers=headers
            )
            assert resp1.status_code == 200

            # Now delete "bravo" BY ID. Under the old index scheme, a client
            # still holding index 1 (bravo's original position) would now hit
            # charlie instead.
            resp2 = await client.delete(
                "/api/admin/config/models/id-bravo", cookies=cookies, headers=headers
            )
            assert resp2.status_code == 200

        remaining_names = {m["name"] for m in cfg.available_models}
        assert remaining_names == {"charlie"}
        assert resp2.json()["removed"]["name"] == "bravo"

    @pytest.mark.asyncio
    async def test_unknown_model_id_returns_404(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        cfg = SimpleNamespace(
            available_models=[_model("alpha", "id-alpha")],
            oauth_providers=[],
            default_model="",
            save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin._audit", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.delete(
                "/api/admin/config/models/no-such-id", cookies=cookies, headers=headers
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_non_superadmin_rejected_before_lookup(self, client):
        """403 for a non-superadmin, proving `_require_superadmin` runs before
        the by-id lookup (and thus before any 404 could leak list contents)."""
        staffer = _make_user("staffer", is_admin=False)
        cookies, headers = _auth("staffer")
        cfg = SimpleNamespace(
            available_models=[_model("alpha", "id-alpha")],
            oauth_providers=[],
            default_model="",
            save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "staffer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
        ):
            MockUser.find_one = AsyncMock(return_value=staffer)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.delete(
                # Even a garbage id must still 403, not 404 — the auth check
                # must short-circuit before the list is ever searched.
                "/api/admin/config/models/whatever",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        cfg.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_lazy_backfill_assigns_ids_and_is_idempotent(self, client):
        """A config whose entries predate stable ids gains one on first touch,
        and calling the backfill again does not change already-assigned ids."""
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        legacy_models = [_model("alpha", None), _model("bravo", None)]
        # Simulate an already-untyped dict lacking the key entirely, not just None.
        del legacy_models[0]["id"]
        del legacy_models[1]["id"]
        cfg = _get_config_cfg(legacy_models)

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin.decrypt_value", return_value=""),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.get("/api/admin/config", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        ids_first = [m["id"] for m in resp.json()["available_models"]]
        assert all(ids_first)
        assert len(set(ids_first)) == 2  # unique
        cfg.save.assert_called_once()  # persisted the backfill

        # Calling again must not regenerate the now-assigned ids.
        cfg.save.reset_mock()
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin.decrypt_value", return_value=""),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp2 = await client.get("/api/admin/config", cookies=cookies, headers=headers)

        ids_second = [m["id"] for m in resp2.json()["available_models"]]
        assert ids_second == ids_first
        cfg.save.assert_not_called()  # nothing changed, so no persist needed

    @pytest.mark.asyncio
    async def test_update_by_id_preserves_key_on_sentinel(self, client):
        """The '***' API-key sentinel must still preserve the stored
        (encrypted) key when updating by id — plan 003 depends on this."""
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        models = [_model("alpha", "id-alpha", api_key="enc-stored-secret")]
        cfg = SimpleNamespace(
            available_models=models,
            oauth_providers=[],
            default_model="",
            save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin._audit", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.put(
                "/api/admin/config/models/id-alpha",
                json={"name": "alpha", "tag": "alpha", "api_key": "***"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert cfg.available_models[0]["api_key"] == "enc-stored-secret"
        assert cfg.available_models[0]["id"] == "id-alpha"

    @pytest.mark.asyncio
    async def test_update_preserves_unmanaged_keys(self, client):
        """#817: the form replaced the whole entry with a fixed dict literal,
        so every key it does not manage was destroyed on save — including the
        three the context budget reads. Editing a model's display tier must
        not silently reset how its tokens are counted."""
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        stored = _model("alpha", "id-alpha", api_key="enc-stored-secret")
        stored.update({
            "tokenizer_path": "/opt/tokenizers/llama-3",
            "tokenizer_cache_root": "/var/cache/hf",
            "token_safety_margin": 1.0,
            "some_future_key": "survives too",
        })
        cfg = SimpleNamespace(
            available_models=[stored],
            oauth_providers=[],
            default_model="",
            save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin._audit", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.put(
                "/api/admin/config/models/id-alpha",
                json={"name": "alpha", "tag": "alpha", "api_key": "***", "tier": "fast"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        saved = cfg.available_models[0]
        # The exact-count and margin controls survive...
        assert saved["tokenizer_path"] == "/opt/tokenizers/llama-3"
        assert saved["tokenizer_cache_root"] == "/var/cache/hf"
        assert saved["token_safety_margin"] == 1.0
        # ...as does anything else set out-of-band...
        assert saved["some_future_key"] == "survives too"
        # ...while the form's own fields still apply.
        assert saved["tier"] == "fast"
        assert saved["id"] == "id-alpha"

    @pytest.mark.asyncio
    async def test_update_preserves_fields_the_form_never_sends(self, client):
        """Same bug class as above, on keys that ARE in the request schema:
        ModelEditor never sends the cost rates, so writing them
        unconditionally reset out-of-band values to None and silently
        dropped Autovalidate's dollar estimates to tokens-only."""
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        stored = _model("alpha", "id-alpha", api_key="enc-stored-secret")
        stored.update({"cost_per_1m_input": 3.0, "cost_per_1m_output": 15.0})
        cfg = SimpleNamespace(
            available_models=[stored],
            oauth_providers=[],
            default_model="",
            save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin._audit", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.put(
                "/api/admin/config/models/id-alpha",
                # The payload ModelEditor actually posts: no cost fields.
                json={"name": "alpha", "tag": "alpha", "api_key": "***", "tier": "fast"},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        saved = cfg.available_models[0]
        assert saved["cost_per_1m_input"] == 3.0
        assert saved["cost_per_1m_output"] == 15.0

    @pytest.mark.asyncio
    async def test_explicit_null_still_clears_a_field(self, client):
        """Omitted means "keep"; explicitly null means "clear" — a form
        control that unsets a value must still work."""
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        stored = _model("alpha", "id-alpha", api_key="enc")
        stored["temperature"] = 0.7
        cfg = SimpleNamespace(
            available_models=[stored], oauth_providers=[],
            default_model="", save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin._audit", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.put(
                "/api/admin/config/models/id-alpha",
                json={"name": "alpha", "tag": "alpha", "api_key": "***", "temperature": None},
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 200
        assert cfg.available_models[0]["temperature"] is None

    @pytest.mark.asyncio
    async def test_delete_default_model_clears_default(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        models = [_model("alpha", "id-alpha"), _model("bravo", "id-bravo")]
        cfg = SimpleNamespace(
            available_models=models,
            oauth_providers=[],
            default_model="alpha",
            save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin._audit", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.delete(
                "/api/admin/config/models/id-alpha", cookies=cookies, headers=headers
            )

        assert resp.status_code == 200
        assert cfg.default_model == ""
        assert resp.json()["default_model"] == ""


class TestTestModelAddressedById:
    """POST /api/admin/config/test-model/{model_id} — stable-id addressing.

    Same class of bug TestModelsAddressedById covers for PUT/DELETE: the old
    route addressed the model to test by array position, so a shift in the
    list (e.g. another admin's delete) could silently run the connectivity
    test — and badge as "Connected" — against the wrong model's credentials.
    """

    @staticmethod
    def _patched_diagnostics():
        """Patch the pieces diagnose_model calls out to so it runs its real
        addressing/step logic without making a live model call."""
        fake_run = MagicMock()
        fake_run.output = "ok"
        fake_run.usage = lambda: SimpleNamespace(request_tokens=1, response_tokens=1, total_tokens=2)
        fake_agent = MagicMock()
        fake_agent.run = AsyncMock(return_value=fake_run)
        return (
            patch("app.services.system_diagnostics.get_agent_model", return_value=MagicMock()),
            patch("pydantic_ai.Agent", return_value=fake_agent),
            patch("app.services.system_diagnostics.decrypt_value", return_value="secret"),
        )

    @pytest.mark.asyncio
    async def test_test_by_id_survives_a_position_shift(self, client):
        """Seed three models, delete a different one first (shifting
        positions), then test a specific remaining model BY ID — the
        response must reflect that model, not whatever now sits at its old
        index. Under the old index scheme, testing "bravo" after "alpha" was
        deleted would have hit "charlie" instead."""
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        models = [
            _model("alpha", "id-alpha", api_key="enc-alpha", api_protocol="openai"),
            _model("bravo", "id-bravo", api_key="enc-bravo", api_protocol="openai"),
            _model("charlie", "id-charlie", api_key="enc-charlie", api_protocol="openai"),
        ]
        cfg = SimpleNamespace(
            available_models=models,
            oauth_providers=[],
            default_model="",
            save=AsyncMock(),
            model_dump=lambda: {"available_models": models},
        )

        p1, p2, p3 = self._patched_diagnostics()
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin._audit", new_callable=AsyncMock),
            p1, p2, p3,
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)

            # Another admin (or tab) deletes "alpha" first — bravo/charlie
            # shift from positions 1/2 down to 0/1.
            resp_delete = await client.delete(
                "/api/admin/config/models/id-alpha", cookies=cookies, headers=headers
            )
            assert resp_delete.status_code == 200

            # Test "bravo" BY ID. Under the old index scheme, a client still
            # holding index 1 (bravo's original position) would now hit
            # "charlie" (now at index 1 post-shift) instead.
            resp = await client.post(
                "/api/admin/config/test-model/id-bravo", cookies=cookies, headers=headers
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["model"] == "bravo"
        assert body["tag"] == "bravo"

    @pytest.mark.asyncio
    async def test_unknown_model_id_returns_404(self, client):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        cfg = SimpleNamespace(
            available_models=[_model("alpha", "id-alpha")],
            oauth_providers=[],
            default_model="",
            save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.post(
                "/api/admin/config/test-model/no-such-id", cookies=cookies, headers=headers
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_non_superadmin_rejected_before_lookup(self, client):
        """403 for a non-superadmin, proving `_require_superadmin` runs before
        the by-id lookup (and thus before any 404 could leak list contents)."""
        staffer = _make_user("staffer", is_admin=False)
        cookies, headers = _auth("staffer")
        cfg = SimpleNamespace(
            available_models=[_model("alpha", "id-alpha")],
            oauth_providers=[],
            default_model="",
            save=AsyncMock(),
        )

        with (
            patch("app.dependencies.decode_token", return_value={"sub": "staffer", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
        ):
            MockUser.find_one = AsyncMock(return_value=staffer)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            resp = await client.post(
                # Even a garbage id must still 403, not 404 — the auth check
                # must short-circuit before the list is ever searched.
                "/api/admin/config/test-model/whatever",
                cookies=cookies,
                headers=headers,
            )

        assert resp.status_code == 403
        # The config (and thus the model list) must never even be loaded —
        # proof the superadmin check ran first, not just that nothing saved.
        MockCfg.get_config.assert_not_called()


class TestModelIdentityUniqueness:
    """POST/PUT /api/admin/config/models — model names and tags stay unambiguous.

    Resolution scans names then tags and returns the first match, so a shared
    tag makes a user's stored selector resolve to whichever model happens to be
    first in the list.
    """

    def _cfg(self, *pairs):
        # Models carry pre-set ids so _ensure_config_ids has nothing to
        # backfill — otherwise it would call cfg.save() itself and break the
        # save.assert_not_awaited() assertions on the rejection paths.
        return SimpleNamespace(
            available_models=[{"id": f"id-{n}", "name": n, "tag": t} for n, t in pairs],
            oauth_providers=[],
            default_model="",
            updated_at=None,
            updated_by=None,
            save=AsyncMock(),
        )

    async def _call(self, client, cfg, method, url, body):
        admin = _make_user("admin", is_admin=True)
        cookies, headers = _auth("admin")
        with (
            patch("app.dependencies.decode_token", return_value={"sub": "admin", "type": "access"}),
            patch("app.dependencies.User") as MockUser,
            patch("app.routers.admin.SystemConfig") as MockCfg,
            patch("app.routers.admin.encrypt_value", side_effect=lambda v: v),
            patch("app.routers.admin.clear_agent_caches"),
            patch("app.routers.admin._audit", new_callable=AsyncMock),
        ):
            MockUser.find_one = AsyncMock(return_value=admin)
            MockCfg.get_config = AsyncMock(return_value=cfg)
            return await getattr(client, method)(
                url, json=body, cookies=cookies, headers=headers
            )

    @pytest.mark.asyncio
    async def test_adding_a_model_with_a_unique_identity_succeeds(self, client):
        cfg = self._cfg(("qwen-large", "local"))
        resp = await self._call(
            client, cfg, "post", "/api/admin/config/models",
            {"name": "gpt-oss", "tag": "fast"},
        )
        assert resp.status_code == 200
        assert len(cfg.available_models) == 2

    @pytest.mark.asyncio
    async def test_adding_a_model_with_a_duplicate_tag_is_rejected(self, client):
        cfg = self._cfg(("qwen-large", "local"))
        resp = await self._call(
            client, cfg, "post", "/api/admin/config/models",
            {"name": "gpt-oss", "tag": "local"},
        )
        assert resp.status_code == 409
        assert "local" in resp.json()["detail"]
        # The colliding model must not have been persisted.
        assert len(cfg.available_models) == 1
        cfg.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_adding_a_model_whose_name_is_another_models_tag_is_rejected(self, client):
        cfg = self._cfg(("qwen-large", "local"))
        resp = await self._call(
            client, cfg, "post", "/api/admin/config/models",
            {"name": "local", "tag": "reasoning"},
        )
        assert resp.status_code == 409
        assert len(cfg.available_models) == 1

    @pytest.mark.asyncio
    async def test_updating_a_model_without_changing_its_identity_succeeds(self, client):
        cfg = self._cfg(("qwen-large", "local"), ("gpt-oss", "fast"))
        resp = await self._call(
            client, cfg, "put", "/api/admin/config/models/id-qwen-large",
            {"name": "qwen-large", "tag": "local", "context_window": 32768},
        )
        assert resp.status_code == 200
        assert cfg.available_models[0]["context_window"] == 32768

    @pytest.mark.asyncio
    async def test_updating_a_model_onto_another_models_tag_is_rejected(self, client):
        cfg = self._cfg(("qwen-large", "local"), ("gpt-oss", "fast"))
        resp = await self._call(
            client, cfg, "put", "/api/admin/config/models/id-qwen-large",
            {"name": "qwen-large", "tag": "fast"},
        )
        assert resp.status_code == 409
        # The original row must survive untouched.
        assert cfg.available_models[0]["tag"] == "local"
        cfg.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_model_id_is_rejected_before_identity(self, client):
        cfg = self._cfg(("qwen-large", "local"))
        resp = await self._call(
            client, cfg, "put", "/api/admin/config/models/no-such-id",
            {"name": "gpt-oss", "tag": "fast"},
        )
        assert resp.status_code == 404
