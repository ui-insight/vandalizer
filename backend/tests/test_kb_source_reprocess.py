"""Reprocess one knowledge-base source in place.

Support ticket: users could rebuild a source only by deleting and re-adding
it. Reprocess re-runs the pipeline for that one source, and what it runs
depends on what the source has to work with (see kb_source_reprocess).
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import kb_source_reprocess
from app.services.kb_source_reprocess import ReprocessRefused, reprocess_source

NOW = datetime.datetime.now(tz=datetime.timezone.utc)


def _kb():
    return SimpleNamespace(uuid="kb-1", status="ready", save=AsyncMock())


def _source(**kw):
    fields = dict(
        uuid="src-1", source_type="document", document_uuid="doc-1", url=None,
        status="error", error_message="Document has no extractable text",
        refresh_queued_at=None, last_refresh_attempted_at=None, created_at=NOW,
    )
    fields.update(kw)
    src = SimpleNamespace(**fields)
    src.save = AsyncMock()
    return src


def _doc(**kw):
    fields = dict(
        uuid="doc-1", raw_text="Award letter text.", task_status="complete",
        processing=False, soft_deleted=False, updated_at=NOW, created_at=NOW,
    )
    fields.update(kw)
    return SimpleNamespace(**fields)


async def _run(source, doc=None, *, authorized=True, restart=None):
    kb = _kb()
    restart = restart or AsyncMock(return_value={"task_id": "t-1"})
    with patch.object(kb_source_reprocess.SmartDocument, "find_one", AsyncMock(return_value=doc)), \
         patch.object(kb_source_reprocess.access_control, "get_authorized_document",
                      AsyncMock(return_value=doc if authorized else None)) as authz, \
         patch.object(kb_source_reprocess.document_service, "restart_extraction", restart), \
         patch.object(kb_source_reprocess, "_dispatch_reindex") as reindex, \
         patch.object(kb_source_reprocess.kb_url_refresh, "queue_refresh", AsyncMock(return_value=1)) as refetch:
        result = await reprocess_source(kb, source, SimpleNamespace(user_id="u1"))
    return result, kb, SimpleNamespace(authz=authz, restart=restart, reindex=reindex, refetch=refetch)


@pytest.mark.asyncio
async def test_document_with_text_is_reindexed_without_re_reading_it():
    src = _source()
    result, kb, m = await _run(src, _doc())

    assert result["mode"] == "reindex"
    m.reindex.assert_called_once_with("src-1")
    # Re-reading would clear the document's text everywhere and re-fire its
    # folder's automations; a document with good text is never re-read.
    m.restart.assert_not_awaited()
    assert src.status == "pending" and src.error_message is None
    assert kb.status == "building"


@pytest.mark.asyncio
async def test_document_without_text_is_re_read_first():
    src = _source()
    doc = _doc(raw_text="", task_status="error")
    order = []
    src.save = AsyncMock(side_effect=lambda: order.append(("save", src.status)))
    restart = AsyncMock(side_effect=lambda *a: order.append(("restart", None)) or {"task_id": "t"})

    result, _, m = await _run(src, doc, restart=restart)

    assert result["mode"] == "reextract"
    restart.assert_awaited_once_with(doc, "u1")
    m.reindex.assert_not_called()
    # Parked before the extraction starts, or a fast extraction finds no
    # pending source to index and the source waits on nothing.
    assert order == [("save", "pending"), ("restart", None)]


@pytest.mark.asyncio
async def test_re_reading_needs_edit_access_to_the_document():
    src = _source()
    with pytest.raises(ReprocessRefused) as exc:
        await _run(src, _doc(raw_text="", task_status="error"), authorized=False)
    assert exc.value.status_code == 403
    assert "owner" in exc.value.detail
    assert src.status == "error"
    src.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_dispatch_puts_the_source_back():
    src = _source()
    with pytest.raises(RuntimeError):
        await _run(src, _doc(raw_text="", task_status="error"),
                   restart=AsyncMock(side_effect=RuntimeError("broker down")))
    assert src.status == "error"
    assert src.error_message == "Document has no extractable text"


@pytest.mark.asyncio
async def test_extraction_already_running_is_waited_on_not_restarted():
    src = _source()
    doc = _doc(raw_text="", task_status="extracting", processing=True)
    result, _, m = await _run(src, doc)

    assert result["mode"] == "waiting"
    m.restart.assert_not_awaited()
    m.reindex.assert_not_called()
    assert src.status == "pending"


@pytest.mark.asyncio
async def test_deleted_document_is_refused_with_a_reason():
    for doc in (None, _doc(soft_deleted=True)):
        with pytest.raises(ReprocessRefused) as exc:
            await _run(_source(), doc)
        assert exc.value.status_code == 400
        assert "deleted from Files" in exc.value.detail


@pytest.mark.asyncio
async def test_web_source_re_fetches():
    src = _source(source_type="url", url="https://example.org/p", document_uuid=None, status="ready")
    result, kb, m = await _run(src)

    assert result["mode"] == "refetch"
    m.refetch.assert_awaited_once()
    assert m.refetch.await_args.args[1] == [src]
    assert kb.status == "building"


@pytest.mark.asyncio
async def test_a_source_in_progress_is_refused():
    src = _source(status="processing", refresh_queued_at=NOW)
    with pytest.raises(ReprocessRefused) as exc:
        await _run(src, _doc())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_a_source_stuck_in_progress_can_be_reprocessed():
    long_ago = NOW - datetime.timedelta(hours=5)
    src = _source(status="processing", refresh_queued_at=long_ago, created_at=long_ago)
    result, _, _ = await _run(src, _doc())
    assert result["mode"] == "reindex"


def test_reindex_dispatch_keeps_retrieval_dates():
    app = MagicMock()
    with patch("app.celery_app.celery_app", app):
        kb_source_reprocess._dispatch_reindex("src-1")
    kwargs = app.send_task.call_args.kwargs
    assert app.send_task.call_args.args[0] == "tasks.documents.kb_ingest_document"
    assert kwargs["args"] == ["src-1"] and kwargs["kwargs"] == {"retrieved": False}
