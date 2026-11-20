"""A Skill's share link.

"Copy share link" on a Skill made a link that only worked for people who could
already open the Skill, while saying "Share it with anyone". The link now
carries a token: someone signed in who opens it is recorded as a recipient and
can read the Skill and use it in chat.

An independent review of the first version found that treating a recipient as
an ordinary viewer gave far too much: filing the Skill in their own library
turned into edit rights, and view-level routes exposed the owner's validation
data. So the grant is opt-in per call site (``allow_shared``), used only where
a Skill is read for chat, and the link lives in its own collection so a stale
whole-document save of the Skill cannot bring back a link that was turned off.
"""

import re
import secrets
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.models.search_set import SearchSet
from app.services import access_control, skill_share_service
from app.utils.security import create_access_token

_TEST_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")
TOKEN = "tok-" + "a" * 40
APP = Path(__file__).resolve().parents[1] / "app"


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
    ss.id = "507f1f77bcf86cd799439011"
    ss.uuid = "skill-1"
    ss.title = "Award review"
    ss.set_type = "prompt"
    ss.user_id = "owner"
    ss.team_id = "team-1"
    ss.is_global = False
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


class _FakeShares:
    """The few collection operations the service uses, over a dict."""

    def __init__(self):
        self.docs: dict[str, dict] = {}

    async def find_one_and_update(self, query, update, upsert=False, return_document=None):
        doc = self.docs.get(query["search_set_uuid"])
        if doc is None and upsert:
            doc = self.docs[query["search_set_uuid"]] = dict(update["$setOnInsert"])
        return doc

    async def find_one_and_delete(self, query):
        return self.docs.pop(query["search_set_uuid"], None)

    async def update_one(self, query, update):
        doc = self.docs.get(query["search_set_uuid"])
        matched = int(doc is not None and doc["token"] == query["token"])
        if matched:
            for user_id in update["$addToSet"].values():
                if user_id not in doc["recipients"]:
                    doc["recipients"].append(user_id)
        return MagicMock(matched_count=matched)

    async def count_documents(self, query, limit=0):
        doc = self.docs.get(query["search_set_uuid"])
        return int(doc is not None and query["recipients"] in doc["recipients"])


@pytest.fixture
def shares():
    fake = _FakeShares()
    with patch.object(skill_share_service, "_shares", return_value=fake):
        yield fake


class TestLinkStore:
    @pytest.mark.asyncio
    async def test_link_is_made_once_and_then_stable(self, shares):
        first = await skill_share_service.create_link("skill-1", "owner")
        second = await skill_share_service.create_link("skill-1", "teammate")
        assert first == second and len(first) >= 40
        assert shares.docs["skill-1"]["created_by"] == "owner"
        assert await skill_share_service.create_link("skill-2", "owner") != first

    @pytest.mark.asyncio
    async def test_right_token_lets_a_person_in_and_no_one_else(self, shares):
        token = await skill_share_service.create_link("skill-1", "owner")
        assert await skill_share_service.is_recipient("skill-1", "outsider") is False
        assert await skill_share_service.open_link("skill-1", token, "outsider") is True
        assert await skill_share_service.open_link("skill-1", token, "outsider") is True
        assert shares.docs["skill-1"]["recipients"] == ["outsider"]
        assert await skill_share_service.is_recipient("skill-1", "outsider") is True
        assert await skill_share_service.is_recipient("skill-1", "stranger") is False
        assert await skill_share_service.is_recipient("skill-2", "outsider") is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", ["wrong", "", None, 5, {"$ne": ""}, "x" * 201])
    async def test_wrong_or_malformed_token_lets_nobody_in(self, shares, bad):
        await skill_share_service.create_link("skill-1", "owner")
        assert await skill_share_service.open_link("skill-1", bad, "outsider") is False
        assert shares.docs["skill-1"]["recipients"] == []

    @pytest.mark.asyncio
    async def test_a_skill_without_a_link_cannot_be_opened(self, shares):
        assert await skill_share_service.open_link("skill-1", "", "outsider") is False
        assert await skill_share_service.open_link("skill-1", TOKEN, "outsider") is False
        assert await skill_share_service.open_link("skill-1", TOKEN, "") is False

    @pytest.mark.asyncio
    async def test_turning_off_removes_everyone_and_kills_the_old_token(self, shares):
        token = await skill_share_service.create_link("skill-1", "owner")
        await skill_share_service.open_link("skill-1", token, "outsider")
        await skill_share_service.open_link("skill-1", token, "another")

        assert await skill_share_service.turn_off("skill-1") == 2
        assert await skill_share_service.is_recipient("skill-1", "outsider") is False
        assert await skill_share_service.open_link("skill-1", token, "outsider") is False
        assert await skill_share_service.turn_off("skill-1") == 0
        # A new link is a new token: the old address stays dead.
        assert await skill_share_service.create_link("skill-1", "owner") != token

    def test_opening_checks_the_token_and_records_in_one_write(self):
        # A link turned off between a separate check and write would still let
        # the person in; the filter must carry the token.
        import inspect

        source = inspect.getsource(skill_share_service.open_link)
        assert source.count("update_one(") == 1 and "find_one" not in source
        assert '"token": token' in source

    def test_the_link_is_not_stored_on_the_skill(self):
        # The Skill document is saved whole from many places; a link kept on it
        # could be restored by a stale save after being turned off.
        assert not {"share_token", "share_recipients"} & set(SearchSet.model_fields)


