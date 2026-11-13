"""Editing your own core Skill keeps it in use (support ticket: chat paused
it as "1 core Skill is paused" until the editor approved their own text in
Assistant settings). A teammate's pending edit still waits for review."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import skill_service


def _doc(content="Check every deadline.", when="Reviewing a new award notice"):
    doc = SimpleNamespace(uuid="s1", title="Award review", set_type="prompt",
                          extraction_config={"content": content, "when_to_use": when})
    doc.get_items = AsyncMock(return_value=[])
    return doc


def _version(doc):
    return skill_service._snapshot(doc, []).version


class _Users:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update):
        self.calls.append((query, update))
        return SimpleNamespace(modified_count=1, matched_count=1)

    async def find_one(self, query, projection=None):
        return {"core_skills": [{"uuid": "s1", "version": "reloaded"}]}


@pytest.fixture
def store(monkeypatch):
    state = SimpleNamespace(doc=_doc(), users=_Users())

    async def find_one(query):
        return state.doc if query == {"uuid": "s1"} else None

    monkeypatch.setattr(skill_service, "SearchSet", SimpleNamespace(find_one=find_one))
    monkeypatch.setattr(skill_service, "_users", lambda: state.users)
    return state


def _user(version):
    return SimpleNamespace(id="user-id", core_skills=[{"uuid": "s1", "version": version}] if version else [])


@pytest.mark.asyncio
async def test_own_edit_moves_the_acceptance_to_the_new_text(store):
    user = _user(_version(store.doc))
    before = await skill_service.core_version_before_edit(user, "s1")
    assert before.version == _version(store.doc)

    store.doc = _doc(content="Check every deadline and the budget.")
    await skill_service.keep_own_edit_accepted(user, "s1", before)

    query, update = store.users.calls[0]
    # Conditional on the person still holding the pre-edit version.
    assert query == {"_id": "user-id", "core_skills": {"$elemMatch": {"uuid": "s1", "version": before.version}}}
    assert update == {"$set": {"core_skills.$.version": _version(store.doc)}}
    assert user.core_skills == [{"uuid": "s1", "version": "reloaded"}]


@pytest.mark.asyncio
async def test_a_teammates_pending_edit_still_waits_for_review(store):
    # The person accepted older text; a teammate's edit is already waiting.
    user = _user("the-text-before-a-teammate-edited-it")
    assert await skill_service.core_version_before_edit(user, "s1") is None
    await skill_service.keep_own_edit_accepted(user, "s1", None)
    assert store.users.calls == []


@pytest.mark.asyncio
async def test_not_a_core_skill_is_left_alone(store):
    user = _user(None)
    assert await skill_service.core_version_before_edit(user, "s1") is None


@pytest.mark.asyncio
async def test_no_write_when_the_text_did_not_change_or_became_unusable(store):
    user = _user(_version(store.doc))
    before = await skill_service.core_version_before_edit(user, "s1")
    await skill_service.keep_own_edit_accepted(user, "s1", before)  # unchanged
    store.doc = _doc(content="")  # emptied: no usable version to accept
    await skill_service.keep_own_edit_accepted(user, "s1", before)
    assert store.users.calls == []


@pytest.mark.asyncio
async def test_a_teammates_concurrent_edit_to_another_part_is_not_accepted(store):
    # This save changed only the "when to use" line, but a teammate's new
    # instructions landed between the before and after reads.
    user = _user(_version(store.doc))
    before = await skill_service.core_version_before_edit(user, "s1")
    store.doc = _doc(content="A teammate's new instructions.", when="Reviewing any award")
    await skill_service.keep_own_edit_accepted(user, "s1", before, frozenset({"title", "when_to_use"}))
    assert store.users.calls == []

    # Without the teammate's change, the same save carries over.
    store.doc = _doc(when="Reviewing any award")
    await skill_service.keep_own_edit_accepted(user, "s1", before, frozenset({"title", "when_to_use"}))
    assert store.users.calls[0][1] == {"$set": {"core_skills.$.version": _version(store.doc)}}


@pytest.mark.asyncio
async def test_a_failure_after_the_save_is_logged_not_raised(store, caplog):
    user = _user(_version(store.doc))
    before = await skill_service.core_version_before_edit(user, "s1")
    store.doc = _doc(content="Check every deadline and the budget.")
    store.users.update_one = AsyncMock(side_effect=RuntimeError("mongo down"))
    with caplog.at_level("WARNING", logger="app.services.skill_service"):
        await skill_service.keep_own_edit_accepted(user, "s1", before)  # does not raise
    record = next(r for r in caplog.records if "s1" in r.getMessage())
    assert record.exc_info and record.exc_info[0] is RuntimeError
    assert user.core_skills == [{"uuid": "s1", "version": before.version}]


# Route wiring: each Edit-window save checks before and carries after.
from unittest.mock import MagicMock, patch  # noqa: E402

from tests.test_files_routes import _auth_cookies, _make_user, client  # noqa: E402,F401


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body,service,edited", [
    ("patch", "/api/extractions/search-sets/s1", {"title": "Award review", "when_to_use": "x"}, "update_search_set",
     {"title", "when_to_use"}),
    ("patch", "/api/extractions/search-sets/s1", {"when_to_use": "x"}, "update_search_set", {"when_to_use"}),
    ("patch", "/api/extractions/search-sets/s1", {"extraction_config": {"content": "x"}}, "update_search_set",
     {"title", "when_to_use", "instructions"}),
    ("patch", "/api/extractions/items/item-1", {"searchphrase": "New text"}, "update_item", {"instructions"}),
    ("post", "/api/extractions/search-sets/s1/items", {"searchphrase": "New text", "searchtype": "prompt", "title": "Award review"}, "add_item",
     {"instructions"}),
])
async def test_edit_routes_keep_the_editors_acceptance(client, method, path, body, service, edited):  # noqa: F811
    user = _make_user()
    cookies, headers = _auth_cookies()
    order = []
    before = AsyncMock(side_effect=lambda u, uuid: order.append(("before", uuid)) or "v-before")
    keep = AsyncMock(side_effect=lambda u, uuid, b, parts: order.append(("keep", uuid, b, set(parts))))
    saved = MagicMock(id="x", searchphrase="New text", searchset="s1", searchtype="prompt", title="Award review",
                      is_optional=False, enum_values=[], description=None)
    with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
         patch("app.dependencies.User") as MockUser, \
         patch("app.routers.extractions._get_search_set_or_404", AsyncMock()), \
         patch("app.routers.extractions._get_search_set_item_or_404", AsyncMock(return_value=SimpleNamespace(searchset="s1"))), \
         patch("app.routers.extractions._ss_response", AsyncMock(return_value={"id": "x", "title": "Award review", "uuid": "s1", "status": "active", "set_type": "prompt"})), \
         patch(f"app.routers.extractions.svc.{service}", AsyncMock(side_effect=lambda *a, **k: order.append(("save",)) or saved)), \
         patch("app.services.verification_service.check_and_flag_stale_verification", AsyncMock()), \
         patch("app.models.search_set.SearchSet", MagicMock(find_one=AsyncMock(return_value=None))), \
         patch("app.routers.extractions.skill_service.core_version_before_edit", before), \
         patch("app.routers.extractions.skill_service.keep_own_edit_accepted", keep):
        MockUser.find_one = AsyncMock(return_value=user)
        resp = await getattr(client, method)(path, json=body, cookies=cookies, headers=headers)
    assert resp.status_code < 500, resp.text
    assert order == [("before", "s1"), ("save",), ("keep", "s1", "v-before", edited)]
