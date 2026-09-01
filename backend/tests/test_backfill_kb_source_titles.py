"""The KB source title backfill must not overwrite fields it didn't read.

It is re-runnable operational tooling, so it will eventually be run against a
live system. A full-document ``save()`` would send every field this process
loaded — rolling back a ``chunk_count``/``status`` write an ingest made
between the find and the save. It writes the one field instead.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "backfill_kb_source_titles.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("backfill_kb_source_titles", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source(uuid="src-1", document_uuid="doc-1", kb_uuid="kb-1"):
    s = MagicMock()
    s.uuid = uuid
    s.document_uuid = document_uuid
    s.knowledge_base_uuid = kb_uuid
    s.set = AsyncMock()
    s.save = AsyncMock()
    return s


def _model(docs):
    model = MagicMock()
    model.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=docs)))
    return model


async def _run(source, *, dry_run=False, doc_exists=True, chunk_name=None):
    """Run the backfill over one source, with the document present or deleted
    and with or without a name recoverable from its indexed chunks."""
    module = _load_script()
    docs = [SimpleNamespace(uuid="doc-1", title="Award Letter.pdf")] if doc_exists else []

    with (
        patch("app.database.init_db", new_callable=AsyncMock),
        patch("app.models.knowledge.KnowledgeBaseSource", _model([source])),
        patch("app.models.knowledge.KnowledgeBase", _model([])),
        patch("app.models.document.SmartDocument", _model(docs)),
        patch("app.services.document_manager.get_document_manager", MagicMock()),
        patch.object(module, "_chunk_source_name", MagicMock(return_value=chunk_name)),
    ):
        await module.main(dry_run)


class TestBackfillWrites:
    @pytest.mark.asyncio
    async def test_writes_only_the_title_field(self):
        source = _source()

        await _run(source)

        source.save.assert_not_awaited()
        source.set.assert_awaited_once()
        written = source.set.await_args.args[0]
        assert list(written.values()) == ["Award Letter.pdf"]

    @pytest.mark.asyncio
    async def test_recovers_the_name_from_indexed_chunks_when_the_document_is_gone(self):
        source = _source()

        await _run(source, doc_exists=False, chunk_name="Deleted Award.pdf")

        assert list(source.set.await_args.args[0].values()) == ["Deleted Award.pdf"]

    @pytest.mark.asyncio
    async def test_dry_run_writes_nothing(self):
        source = _source()

        await _run(source, dry_run=True)

        source.set.assert_not_awaited()
        source.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_source_with_no_recoverable_name_is_left_alone(self):
        """Document deleted and its chunks gone too: nothing to write, and
        inventing a placeholder would be worse than the UUID it shows now."""
        source = _source()

        await _run(source, doc_exists=False, chunk_name=None)

        source.set.assert_not_awaited()
        source.save.assert_not_awaited()