class TestAccessRule:
    async def _authorized(self, user, ss, *, recipient, **kwargs):
        with (
            patch("app.models.search_set.SearchSet", new=MagicMock(find_one=AsyncMock(return_value=ss))),
            patch.object(access_control, "get_team_access_context", new=AsyncMock(return_value=MagicMock(team_uuids=set(), team_object_ids=set(), roles_by_team={}))),
            patch.object(access_control, "has_library_backed_object_access", new=AsyncMock(return_value=False)),
            patch.object(access_control, "has_open_verification_review_access", new=AsyncMock(return_value=False)),
            patch.object(skill_share_service, "is_recipient", new=AsyncMock(return_value=recipient)) as is_recipient,
        ):
            result = await access_control.get_authorized_search_set("skill-1", user, **kwargs)
        return result, is_recipient

    @pytest.mark.asyncio
    async def test_a_recipient_is_let_in_only_where_the_caller_asks(self):
        ss = _skill()
        allowed, _ = await self._authorized(_user(), ss, recipient=True, allow_shared=True)
        assert allowed is ss

        # Every other view-level check (validation data, exports, filing in a
        # library, submitting for verification) must not see a link holder.
        refused, is_recipient = await self._authorized(_user(), ss, recipient=True)
        assert refused is None
        is_recipient.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_link_never_gives_edit_rights(self):
        refused, is_recipient = await self._authorized(_user(), _skill(), recipient=True, allow_shared=True, manage=True)
        assert refused is None
        is_recipient.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_someone_who_did_not_open_the_link_is_refused(self):
        refused, _ = await self._authorized(_user(), _skill(), recipient=False, allow_shared=True)
        assert refused is None

    @pytest.mark.asyncio
    async def test_a_link_never_opens_an_extraction(self):
        refused, is_recipient = await self._authorized(_user(), _skill(set_type="extraction"), recipient=True, allow_shared=True)
        assert refused is None
        is_recipient.assert_not_awaited()

    def test_can_view_search_set_knows_nothing_about_links(self):
        # The synchronous rule feeds lists and many routes; link access must
        # not ride along with it.
        ss = _skill()
        ss.share_recipients = ["outsider"]
        assert access_control.can_view_search_set(ss, _user("outsider")) is False

    def test_only_reading_a_skill_for_chat_asks_for_link_access(self):
        asking = sorted(
            str(path.relative_to(APP))
            for path in APP.rglob("*.py")
            if re.search(r"allow_shared\s*=\s*True", path.read_text())
        )
        assert asking == ["services/skill_service.py"]
        # The by-id lookup (library, verification) has no such switch at all.
        import inspect

        assert "allow_shared" not in inspect.signature(access_control.get_authorized_search_set_by_id).parameters


