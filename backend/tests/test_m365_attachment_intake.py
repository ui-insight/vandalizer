"""M365 mail/drive attachment intake validates files before storing them.

#834: ``_save_attachment_as_document`` stored every attachment as a
SmartDocument (``ext or "bin"``) without the upload endpoint's two checks, so
each signature image, .exe, or zero-byte stub got a document row, was queued,
fully read, and only then refused — a permanent error-state document per
attachment. Intake now skips what the upload endpoint would have refused and
records the skip on the WorkItem.
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

from app.tasks import m365_tasks

PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


class TestAttachmentRejection:
    def test_a_valid_pdf_is_accepted(self):
        assert m365_tasks._attachment_rejection("award.pdf", PDF) is None

    def test_an_executable_is_refused_by_type(self):
        reason = m365_tasks._attachment_rejection("setup.exe", b"MZ\x90\x00" + b"\x00" * 64)
        assert reason == "unsupported file type .exe"

    def test_a_zero_byte_pdf_is_refused_as_empty(self):
        assert m365_tasks._attachment_rejection("blank.pdf", b"") == "empty file"

    def test_a_pdf_whose_bytes_are_not_a_pdf_is_refused_by_content(self):
        reason = m365_tasks._attachment_rejection("scan.pdf", b"GIF89a" + b"\x00" * 64)
        assert reason == "content does not match .pdf"

    def test_a_name_without_an_extension_is_refused(self):
        assert m365_tasks._attachment_rejection("attachment", PDF) == "no file extension"


def _file_attachment(name: str, content: bytes) -> dict:
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": name,
        "contentBytes": base64.b64encode(content).decode("ascii"),
    }


def _db_with_intake():
    db = MagicMock()
    db.intake_configs.find_one.return_value = {
        "_id": "intake-oid", "uuid": "intake-1", "intake_type": "outlook_folder",
        "team_id": "team-1",
    }
    db.work_items.find_one.return_value = None  # not a duplicate
    db.work_items.insert_one.return_value = MagicMock(inserted_id="wi-oid")
    return db


def _graph_client(attachments: list[dict]):
    client = MagicMock()
    client.get_message.return_value = {
        "hasAttachments": bool(attachments),
        "subject": "FW: award documents",
        "body": {"contentType": "text", "content": "see attached"},
        "from": {"emailAddress": {"address": "pi@uidaho.edu", "name": "PI"}},
        "receivedDateTime": "2026-09-16T10:00:00Z",
    }
    client.get_message_attachments.return_value = attachments
    return client


class TestEmailIngestionSkipsInvalidAttachments:
    def _ingest(self, attachments: list[dict]):
        db = _db_with_intake()
        saved: list[str] = []

        def fake_save(db_, content, filename, user_id):
            saved.append(filename)
            return {"_id": f"doc-{len(saved)}", "uuid": f"u{len(saved)}", "extension": "pdf"}

        with patch.object(m365_tasks, "_get_db", return_value=db), \
             patch("app.services.graph_client.GraphClient",
                   return_value=_graph_client(attachments)), \
             patch.object(m365_tasks, "_save_attachment_as_document", side_effect=fake_save), \
             patch.object(m365_tasks, "_trigger_text_extraction"), \
             patch.object(m365_tasks, "triage_work_item"):
            out = m365_tasks.ingest_email_message(
                "user-1", "users/u/messages/msg-1", "intake-1",
            )
        work_item = db.work_items.insert_one.call_args.args[0]
        audit = db.m365_audit_entry.insert_one.call_args.args[0]
        return out, saved, work_item, audit

    def test_exe_and_empty_pdf_are_skipped_with_reasons_and_the_valid_pdf_saves(self):
        out, saved, work_item, audit = self._ingest([
            _file_attachment("setup.exe", b"MZ\x90\x00" + b"\x00" * 64),
            _file_attachment("blank.pdf", b""),
            _file_attachment("award.pdf", PDF),
        ])

        assert out["status"] == "ingested"
        assert saved == ["award.pdf"]
        assert work_item["attachment_count"] == 1
        assert work_item["attachments"] == ["doc-1"]
        assert work_item["skipped_attachments"] == [
            {"name": "setup.exe", "reason": "unsupported file type .exe"},
            {"name": "blank.pdf", "reason": "empty file"},
        ]
        assert audit["detail"]["skipped_attachments"] == work_item["skipped_attachments"]

    def test_a_message_whose_attachments_all_pass_records_no_skips(self):
        out, saved, work_item, _ = self._ingest([_file_attachment("award.pdf", PDF)])
        assert out["status"] == "ingested"
        assert saved == ["award.pdf"]
        assert work_item["skipped_attachments"] == []

    def test_skips_are_logged_at_info_without_content(self):
        with patch.object(m365_tasks, "logger") as log:
            self._ingest([_file_attachment("setup.exe", b"MZ\x90\x00SECRETBYTES")])
        messages = [str(c.args) for c in log.info.call_args_list]
        assert any("setup.exe" in m and "msg-1" in m for m in messages)
        assert not any("SECRETBYTES" in m for m in messages)


class TestDriveIngestionSkipsInvalidFiles:
    def _ingest(self, filename: str, content: bytes):
        db = _db_with_intake()
        client = MagicMock()
        client.get_drive_item.return_value = {"name": filename, "size": len(content)}
        client.download_file.return_value = content

        with patch.object(m365_tasks, "_get_db", return_value=db), \
             patch("app.services.graph_client.GraphClient", return_value=client), \
             patch.object(m365_tasks, "_save_attachment_as_document") as save, \
             patch.object(m365_tasks, "_trigger_text_extraction"), \
             patch.object(m365_tasks, "triage_work_item"):
            save.return_value = {"_id": "doc-1", "uuid": "u1", "extension": "pdf"}
            out = m365_tasks.ingest_drive_item("user-1", "drives/d/items/item-1", "intake-1")
        return out, save, db

    def test_a_zip_dropped_in_the_folder_creates_no_document_and_is_audited(self):
        out, save, db = self._ingest("bundle.zip", b"PK\x03\x04" + b"\x00" * 64)

        assert out["status"] == "filtered_out"
        assert "unsupported file type .zip" in out["reason"]
        save.assert_not_called()
        db.work_items.insert_one.assert_not_called()
        audit = db.m365_audit_entry.insert_one.call_args.args[0]
        assert audit["action"] == "ingest_skipped"
        assert audit["detail"]["filename"] == "bundle.zip"
        assert audit["detail"]["reason"] == "unsupported file type .zip"

    def test_a_valid_pdf_still_becomes_a_work_item(self):
        out, save, db = self._ingest("award.pdf", PDF)
        assert out["status"] == "ingested"
        save.assert_called_once()
        db.work_items.insert_one.assert_called_once()
