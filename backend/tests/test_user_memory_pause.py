"""Assistant memory can be turned off per (user, team) scope (#1014 item 48).

While paused nothing is recorded and the system prompt gets no patterns
block; what is already stored survives, and clearing doesn't unpause it.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import user_memory_service as svc


def _doc(paused=False):
    recent = datetime.datetime.now(datetime.timezone.utc).isoformat()
    doc = MagicMock()
    doc.paused = paused
    doc.extraction_runs = {"ss-1": {"title": "NOA fields", "count": 4, "last_used": recent}}
    doc.workflow_runs = {}
    doc.kb_queries = {}
    doc.save = AsyncMock()
    doc.delete = AsyncMock()
    return doc


def _find(doc):
    # The model's field descriptors need init_beanie; stand in for the class.
    model = MagicMock()
    model.find_one = AsyncMock(return_value=doc)
    return patch.object(svc, "UserMemory", model)


@pytest.mark.asyncio
async def test_paused_memory_records_nothing():
    doc = _doc(paused=True)
    with patch.object(svc, "_get_or_create", AsyncMock(return_value=doc)):
        await svc.record_extraction("u1", "t1", "ss-1", "NOA fields")
    assert doc.extraction_runs["ss-1"]["count"] == 4
    doc.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_memory_still_records():
    doc = _doc()
    with patch.object(svc, "_get_or_create", AsyncMock(return_value=doc)):
        await svc.record_extraction("u1", "t1", "ss-1", "NOA fields")
    assert doc.extraction_runs["ss-1"]["count"] == 5


@pytest.mark.asyncio
async def test_paused_memory_gives_the_prompt_no_patterns():
    with _find(_doc(paused=True)):
        assert await svc.build_patterns_block("u1", "t1") == ""
    with _find(_doc()):
        assert "NOA fields" in await svc.build_patterns_block("u1", "t1")


@pytest.mark.asyncio
async def test_patterns_report_the_paused_state_and_keep_items():
    with _find(_doc(paused=True)):
        out = await svc.get_patterns("u1", "t1")
    assert out["paused"] is True
    assert [e["title"] for e in out["extractions"]] == ["NOA fields"]


@pytest.mark.asyncio
async def test_set_paused_saves_the_flag():
    doc = _doc()
    with patch.object(svc, "_get_or_create", AsyncMock(return_value=doc)):
        assert await svc.set_paused("u1", "t1", True) is True
    assert doc.paused is True
    doc.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_clearing_paused_memory_keeps_it_paused():
    doc = _doc(paused=True)
    with _find(doc):
        assert await svc.clear_memory("u1", "t1") is True
    doc.delete.assert_not_awaited()
    assert doc.extraction_runs == {}
    assert doc.paused is True


@pytest.mark.asyncio
async def test_clearing_active_memory_deletes_it():
    doc = _doc()
    with _find(doc):
        assert await svc.clear_memory("u1", "t1") is True
    doc.delete.assert_awaited_once()
