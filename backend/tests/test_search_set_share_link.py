"""A Skill or extraction's share link.

"Copy share link" on a Skill made a link that only worked for people who could
already open the Skill, while saying "Share it with anyone". The link now
carries a token: someone signed in who opens it is recorded on the item and
can view and use it, never edit it. Turning the link off removes them.
"""

import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.models.search_set import SearchSet
from app.services.access_control import can_manage_search_set, can_view_search_set
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")
TOKEN = "tok-" + "a" * 40


def _user(user_id="outsider"):
    user = MagicMock()
    user.id = "fake-id"
    user.user_id = user_id
    user.email = f"{user_id}@example.com"
    user.is_admin = False
    user.is_examiner = False
    user.current_team = None
    user.is_demo_user = False
    user.token_version = 0
    user.demo_status = None
    return user


def _skill(**over):
    ss = MagicMock()
    ss.uuid = "skill-1"
    ss.title = "Award review"
    ss.set_type = "prompt"
    ss.user_id = "owner"
    ss.team_id = "team-1"
    ss.is_global = False
    ss.share_token = TOKEN
    ss.share_recipients = []
    ss.set = AsyncMock()
    ss.update = AsyncMock()
    for key, value in over.items():
        setattr(ss, key, value)
    return ss


def _auth(user_id):
    csrf = secrets.token_urlsafe(32)
    return {"access_token": create_access_token(user_id, _TEST_SETTINGS), "csrf_token": csrf}, {"X-CSRF-Token": csrf}


@pytest.fixture
async def client():
    with patch("app.main.init_db", new_callable=AsyncMock):
        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


def _signed_in(user):
    """Patches that make *user* the caller."""
    mock_user = patch("app.dependencies.User")
    return (
        patch("app.dependencies.decode_token", return_value={"sub": user.user_id, "type": "access"}),
        mock_user,
        patch("app.routers.extractions.audit_service.log_event", new_callable=AsyncMock),
    )


class TestViewRule:
    def test_someone_who_opened_the_link_can_view_but_not_manage(self):
        ss = _skill(share_recipients=["outsider"])
        assert can_view_search_set(ss, _user("outsider")) is True
        assert can_manage_search_set(ss, _user("outsider")) is False

    def test_others_still_cannot_view(self):
        ss = _skill(share_recipients=["outsider"])
        assert can_view_search_set(ss, _user("stranger")) is False

    def test_the_token_alone_grants_nothing(self):
        # Access comes from opening the link while signed in, not from the
        # item merely having a link.
        assert can_view_search_set(_skill(), _user("outsider")) is False

    def test_new_fields_default_to_no_link(self):
        fields = SearchSet.model_fields
        assert fields["share_token"].default is None
        assert fields["share_recipients"].default == []


