"""A stored turn should record the documents it was asked against.

A KB-grounded answer already recorded what it drew on — `citations` on the
assistant turn — while a direct-document answer recorded nothing, even though
the router has the fully resolved, authorized set in hand when it writes the
user turn. Without it a saved conversation cannot say which document produced
which answer, and continuing a conversation across a changed selection (which
is deliberate and useful) leaves no trace of the change.
"""

from __future__ import annotations

import pytest

from app.models.chat import (
    MAX_RECORDED_SOURCE_DOCUMENTS,
    ChatMessage,
    ChatRole,
    _cap_source_documents,
)


def _doc(uuid: str, title: str) -> dict:
    return {"uuid": uuid, "title": title}


class TestRecordedScope:
    def test_a_turn_serializes_the_scope_it_was_asked_against(self):
        msg = ChatMessage.model_construct(
            role=ChatRole.USER,
            message="What is the budget?",
            thinking=None,
            thinking_duration=None,
            citations=None,
            source_documents=[_doc("d1", "Proposal A.pdf")],
        )
        assert msg.to_dict()["source_documents"] == [_doc("d1", "Proposal A.pdf")]

    def test_a_turn_without_a_scope_says_nothing(self):
        """Attachment notices and KB-only turns have no document scope; the key
        should be absent rather than an empty list, so old messages and new ones
        look the same to a reader."""
        msg = ChatMessage.model_construct(
            role=ChatRole.USER, message="hello", thinking=None,
            thinking_duration=None, citations=None, source_documents=None,
        )
        assert "source_documents" not in msg.to_dict()

    def test_the_title_is_kept_beside_the_uuid(self):
        """The point of the record is to be readable later, and a uuid stops
        resolving the moment the document is deleted — which is exactly when
        someone wants to know what an old answer was based on."""
        msg = ChatMessage.model_construct(
            role=ChatRole.USER,
            message="q",
            thinking=None,
            thinking_duration=None,
            citations=None,
            source_documents=[_doc("d1", "Proposal A.pdf")],
        )
        recorded = msg.to_dict()["source_documents"][0]
        assert recorded["title"] == "Proposal A.pdf"
        assert recorded["uuid"] == "d1"


class TestScopeIsBounded:
    def test_a_small_selection_is_recorded_whole(self):
        docs = [_doc(f"d{i}", f"Doc {i}") for i in range(3)]
        assert _cap_source_documents(docs) == docs

    def test_nothing_becomes_none_rather_than_an_empty_list(self):
        assert _cap_source_documents([]) is None
        assert _cap_source_documents(None) is None

    def test_an_oversized_selection_says_how_much_it_left_out(self):
        """Folder expansion alone allows 500 documents per folder, and this is
        written on every turn — so it is bounded, and says so rather than
        silently dropping the tail."""
        docs = [
            _doc(f"d{i}", f"Doc {i}")
            for i in range(MAX_RECORDED_SOURCE_DOCUMENTS + 7)
        ]
        capped = _cap_source_documents(docs)

        assert len(capped) == MAX_RECORDED_SOURCE_DOCUMENTS + 1
        assert capped[:MAX_RECORDED_SOURCE_DOCUMENTS] == docs[:MAX_RECORDED_SOURCE_DOCUMENTS]
        assert capped[-1] == {"truncated": 7}

    def test_exactly_at_the_cap_is_not_marked_truncated(self):
        docs = [
            _doc(f"d{i}", f"Doc {i}")
            for i in range(MAX_RECORDED_SOURCE_DOCUMENTS)
        ]
        capped = _cap_source_documents(docs)
        assert len(capped) == MAX_RECORDED_SOURCE_DOCUMENTS
        assert all("truncated" not in d for d in capped)


class TestAddMessageThreadsItThrough:
    @pytest.mark.asyncio
    async def test_the_scope_reaches_the_stored_message(self, monkeypatch):
        created = await _add(monkeypatch, [_doc("d1", "Proposal A.pdf")])
        assert created.source_documents == [_doc("d1", "Proposal A.pdf")]

    @pytest.mark.asyncio
    async def test_an_oversized_selection_is_capped_on_the_way_in(self, monkeypatch):
        """The cap belongs on the write, not on every caller."""
        too_many = [
            _doc(f"d{i}", f"Doc {i}")
            for i in range(MAX_RECORDED_SOURCE_DOCUMENTS + 3)
        ]
        created = await _add(monkeypatch, too_many)
        assert created.source_documents[-1] == {"truncated": 3}


async def _add(monkeypatch, source_documents):
    """Run add_message with the DB writes stubbed, returning the stored message."""
    from app.models import chat as chat_model

    created: list[ChatMessage] = []

    async def fake_insert(self):
        created.append(self)
        self.id = "msg-1"

    async def fake_save(self):
        return self

    monkeypatch.setattr(chat_model.ChatMessage, "insert", fake_insert)
    monkeypatch.setattr(chat_model.ChatConversation, "save", fake_save)
    # Construct without Beanie's collection machinery, which these tests do not
    # stand up; the field plumbing is what is under test.
    monkeypatch.setattr(
        chat_model, "ChatMessage",
        type("_M", (), {
            "__init__": lambda self, **kw: self.__dict__.update(kw),
            "insert": fake_insert,
        }),
    )

    conversation = chat_model.ChatConversation.model_construct(
        uuid="c-1", user_id="u1", title="t", messages=[],
    )
    await conversation.add_message(
        ChatRole.USER, "q", source_documents=source_documents,
    )
    return created[0]
