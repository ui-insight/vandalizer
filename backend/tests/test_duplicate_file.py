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
        task_status="complete",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_copy_title_keeps_the_extension_and_counts_up():
    assert _copy_title("R4-inbox-test.pdf", 1) == "R4-inbox-test (Copy).pdf"
    assert _copy_title("R4-inbox-test.pdf", 2) == "R4-inbox-test (Copy 2).pdf"
    assert _copy_title("notes", 1) == "notes (Copy)"
    assert _copy_title(".env", 1) == ".env (Copy)"


class _Env:
    def __init__(self, doc, *, siblings=(), folder=SimpleNamespace(team_id=None), manage=True):
        self.storage = MagicMock()
        self.storage.read = AsyncMock(return_value=b"%PDF-bytes")
        self.storage.write = AsyncMock()
        self.storage.delete = AsyncMock()
        self.Model = MagicMock()
        self.Model.find.return_value.to_list = AsyncMock(
            return_value=[SimpleNamespace(title=t) for t in siblings])
        self.instance = MagicMock(insert=AsyncMock())
        self.Model.return_value = self.instance
        self.ingest = MagicMock()

        async def get_doc(uuid, user, *, manage=False, **_):
            return doc if (manage_ok or not manage) else None

        manage_ok = manage
        self.patches = [
            patch("app.services.access_control.get_authorized_document", side_effect=get_doc),
            patch("app.services.access_control.get_authorized_folder", AsyncMock(return_value=folder)),
            patch("app.services.file_service.SmartDocument", self.Model),
            patch("app.services.storage.get_storage", return_value=self.storage),
            patch("app.tasks.document_tasks.perform_semantic_ingestion.delay", self.ingest),
        ]

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()

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
    assert f["task_status"] == "readying" and f["processing"] is False
    assert f["chromadb_ready"] is False
    # A fresh document: no version chain, no knowledge base.
    assert "version_root" not in f and "previous_version_uuid" not in f
    env.instance.insert.assert_awaited_once()
    env.ingest.assert_called_once_with("Award text", result["uuid"], "dup-user")


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
    env.ingest.assert_not_called()


@pytest.mark.asyncio
async def test_failed_reading_with_some_text_is_not_marked_ready():
    with _Env(_doc(task_status="error", error_message="Garbled text layer")) as env:
        await file_service.duplicate_document("SRC", _SETTINGS, user=_make_user())
    assert env.fields["task_status"] == "error"
    env.ingest.assert_not_called()


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
    env.ingest.assert_not_called()


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
