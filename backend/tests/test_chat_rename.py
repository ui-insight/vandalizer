"""Chats can be renamed, and a chat's name is generated until one sticks.

Support ticket: chats in Recent activity were named from the first words of
the first message ("add PAPPG.pdf and nih-r01-neuroscience.pdf to the") with
no way to rename them.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.services import activity_service
from app.services.activity_service import should_queue_chat_title


def _event(**kw):
    ev = MagicMock()
    ev.type = kw.get("type", "conversation")
    ev.title = kw.get("title", "add PAPPG.pdf and nih-r01-neuroscience.pdf to the")
    ev.meta_summary = kw.get("meta_summary", {"description_generated": True})
    ev.conversation_id = kw.get("conversation_id", "conv-1")
    ev.save = AsyncMock()
    return ev


async def _rename(ev, title, conversation=None):
    with patch.object(activity_service, "ActivityEvent") as AE, \
         patch.object(activity_service, "ChatConversation") as CC:
        AE.find_one = AsyncMock(return_value=ev)
        CC.find_one = AsyncMock(return_value=conversation)
        return await activity_service.rename_conversation_activity(ObjectId(), "u1", title)


# --- the rename itself --------------------------------------------------------


@pytest.mark.asyncio
async def test_renaming_sets_the_title_on_the_chat_and_its_conversation():
    ev = _event()
    conversation = SimpleNamespace(title="add PAPPG.pdf and", save=AsyncMock())
    result = await _rename(ev, "  PAPPG and   NIH R01 KB ", conversation)

    assert result is ev
    assert ev.title == "PAPPG and NIH R01 KB"
    assert ev.meta_summary["title_user_set"] is True
    assert ev.meta_summary["description_generated"] is True
    ev.save.assert_awaited_once()
    assert conversation.title == "PAPPG and NIH R01 KB"
    conversation.save.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("title, message", [("   ", "empty"), ("x" * 121, "120 characters")])
async def test_an_empty_or_overlong_name_is_refused(title, message):
    with pytest.raises(ValueError, match=message):
        await _rename(_event(), title)


@pytest.mark.asyncio
async def test_only_chats_can_be_renamed():
    with pytest.raises(ValueError, match="Only chats"):
        await _rename(_event(type="workflow_run"), "New name")


@pytest.mark.asyncio
async def test_someone_elses_chat_is_not_found():
    assert await _rename(None, "New name") is None


@pytest.mark.asyncio
async def test_the_endpoint_maps_errors_to_422_and_404():
    from app.routers import activity as router

    user = MagicMock(user_id="u1")
    body = router.RenameActivityRequest(title="New name")
    oid = str(ObjectId())
    with patch.object(router.activity_service, "rename_conversation_activity", new=AsyncMock(side_effect=ValueError("Only chats can be renamed."))):
        with pytest.raises(HTTPException) as exc:
            await router.rename_activity(oid, body, user=user)
    assert exc.value.status_code == 422
    with patch.object(router.activity_service, "rename_conversation_activity", new=AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc:
            await router.rename_activity(oid, body, user=user)
    assert exc.value.status_code == 404
    ev = MagicMock()
    ev.to_dict.return_value = {"id": oid, "title": "New name"}
    with patch.object(router.activity_service, "rename_conversation_activity", new=AsyncMock(return_value=ev)):
        assert (await router.rename_activity(oid, body, user=user))["activity"]["title"] == "New name"


# --- when chat asks for a generated title -------------------------------------


@pytest.mark.parametrize("meta, expected", [
    ({}, True),                                            # first exchange
    ({"description_generated": True}, True),               # an attempt ran but produced nothing
    ({"title_attempts": 2}, True),
    ({"title_attempts": 3}, False),                        # gave up after three
    ({"ai_description": "Subaward Cost Share"}, False),    # already titled
    ({"title_user_set": True}, False),                     # the user named it
    (None, True),
])
def test_should_queue_chat_title(meta, expected):
    assert should_queue_chat_title(meta) is expected


# --- the generator leaves a user's name alone ---------------------------------


def test_the_generated_title_never_replaces_a_name_the_user_set():
    import app.tasks.activity_tasks as at

    db = MagicMock()
    oid = ObjectId()
    db.activity_event.find_one.return_value = {"_id": oid, "user_id": "u1", "team_id": None}
    db.smart_document.find_one.return_value = {"uuid": "d", "title": "NOA.pdf", "raw_text": "Award notice."}
    db.user_model_config.find_one.return_value = None
    db.system_config.find_one.return_value = {}

    with patch.object(at, "_get_db", return_value=db), \
         patch.object(at, "_pick_title_model", return_value="fast"), \
         patch("app.services.llm_service.create_chat_agent", return_value=MagicMock()), \
         patch("app.services.metering.metered", return_value=MagicMock()), \
         patch.object(at, "run_task_async", return_value=SimpleNamespace(output="NOA Budget Review")):
        at.generate_activity_description_task(
            activity_id=str(oid), activity_type="conversation", document_uuids=["d"],
        )

    title_writes = [
        c.args for c in db.activity_event.update_one.call_args_list if "title" in c.args[1]["$set"]
    ]
    assert len(title_writes) == 1
    query, update = title_writes[0]
    assert query == {"_id": oid, "meta_summary.title_user_set": {"$ne": True}}
    assert update["$set"]["title"] == "NOA Budget Review"