class TestCreateLink:
    @pytest.mark.asyncio
    async def test_owner_gets_a_token_and_it_is_stable(self, client):
        user, ss = _user("owner"), _skill(share_token=None)
        cookies, headers = _auth("owner")
        decode, mock_user, audit = _signed_in(user)
        with decode, mock_user as MockUser, audit, patch(
            "app.routers.extractions.access_control.get_authorized_search_set", new_callable=AsyncMock, return_value=ss,
        ) as authz:
            MockUser.find_one = AsyncMock(return_value=user)
            first = await client.post("/api/extractions/search-sets/skill-1/share-token", cookies=cookies, headers=headers)
            second = await client.post("/api/extractions/search-sets/skill-1/share-token", cookies=cookies, headers=headers)

        assert first.status_code == 200
        token = first.json()["share_token"]
        assert len(token) >= 40
        assert second.json()["share_token"] == token
        ss.set.assert_awaited_once_with({"share_token": token})
        # Making a link is an edit-level action.
        assert authz.await_args.kwargs["manage"] is True

    @pytest.mark.asyncio
    async def test_someone_who_cannot_edit_gets_no_token(self, client):
        user = _user("member")
        cookies, headers = _auth("member")
        decode, mock_user, audit = _signed_in(user)
        with decode, mock_user as MockUser, audit, patch(
            "app.routers.extractions.access_control.get_authorized_search_set", new_callable=AsyncMock, return_value=None,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post("/api/extractions/search-sets/skill-1/share-token", cookies=cookies, headers=headers)

        assert resp.status_code == 404
        assert "share_token" not in resp.text


class TestOpenLink:
    async def _redeem(self, client, user, ss, token):
        cookies, headers = _auth(user.user_id)
        decode, mock_user, audit = _signed_in(user)
        with decode, mock_user as MockUser, audit, patch("app.routers.extractions.SearchSet") as MockSet:
            MockUser.find_one = AsyncMock(return_value=user)
            MockSet.find_one = AsyncMock(return_value=ss)
            return await client.post(
                "/api/extractions/search-sets/skill-1/share-token/redeem",
                json={"share_token": token}, cookies=cookies, headers=headers,
            )

    @pytest.mark.asyncio
    async def test_right_token_records_the_person(self, client):
        ss = _skill()
        resp = await self._redeem(client, _user("outsider"), ss, TOKEN)

        assert resp.status_code == 200
        assert resp.json() == {"uuid": "skill-1", "title": "Award review", "set_type": "prompt"}
        ss.update.assert_awaited_once_with({"$addToSet": {"share_recipients": "outsider"}})

    @pytest.mark.asyncio
    @pytest.mark.parametrize("token", ["wrong", TOKEN[:-1], TOKEN + "x", "ünïcode"])
    async def test_wrong_token_records_nobody(self, client, token):
        ss = _skill()
        resp = await self._redeem(client, _user("outsider"), ss, token)

        assert resp.status_code == 404
        ss.update.assert_not_awaited()
        assert "Award review" not in resp.text

    @pytest.mark.asyncio
    async def test_item_without_a_link_cannot_be_opened(self, client):
        # An empty token on the item must not match an empty token in a link.
        for stored in (None, ""):
            ss = _skill(share_token=stored)
            resp = await self._redeem(client, _user("outsider"), ss, stored or "")
            assert resp.status_code == 404
            ss.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_item_answers_like_a_wrong_token(self, client):
        missing = await self._redeem(client, _user("outsider"), None, TOKEN)
        wrong = await self._redeem(client, _user("outsider"), _skill(), "wrong")
        assert missing.status_code == wrong.status_code == 404
        assert missing.json() == wrong.json()

    @pytest.mark.asyncio
    async def test_owner_and_repeat_visits_are_not_recorded_again(self, client):
        ss = _skill()
        assert (await self._redeem(client, _user("owner"), ss, TOKEN)).status_code == 200
        ss.update.assert_not_awaited()

        ss = _skill(share_recipients=["outsider"])
        assert (await self._redeem(client, _user("outsider"), ss, TOKEN)).status_code == 200
        ss.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_signed_out_person_is_refused(self, client):
        csrf = secrets.token_urlsafe(32)
        resp = await client.post(
            "/api/extractions/search-sets/skill-1/share-token/redeem",
            json={"share_token": TOKEN}, cookies={"csrf_token": csrf}, headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 401


class TestTurnOff:
    @pytest.mark.asyncio
    async def test_turning_the_link_off_removes_the_token_and_everyone_it_let_in(self, client):
        user, ss = _user("owner"), _skill(share_recipients=["outsider", "another"])
        cookies, headers = _auth("owner")
        decode, mock_user, audit = _signed_in(user)
        with decode, mock_user as MockUser, audit, patch(
            "app.routers.extractions.access_control.get_authorized_search_set", new_callable=AsyncMock, return_value=ss,
        ) as authz:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.delete("/api/extractions/search-sets/skill-1/share-token", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        ss.set.assert_awaited_once_with({"share_token": None, "share_recipients": []})
        assert authz.await_args.kwargs["manage"] is True


class TestNotLeaked:
    def test_responses_and_exports_do_not_carry_the_link(self):
        from app.schemas.extractions import SearchSetResponse

        assert "share_token" not in SearchSetResponse.model_fields
        assert "share_recipients" not in SearchSetResponse.model_fields

    @pytest.mark.asyncio
    async def test_export_and_clone_start_without_a_link(self):
        import inspect

        from app.services import export_import_service, search_set_service

        for fn in (export_import_service.export_search_set, search_set_service.clone_search_set):
            source = inspect.getsource(fn)
            assert "share_token" not in source and "share_recipients" not in source
            assert "model_dump" not in source and "model_copy" not in source