class TestRoutes:
    def _caller(self, user):
        return (
            patch("app.dependencies.decode_token", return_value={"sub": user.user_id, "type": "access"}),
            patch("app.dependencies.User"),
            patch("app.routers.extractions.audit_service.log_event", new_callable=AsyncMock),
        )

    @pytest.mark.asyncio
    async def test_making_a_link_needs_edit_rights(self, client, shares):
        user = _user("owner")
        cookies, headers = _auth("owner")
        decode, mock_user, audit = self._caller(user)
        with decode, mock_user as MockUser, audit, patch(
            "app.routers.extractions.access_control.get_authorized_search_set", new_callable=AsyncMock, return_value=_skill(),
        ) as authz:
            MockUser.find_one = AsyncMock(return_value=user)
            first = await client.post("/api/extractions/search-sets/skill-1/share-token", cookies=cookies, headers=headers)
            second = await client.post("/api/extractions/search-sets/skill-1/share-token", cookies=cookies, headers=headers)

        assert first.status_code == 200
        assert first.json() == second.json() == {"share_token": shares.docs["skill-1"]["token"]}
        assert authz.await_args.kwargs["manage"] is True
        assert "allow_shared" not in authz.await_args.kwargs

    @pytest.mark.asyncio
    async def test_someone_who_cannot_edit_gets_no_link(self, client, shares):
        shares.docs["skill-1"] = {"search_set_uuid": "skill-1", "token": TOKEN, "recipients": ["member"]}
        user = _user("member")
        cookies, headers = _auth("member")
        decode, mock_user, audit = self._caller(user)
        with decode, mock_user as MockUser, audit, patch(
            "app.routers.extractions.access_control.get_authorized_search_set", new_callable=AsyncMock, return_value=None,
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            mint = await client.post("/api/extractions/search-sets/skill-1/share-token", cookies=cookies, headers=headers)
            off = await client.delete("/api/extractions/search-sets/skill-1/share-token", cookies=cookies, headers=headers)

        assert mint.status_code == off.status_code == 404
        assert TOKEN not in mint.text
        assert shares.docs["skill-1"]["recipients"] == ["member"]

    @pytest.mark.asyncio
    async def test_an_extraction_gets_no_link(self, client, shares):
        user = _user("owner")
        cookies, headers = _auth("owner")
        decode, mock_user, audit = self._caller(user)
        with decode, mock_user as MockUser, audit, patch(
            "app.routers.extractions.access_control.get_authorized_search_set", new_callable=AsyncMock,
            return_value=_skill(set_type="extraction"),
        ):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post("/api/extractions/search-sets/skill-1/share-token", cookies=cookies, headers=headers)

        assert resp.status_code == 400
        assert shares.docs == {}

    async def _redeem(self, client, user, ss, token):
        cookies, headers = _auth(user.user_id)
        decode, mock_user, audit = self._caller(user)
        with decode, mock_user as MockUser, audit, patch("app.routers.extractions.SearchSet") as MockSet:
            MockUser.find_one = AsyncMock(return_value=user)
            MockSet.find_one = AsyncMock(return_value=ss)
            return await client.post(
                "/api/extractions/search-sets/skill-1/share-token/redeem",
                json={"share_token": token}, cookies=cookies, headers=headers,
            )

    @pytest.mark.asyncio
    async def test_opening_with_the_right_token_records_the_person(self, client, shares):
        shares.docs["skill-1"] = {"search_set_uuid": "skill-1", "token": TOKEN, "recipients": []}
        resp = await self._redeem(client, _user("outsider"), _skill(), TOKEN)

        assert resp.status_code == 200
        assert resp.json() == {"uuid": "skill-1", "title": "Award review"}
        assert shares.docs["skill-1"]["recipients"] == ["outsider"]

    @pytest.mark.asyncio
    async def test_wrong_token_and_missing_skill_answer_alike_and_record_nobody(self, client, shares):
        shares.docs["skill-1"] = {"search_set_uuid": "skill-1", "token": TOKEN, "recipients": []}
        wrong = await self._redeem(client, _user("outsider"), _skill(), TOKEN + "x")
        shares.docs.clear()
        missing = await self._redeem(client, _user("outsider"), None, TOKEN)

        assert wrong.status_code == missing.status_code == 404
        assert wrong.json() == missing.json()
        assert "Award review" not in wrong.text

    @pytest.mark.asyncio
    async def test_signed_out_person_is_refused(self, client, shares):
        shares.docs["skill-1"] = {"search_set_uuid": "skill-1", "token": TOKEN, "recipients": []}
        csrf = secrets.token_urlsafe(32)
        resp = await client.post(
            "/api/extractions/search-sets/skill-1/share-token/redeem",
            json={"share_token": TOKEN}, cookies={"csrf_token": csrf}, headers={"X-CSRF-Token": csrf},
        )
        assert resp.status_code == 401
        assert shares.docs["skill-1"]["recipients"] == []

    @pytest.mark.asyncio
    async def test_turning_the_link_off_needs_edit_rights_and_removes_everyone(self, client, shares):
        shares.docs["skill-1"] = {"search_set_uuid": "skill-1", "token": TOKEN, "recipients": ["outsider", "another"]}
        user = _user("owner")
        cookies, headers = _auth("owner")
        decode, mock_user, audit = self._caller(user)
        with decode, mock_user as MockUser, audit as log, patch(
            "app.routers.extractions.access_control.get_authorized_search_set", new_callable=AsyncMock, return_value=_skill(),
        ) as authz:
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.delete("/api/extractions/search-sets/skill-1/share-token", cookies=cookies, headers=headers)

        assert resp.status_code == 200
        assert shares.docs == {}
        assert authz.await_args.kwargs["manage"] is True
        assert log.await_args.kwargs["detail"] == {"recipients_removed": 2}


class TestSkillUseInChat:
    @pytest.mark.asyncio
    async def test_reading_a_skill_for_chat_honours_the_link(self):
        from app.services import skill_service

        ss = _skill()
        with patch.object(access_control, "get_authorized_search_set", new=AsyncMock(return_value=ss)) as authz:
            assert await skill_service.authorize_skill("skill-1", _user()) is ss
        assert authz.await_args.kwargs == {"allow_shared": True}

    def test_someone_elses_skill_still_has_to_be_accepted_first(self):
        from app.schemas.skills import SkillSnapshot
        from app.services import skill_service

        user = _user()
        user.accepted_skills = []
        snapshot = SkillSnapshot(uuid="skill-1", title="Award review", instructions="Do the review.", version="v1")
        assert skill_service.needs_review(_skill(), user, snapshot)
