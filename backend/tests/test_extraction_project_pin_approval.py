"""An extraction created from chat is pinned only to the project its card named.

Support ticket: chat said the new template "has been created and pinned to the
project", but the approval card never mentioned a project. The gate's key held
only the documents and title, and the project was resolved afresh on the
approval turn, so a project open then (but not when the card was shown) got
the pin without ever being put in front of the user.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.test_chat_tools import TestCreateExtractionAutoPin as _AutoPin
from tests.test_chat_tools import _fake_project, _make_context


class _Conversation:
    def __init__(self):
        self.pending_confirmations: list = []

    async def save(self):
        pass


@pytest.mark.asyncio
async def test_project_opened_after_the_card_re_asks_instead_of_pinning():
    from app.services.chat_tools import create_extraction_from_document

    helper = _AutoPin()
    ctx = _make_context(team_id="team1", user_id="user1",
                        conversation=_Conversation(), turn_marker=5)
    with helper._patches(helper._ss(), _fake_project(), can_manage=True):
        with patch("app.services.project_service.add_pin",
                   new_callable=AsyncMock) as mock_add:
            card = await create_extraction_from_document(ctx, ["d1"])
            assert card["needs_confirmation"] is True
            assert "project" not in card["preview"]

            # The user approves from inside a project the card never named.
            ctx.deps.turn_marker = 6
            ctx.deps.active_project_uuid = "p1"
            again = await create_extraction_from_document(ctx, ["d1"], confirmed=True)

    mock_add.assert_not_awaited()
    assert again["needs_confirmation"] is True
    assert 'pinned to project "NIH R01"' in again["preview"]


@pytest.mark.asyncio
async def test_project_named_on_the_card_is_pinned_on_approval():
    from app.services.chat_tools import create_extraction_from_document

    helper = _AutoPin()
    ctx = _make_context(team_id="team1", user_id="user1", active_project_uuid="p1",
                        conversation=_Conversation(), turn_marker=5)
    with helper._patches(helper._ss(), _fake_project(), can_manage=True):
        with patch("app.services.project_service.add_pin",
                   new_callable=AsyncMock) as mock_add:
            card = await create_extraction_from_document(ctx, ["d1"])
            assert 'pinned to project "NIH R01"' in card["preview"]

            ctx.deps.turn_marker = 6
            done = await create_extraction_from_document(ctx, ["d1"], confirmed=True)

    mock_add.assert_awaited_once()
    assert done["pinned_to_project"] == "NIH R01"
