"""Mixed obligation batches save on the first approval of the accepted items."""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import chat_tools, obligation_service as service
from tests.conftest import fake_model
from tests.test_chat_tools import _make_context


def deadline(index, *, rejected=False):
    return {
        "kind": "deadline", "deadline_type": "other", "title": f"Report {index}",
        "due_at": f"2026-{'07' if rejected else '06'}-{index:02}",
        "due_text": None if rejected else f"due June {index}, 2026",
        "sources": [{"document_uuid": "source", "quote": f"Report {index} is due June {index}, 2026."}],
    }


@pytest.fixture
def environment(monkeypatch):
    project = SimpleNamespace(uuid="project", title="Award", team_id=None)
    doc = SimpleNamespace(uuid="source", title="Award.pdf", raw_text="\n".join(
        f"Report {i} is due June {i}, 2026." for i in range(1, 7)), text_markers=None)
    monkeypatch.setattr(service, "_readable_document", AsyncMock(return_value=doc))
    monkeypatch.setattr(service, "Obligation", fake_model([]))
    monkeypatch.setattr(chat_tools, "_resolve_active_project", AsyncMock(return_value=project))
    monkeypatch.setattr("app.services.project_service.can_manage_project", AsyncMock(return_value=True))
    write = AsyncMock(side_effect=lambda project, user, clean: clean)
    monkeypatch.setattr(service, "save_checked", write)
    monkeypatch.setattr(service, "serialize", lambda ob, *args: ob)
    ctx = _make_context(conversation=SimpleNamespace(pending_confirmations=[], save=AsyncMock()))
    return ctx, project, write


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted_only", [False, True])
async def test_first_approval_saves_three_accepted_items(environment, accepted_only):
    ctx, project, write = environment
    items = [deadline(i) for i in range(1, 4)] + [deadline(i, rejected=True) for i in range(4, 7)]
    preview = await chat_tools.propose_obligations(ctx, items)
    assert len(preview["obligation_review"]["items"]) == 3
    assert len(preview["obligation_review"]["excluded"]) == 3
    assert "cite the passage" not in preview["preview"]
    assert "due June" not in preview["preview"]
    assert "Add to inbox" in preview["assistant_instruction"]
    write.assert_not_awaited()
    ctx.deps.turn_marker += 2
    confirmed = list(reversed(items[:3])) if accepted_only else items
    if accepted_only:
        # Equivalent input formatting must not affect the reviewed write.
        confirmed = [{**item, "due_text": None} for item in confirmed]
    result = await chat_tools.propose_obligations(ctx, confirmed, confirmed=True)
    assert result["ok"] is True
    assert result["approval_key"] == preview["approval_key"]
    assert len(result["added"]) == write.await_count == 3
    assert ctx.deps.conversation.pending_confirmations == []


@pytest.mark.asyncio
async def test_same_turn_cannot_approve_accepted_subset(environment):
    ctx, _, write = environment
    await chat_tools.propose_obligations(ctx, [deadline(1), deadline(2, rejected=True)])
    assert (await chat_tools.propose_obligations(ctx, [deadline(1)], confirmed=True))["needs_confirmation"]
    write.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["date", "source", "replacement", "project", "extra_item", "removed_item"])
async def test_changed_write_requires_review(environment, change):
    ctx, project, write = environment
    items = [deadline(1), deadline(2)]
    await chat_tools.propose_obligations(ctx, items)
    ctx.deps.turn_marker += 2
    checked = copy.deepcopy(await service.propose(project, ctx.deps.user, items))
    row = checked["accepted"][0]
    if change == "date":
        row["clean"]["due_at"] = row["clean"]["due_at"].replace(day=3)
    elif change == "source":
        row["clean"]["sources"][0].quote += " Changed source."
    elif change == "replacement":
        row["replaces"] = {"uuid": "old", "due_at": "2026-05-01", "sources": [{"document_title": "Old award.pdf"}]}
    elif change == "project":
        project.uuid = "other-project"
    elif change == "extra_item":
        checked["accepted"].append(copy.deepcopy(row))
    elif change == "removed_item":
        checked["accepted"].pop()
    with patch.object(service, "propose", AsyncMock(return_value=checked)):
        assert (await chat_tools.propose_obligations(ctx, items, confirmed=True))["needs_confirmation"]
    write.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_source_does_not_expose_internal_id(environment, monkeypatch):
    ctx, project, _ = environment
    monkeypatch.setattr(service, "_readable_document", AsyncMock(return_value=None))
    item = deadline(1)
    item["sources"][0]["document_uuid"] = "internal-document-identifier"
    result = await service.propose(project, ctx.deps.user, [item])
    assert "internal-document-identifier" not in str(result)
    assert "source document" in result["rejected"][0]["reason"]
