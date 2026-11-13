"""Files ⋯ menu → Duplicate (support ticket): copy a document into its own
folder as "<name> (Copy)", with its own stored file."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services import file_service
from app.services.file_service import _copy_title
from tests.test_files_routes import _auth_cookies, _make_user, client  # noqa: F401

_SETTINGS = Settings(jwt_secret_key="test-secret-key", environment="development")


def _doc(**overrides):
    base = dict(
        uuid="SRC", title="R4-inbox-test.pdf", extension="pdf", folder="f1", team_id=None,
        user_id="owner", path="owner/SRC.pdf", downloadpath="owner/SRC.pdf",
        raw_text="Award text", text_markers=[{"char_offset": 0, "kind": "page", "value": 1}],
        token_count=3, num_pages=1, valid=True, validation_feedback=None,
        error_message=None, error_retryable=None, extraction_nonletter_ratio=0.0,
        text_layer_rejected=False, ingestion_warnings=["partial_ocr"], unread_pages=[],
        classification="internal", classification_confidence=0.9, classified_at=None,
        classified_by="auto", generated_by=None, soft_deleted=False, processing=False,
        task_status="complete", scheduled_deletion_at=None, retention_hold=False,
        retention_hold_reason=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_copy_title_keeps_the_extension_and_counts_up():
    assert _copy_title("R4-inbox-test.pdf", 1, "pdf") == "R4-inbox-test (Copy).pdf"
    assert _copy_title("R4-inbox-test.pdf", 2, "pdf") == "R4-inbox-test (Copy 2).pdf"
    assert _copy_title("Scan.PDF", 1, "pdf") == "Scan (Copy).PDF"
    assert _copy_title("notes", 1, "txt") == "notes (Copy)"
    assert _copy_title(".env", 1, "env") == ".env (Copy)"


def test_copy_title_splits_only_on_the_documents_extension():
    # A renamed file whose title has a dot that isn't its extension.
    assert _copy_title("Q3 Report v1.2", 1, "pdf") == "Q3 Report v1.2 (Copy)"
    assert _copy_title("Q3 Report v1.2", 1, None) == "Q3 Report v1.2 (Copy)"
    assert _copy_title("Q3 Report v1.2.pdf", 1, "pdf") == "Q3 Report v1.2 (Copy).pdf"


class _Env:
    def __init__(self, doc, *, siblings=(), folder=SimpleNamespace(team_id=None), manage=True):
        self.storage = MagicMock()
        self.storage.read = AsyncMock(return_value=b"%PDF-bytes")
        self.storage.write = AsyncMock()
        self.storage.delete = AsyncMock()
        self.Model = MagicMock()
        self.Model.find.return_value.project.return_value.to_list = AsyncMock(
            return_value=[SimpleNamespace(title=t) for t in siblings])
        self.instance = MagicMock(insert=AsyncMock(), delete=AsyncMock())
        self.Model.return_value = self.instance
        # update_document_fields.si(...) [| perform_semantic_ingestion.si(...)]
        self.update_si = MagicMock()
        self.ingest_si = MagicMock()
        self.chain = self.update_si.return_value
        self.chain.__or__ = MagicMock(return_value=self.chain)

        async def get_doc(uuid, user, *, manage=False, **_):
            return doc if (manage_ok or not manage) else None

        manage_ok = manage
        self.patches = [
            patch("app.services.access_control.get_authorized_document", side_effect=get_doc),
            patch("app.services.access_control.get_authorized_folder", AsyncMock(return_value=folder)),
            patch("app.services.file_service.SmartDocument", self.Model),
            patch("app.services.storage.get_storage", return_value=self.storage),
            patch("app.tasks.document_tasks.update_document_fields.si", self.update_si),
            patch("app.tasks.document_tasks.perform_semantic_ingestion.si", self.ingest_si),
        ]

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()

    @property
    def queued(self):
        return self.chain.apply_async.called

    @property
    def indexed(self):
        return self.ingest_si.called

    @property
    def fields(self):
        return self.Model.call_args.kwargs


@pytest.mark.asyncio
async def test_copies_file_and_text_into_the_same_folder():
    doc = _doc()
    user = _make_user("dup-user")
    with _Env(doc) as env:
        result = await file_service.duplicate_document("SRC", _SETTINGS, user=user)

    assert result["title"] == "R4-inbox-test (Copy).pdf"
    f = env.fields
    assert f["folder"] == "f1" and f["team_id"] is None and f["user_id"] == "dup-user"
    # Its own stored file, so deleting one never removes the other's bytes.
    env.storage.read.assert_awaited_once_with("owner/SRC.pdf")
    new_path = env.storage.write.await_args.args[0]
    assert new_path == f"dup-user/{result['uuid']}.pdf" == f["path"] == f["downloadpath"]
    assert env.storage.write.await_args.args[1] == b"%PDF-bytes"
    # Not read again: same text and caveats; only indexing is left.
    assert f["raw_text"] == "Award text" and f["text_markers"] == doc.text_markers
    assert f["ingestion_warnings"] == ["partial_ocr"]
    # Not an in-progress status: the stuck-document sweep must not finish the
    # copy while its steps are still queued.
    assert f["task_status"] == "complete" and f["processing"] is False
    assert f["chromadb_ready"] is False
    # A fresh document: no version chain, no knowledge base.
    assert "version_root" not in f and "previous_version_uuid" not in f
    env.instance.insert.assert_awaited_once()
    # The steps an upload runs after reading: folder-watch check, then indexing.
    env.update_si.assert_called_once_with(document_uuid=result["uuid"])
    env.ingest_si.assert_called_once_with(raw_text="", document_uuid=result["uuid"], user_id="dup-user")
    env.chain.__or__.assert_called_once_with(env.ingest_si.return_value)
    env.chain.apply_async.assert_called_once_with()


@pytest.mark.asyncio
async def test_numbers_the_copy_when_the_name_is_taken():
    with _Env(_doc(), siblings=["R4-inbox-test.pdf", "R4-inbox-test (Copy).pdf",
                                "R4-inbox-test (Copy 2).pdf"]):
        result = await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    assert result["title"] == "R4-inbox-test (Copy 3).pdf"


@pytest.mark.asyncio
async def test_team_folder_copy_stays_in_the_team():
    with _Env(_doc(team_id="T1"), folder=SimpleNamespace(team_id="T1")) as env:
        await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    assert env.fields["team_id"] == "T1"
    assert env.Model.find.call_args.args[0]["team_id"] == "T1"


@pytest.mark.asyncio
async def test_unseen_document_is_none():
    with _Env(None):
        assert await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user()) is None


@pytest.mark.asyncio
async def test_refuses_a_file_still_being_read():
    with _Env(_doc(processing=True, task_status="extracting")) as env, \
         pytest.raises(ValueError, match="still being read"):
        await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    env.storage.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_refuses_when_the_folder_takes_no_new_files():
    with _Env(_doc(), folder=None) as env, pytest.raises(ValueError, match="can't add files"):
        await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    env.storage.write.assert_not_awaited()


@pytest.mark.asyncio
async def test_team_root_copy_needs_manage_access():
    with _Env(_doc(folder="0", team_id="T1"), manage=False), \
         pytest.raises(ValueError, match="can't add files"):
        await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())


@pytest.mark.asyncio
async def test_failed_reading_is_copied_without_indexing():
    doc = _doc(raw_text="", task_status="error", error_message="Could not read", error_retryable=True)
    with _Env(doc) as env:
        await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    assert env.fields["task_status"] == "error"
    assert env.fields["error_message"] == "Could not read"
    assert not env.queued and not env.indexed


@pytest.mark.asyncio
async def test_failed_reading_with_some_text_is_not_marked_ready():
    with _Env(_doc(task_status="error", error_message="Garbled text layer")) as env:
        await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    assert env.fields["task_status"] == "error"
    assert not env.queued and not env.indexed


@pytest.mark.asyncio
async def test_unreadable_stored_file_is_a_clear_error():
    with _Env(_doc()) as env:
        env.storage.read = AsyncMock(side_effect=FileNotFoundError("gone"))
        with pytest.raises(ValueError, match="could not be read"):
            await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    env.instance.insert.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_insert_removes_the_copied_file():
    with _Env(_doc()) as env:
        env.instance.insert = AsyncMock(side_effect=RuntimeError("db down"))
        with pytest.raises(RuntimeError):
            await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    env.storage.delete.assert_awaited_once_with(env.storage.write.await_args.args[0])
    assert not env.queued


@pytest.mark.asyncio
async def test_textless_copy_still_runs_folder_watch_but_is_not_indexed():
    with _Env(_doc(raw_text="")) as env:
        await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    assert env.fields["task_status"] == "complete"
    assert env.queued and not env.indexed


@pytest.mark.asyncio
async def test_queue_failure_takes_the_copy_back_out():
    with _Env(_doc()) as env:
        env.chain.apply_async.side_effect = ConnectionError("broker down")
        with pytest.raises(file_service.DuplicateNotQueuedError, match="could not be queued"):
            await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    env.instance.insert.assert_awaited_once()
    env.instance.delete.assert_awaited_once()
    env.storage.delete.assert_awaited_once_with(env.storage.write.await_args.args[0])


@pytest.mark.asyncio
async def test_copy_keeps_the_originals_scheduled_deletion_and_hold():
    import datetime

    when = datetime.datetime(2026, 12, 1, tzinfo=datetime.timezone.utc)
    with _Env(_doc(scheduled_deletion_at=when)) as env:
        await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    assert env.fields["scheduled_deletion_at"] == when
    assert env.fields["retention_hold"] is False

    with _Env(_doc(retention_hold=True, retention_hold_reason="Audit")) as env:
        await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    assert env.fields["retention_hold"] is True
    assert env.fields["retention_hold_reason"] == "Audit"
    assert env.fields["scheduled_deletion_at"] is None


@pytest.mark.asyncio
async def test_title_with_a_dot_that_isnt_the_extension():
    with _Env(_doc(title="Q3 Report v1.2")) as env:
        result = await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    assert result["title"] == "Q3 Report v1.2 (Copy)"
    assert env.Model.find.return_value.project.called


class TestDuplicateRoute:
    @pytest.mark.asyncio
    async def test_unauthenticated(self, client):  # noqa: F811
        resp = await client.post("/api/files/SRC/duplicate")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("outcome,status", [
        ({"uuid": "NEW", "title": "A (Copy).pdf"}, 200),
        (None, 404),
        (ValueError("This file is still being read."), 400),
        (file_service.DuplicateNotQueuedError("could not be queued"), 503),
    ])
    async def test_maps_service_outcomes(self, client, outcome, status):  # noqa: F811
        user = _make_user()
        cookies, headers = _auth_cookies()
        svc = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
        with patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}), \
             patch("app.dependencies.User") as MockUser, \
             patch("app.routers.files.file_service.duplicate_document", svc):
            MockUser.find_one = AsyncMock(return_value=user)
            resp = await client.post("/api/files/SRC/duplicate", cookies=cookies, headers=headers)
        assert resp.status_code == status
        assert svc.call_args.kwargs["user"] is user
        if status == 200:
            assert resp.json() == outcome
        if status == 400:
            assert "still being read" in resp.json()["detail"]
