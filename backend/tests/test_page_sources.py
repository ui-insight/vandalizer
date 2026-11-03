"""Living Pages: a Page knows its source files and notices a newer version."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import page_sources


class Docs:
    """smart_document stand-in: equality and $in queries, projections ignored."""

    def __init__(self, *docs):
        self.docs = [deepcopy(d) for d in docs]

    def _match(self, doc, query):
        for key, value in query.items():
            if isinstance(value, dict) and "$in" in value:
                if doc.get(key) not in value["$in"]:
                    return False
            elif doc.get(key) != value:
                return False
        return True

    def find_one(self, query, projection=None):
        return deepcopy(next((d for d in self.docs if self._match(d, query)), None))

    def find(self, query, projection=None):
        return [deepcopy(d) for d in self.docs if self._match(d, query)]


V1_TEXT = """## Budget
| Category | Y1 | Y2 | Total |
| --- | --- | --- | --- |
| Personnel | 200,000 | 206,000 | 406,000 |
| Equipment | 15,000 | 15,000 | 30,000 |
| Total | 620,000 | 630,000 | 1,250,000 |
Prepared by the Office of Sponsored Programs."""

V2_TEXT = V1_TEXT.replace("| Equipment | 15,000 | 15,000 | 30,000 |", "| Equipment | 15,000 | 20,000 | 35,000 |") \
    .replace("| Total | 620,000 | 630,000 | 1,250,000 |", "| Total | 620,000 | 635,000 | 1,255,000 |")


def chain_db():
    return SimpleNamespace(smart_document=Docs(
        {"uuid": "V1", "title": "NIH R01 Budget Table.xlsx", "version_number": 1, "superseded_by": "V2", "raw_text": V1_TEXT},
        {"uuid": "V2", "title": "NIH_R01_Budget_Table_v2.xlsx", "version_number": 2, "version_root": "V1",
         "previous_version_uuid": "V1", "superseded_by": None, "raw_text": V2_TEXT, "processing": False},
        {"uuid": "OTHER", "title": "Narrative.docx", "version_number": 1, "raw_text": "text"},
    ))


def test_spreadsheet_changes_name_the_row_column_and_values():
    summary = page_sources.summarize_changes(V1_TEXT, V2_TEXT)
    assert summary["items"] == [
        "Equipment · Y2: 15,000 → 20,000",
        "Equipment · Total: 30,000 → 35,000",
        "Total · Y2: 630,000 → 635,000",
        "Total · Total: 1,250,000 → 1,255,000",
    ]
    assert summary["more"] == 0


def test_text_changes_show_the_differing_words_and_cap_the_list():
    old = "\n".join(f"Line {i} says alpha" for i in range(12))
    new = "\n".join(f"Line {i} says beta" for i in range(12))
    summary = page_sources.summarize_changes(old, new)
    assert summary["items"][0] == "Line 0 says: alpha → beta"
    assert len(summary["items"]) == page_sources.MAX_CHANGES
    assert summary["more"] == 12 - page_sources.MAX_CHANGES
    assert page_sources.summarize_changes(old, old)["total"] == 0


def test_freshness_reports_newer_version_with_changes():
    db = chain_db()
    sources = page_sources.resolve(db, ["V1", "OTHER", "V1", "GONE"])
    assert [s["uuid"] for s in sources] == ["V1", "OTHER"]
    result = page_sources.freshness(db, sources + [{"uuid": "GONE", "title": "Old.pdf"}], changes=True)
    stale, current, missing = result
    assert stale["status"] == "updated"
    assert stale["latest"]["uuid"] == "V2" and stale["latest"]["version_number"] == 2 and stale["latest"]["ready"]
    assert "Equipment · Y2: 15,000 → 20,000" in stale["changes"]["items"]
    assert current["status"] == "current"
    assert missing["status"] == "missing"


def test_newer_version_still_being_read_has_no_changes_yet():
    db = chain_db()
    db.smart_document.docs[1]["processing"] = True
    [item] = page_sources.freshness(db, page_sources.resolve(db, ["V1"]), changes=True)
    assert item["status"] == "updated" and item["latest"]["ready"] is False
    assert "changes" not in item


def test_revised_page_swaps_in_the_new_version_it_was_rebuilt_from():
    db = chain_db()
    previous = page_sources.resolve(db, ["V1", "OTHER"])
    # The update turn attached v2: same file lineage, so it replaces v1.
    assert page_sources.carry_forward(db, previous, ["V2"]) == ["V2", "OTHER"]
    # A turn that used unrelated files keeps the page's recorded sources.
    assert page_sources.carry_forward(db, previous, ["OTHER"]) == ["V1", "OTHER"]
    # A page with no recorded sources adopts the files this turn used.
    assert page_sources.carry_forward(db, [], ["V2"]) == ["V2"]


def test_public_flag_tracks_the_published_revision():
    db = chain_db()
    stale_revision = {"source": {"documents": page_sources.resolve(db, ["V1"])}}
    fresh_revision = {"source": {"documents": page_sources.resolve(db, ["V2"])}}
    assert page_sources.newer_data_available(db, stale_revision) is True
    assert page_sources.newer_data_available(db, fresh_revision) is False
    assert page_sources.newer_data_available(db, {"source": {"kind": "editor"}}) is False


class _Cursor:
    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        self._it = iter(self.items)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.asyncio
async def test_owner_is_notified_only_for_pages_whose_latest_version_used_the_file():
    pages = [
        {"uuid": "p1", "user_id": "owner", "title": "NIH R01 Budget Dashboard", "latest_revision": "r1",
         "revisions": [{"uuid": "r1", "source": {"documents": [{"uuid": "V1"}]}}]},
        # Already rebuilt from another file: its latest revision doesn't use V1.
        {"uuid": "p2", "user_id": "owner", "title": "Old", "latest_revision": "r3",
         "revisions": [{"uuid": "r2", "source": {"documents": [{"uuid": "V1"}]}},
                       {"uuid": "r3", "source": {"documents": [{"uuid": "OTHER"}]}}]},
    ]
    collection = MagicMock()
    collection.find.return_value = _Cursor(pages)
    previous = SimpleNamespace(uuid="V1", version_number=1, title="NIH R01 Budget Table.xlsx")
    latest = SimpleNamespace(uuid="V2", version_number=2, title="NIH_R01_Budget_Table_v2.xlsx")
    with patch("app.models.artifact.Artifact.get_motor_collection", return_value=collection), \
         patch("app.services.notification_service.create_notification", new_callable=AsyncMock) as notify:
        await page_sources.notify_source_revised(previous, latest)
    notify.assert_awaited_once()
    kwargs = notify.await_args.kwargs
    assert kwargs["user_id"] == "owner" and kwargs["link"] == "/pages/p1"
    assert kwargs["kind"] == "page_source_updated"
    assert "NIH R01 Budget Dashboard" in kwargs["body"]


@pytest.mark.asyncio
async def test_notification_failure_never_fails_the_upload():
    previous = SimpleNamespace(uuid="V1", version_number=1, title="a")
    latest = SimpleNamespace(uuid="V2", version_number=2, title="b")
    with patch("app.models.artifact.Artifact.get_motor_collection", side_effect=RuntimeError("down")):
        await page_sources.notify_source_revised(previous, latest)


def _version_upload_mocks(claimed: int):
    storage = MagicMock()
    storage.write = AsyncMock()
    storage.delete = AsyncMock()
    storage.public_path.return_value = "/tmp/x.xlsx"
    collection = MagicMock()
    collection.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=claimed))
    return storage, collection


@pytest.mark.asyncio
@pytest.mark.parametrize("claimed", [1, 0])
async def test_new_version_claims_the_old_file_once(claimed):
    from app.services import file_service

    storage, collection = _version_upload_mocks(claimed)
    replaces = SimpleNamespace(uuid="V1", version_root=None, version_number=1, folder="F1",
                               team_id="T1", superseded_by=None)
    settings = SimpleNamespace(max_upload_size_mb=10)
    user = SimpleNamespace(user_id="u1")
    created = []

    class FakeDoc:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.version_root = None
            self.version_number = 1
            self.previous_version_uuid = None
            self.id = "oid"
            created.append(self)

        async def insert(self):
            return None

        get_motor_collection = staticmethod(lambda: collection)

    with patch("app.services.file_service.is_allowed_file", return_value=True), \
         patch("app.services.file_service.is_valid_file_content", return_value=True), \
         patch("app.services.file_service.SmartDocument", FakeDoc), \
         patch("app.services.file_service.record_extraction_dispatch", new_callable=AsyncMock), \
         patch("app.services.storage.get_storage", return_value=storage), \
         patch("app.tasks.upload_tasks.dispatch_upload_tasks", return_value="task"), \
         patch("app.services.page_sources.notify_source_revised", new_callable=AsyncMock) as notify:
        if not claimed:
            with pytest.raises(ValueError, match="newer version"):
                await file_service.upload_document("YWJj", "Budget v2.pdf", "pdf", user, settings, replaces=replaces)
            storage.delete.assert_awaited_once()
            notify.assert_not_awaited()
            return
        result = await file_service.upload_document("YWJj", "Budget v2.pdf", "pdf", user, settings, replaces=replaces)
    [doc] = created
    assert doc.folder == "F1" and doc.team_id == "T1"
    assert (doc.version_root, doc.version_number, doc.previous_version_uuid) == ("V1", 2, "V1")
    assert result["version_number"] == 2 and result["replaces"] == "V1"
    query, update = collection.update_one.await_args.args
    assert query == {"uuid": "V1", "superseded_by": None}
    assert update == {"$set": {"superseded_by": doc.uuid}}
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_deleting_the_current_version_restores_the_previous_one():
    from app.services import file_service

    collection = MagicMock()
    collection.update_one = AsyncMock()
    head = SimpleNamespace(uuid="V2", previous_version_uuid="V1", superseded_by=None)
    with patch("app.services.file_service.SmartDocument.get_motor_collection", return_value=collection):
        await file_service._unlink_version(head)
    query, update = collection.update_one.await_args.args
    assert query == {"uuid": "V1", "superseded_by": "V2"}
    assert update == {"$set": {"superseded_by": None}}


def test_chat_page_records_used_files_and_update_turn_moves_to_new_version():
    from app.services.chat_artifact_tools import _source_documents, _used_documents

    context = SimpleNamespace(deps=SimpleNamespace(context_document_uuids=["V1"], documents_read=["OTHER", "V1"]))
    assert _used_documents(context) == ["V1", "OTHER"]
    db = chain_db()
    created = _source_documents(db, None, _used_documents(context))
    assert [d["uuid"] for d in created] == ["V1", "OTHER"]
    assert created[0] == {"uuid": "V1", "title": "NIH R01 Budget Table.xlsx", "version_number": 1}
    page = {"latest_revision": "r1", "revisions": [{"uuid": "r1", "source": {"documents": created}}]}
    # "Update page" attaches v2; the revision now cites v2 and stays linked to OTHER.
    revised = _source_documents(db, page, ["V2"])
    assert [(d["uuid"], d["version_number"]) for d in revised] == [("V2", 2), ("OTHER", 1)]
    assert page_sources.freshness(db, revised)[0]["status"] == "current"
