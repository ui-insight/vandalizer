"""Repair of documents stored with a raw OCR ``ocr.result`` envelope (support ticket).

The stored text in these fixtures is built the way it was stored before
``parse_raw_response``: the OCR body passed through ``layout_json_to_text``,
which leaves an envelope untouched.
"""

import json
from unittest.mock import MagicMock, patch

from app.services.document_readers import _interpolate_page_markers, _join_pages
from app.services.ocr_client import layout_json_to_text, parse_raw_response
from app.services.ocr_envelope_repair import (
    repair_document,
    repair_markers,
    unwrap_ocr_envelopes,
)

CONTENT = (
    "# RESEARCH SUBAWARD AGREEMENT\n\n"
    "Subaward No. NIH-WSU-UI-2025-1132\n\n"
    "| Category | Amount |\n|---|---|\n| Travel | $5,000 |\n\n"
    "Path: C:\\awards\\1132\n\n"
    "The period of performance is July 1, 2025 through June 30, 2026."
)


def _envelope(content: str, ocr_id: str = "ocr-3dae") -> str:
    return json.dumps({
        "id": ocr_id, "object": "ocr.result", "created": 1791837603,
        "model": "dots.MOCR", "content": content,
    })


def _stored_before_fix(body: str) -> str:
    return layout_json_to_text(body)


class TestUnwrap:
    def test_whole_document_envelope_becomes_what_a_fresh_upload_stores(self):
        stored = _stored_before_fix(_envelope(CONTENT))
        assert stored.startswith('{"id": "ocr-3dae"') and "\\n" in stored

        result = unwrap_ocr_envelopes(stored)

        assert result is not None and result.envelopes == 1
        assert result.text == parse_raw_response(_envelope(CONTENT)) == CONTENT
        # JSON decoding, not escape replacement: the literal backslashes stay.
        assert "C:\\awards\\1132" in result.text
        assert "dots.MOCR" not in result.text

    def test_text_without_an_envelope_is_left_alone(self):
        assert unwrap_ocr_envelopes(CONTENT) is None
        # A JSON example quoted in a document has no ocr.result discriminator.
        quoted = 'Send {"id": "x", "object": "invoice", "content": "a\\nb"} to AP.'
        assert unwrap_ocr_envelopes(quoted) is None

    def test_mention_of_ocr_result_outside_json_is_left_alone(self):
        text = 'The API returns "object": "ocr.result" in its response.'
        assert unwrap_ocr_envelopes(text) is None

    def test_envelope_without_string_content_is_not_repaired(self):
        body = json.dumps({"id": "ocr-1", "object": "ocr.result", "content": None})
        result = unwrap_ocr_envelopes(_stored_before_fix(body))
        assert result is None

    def test_per_page_envelopes_between_local_pages_keep_exact_page_markers(self):
        page1 = "Page one was read locally from its text layer."
        page2_ocr = "Scanned page two.\nBudget: Travel $5,000."
        page3 = "Page three was read locally as well."
        page4_ocr = "Scanned page four.\nSignatures."
        stored, markers = _join_pages({
            1: page1,
            2: _stored_before_fix(_envelope(page2_ocr, "ocr-p2")),
            3: page3,
            4: _stored_before_fix(_envelope(page4_ocr, "ocr-p4")),
        })

        result = unwrap_ocr_envelopes(stored)
        assert result is not None and result.envelopes == 2
        expected, expected_markers = _join_pages({1: page1, 2: page2_ocr, 3: page3, 4: page4_ocr})
        assert result.text == expected
        assert repair_markers(markers, result) == expected_markers

    def test_interpolated_markers_are_spread_over_the_repaired_text(self):
        stored = _stored_before_fix(_envelope(CONTENT))
        markers = _interpolate_page_markers(stored, 3)
        result = unwrap_ocr_envelopes(stored)
        assert repair_markers(markers, result) == _interpolate_page_markers(CONTENT, 3)


def _doc(**overrides) -> dict:
    stored = _stored_before_fix(_envelope(CONTENT))
    doc = {
        "uuid": "doc-1", "title": "sample-subaward-NIH-WSU-UI-2025-1132.pdf",
        "raw_text": stored, "text_markers": _interpolate_page_markers(stored, 2),
        "user_id": "u1", "processing": False, "extension": "pdf", "num_pages": 2,
        "ingestion_warnings": ["sparse_text", "unread_pages"],
        "_extraction_restart_revision": 3,
    }
    doc.update(overrides)
    return doc


def _db(matched: int = 1) -> MagicMock:
    db = MagicMock()
    db.smart_document.update_one.return_value.matched_count = matched
    db.knowledge_bases.find.return_value = [{"uuid": "project-kb"}]
    db.knowledge_base_sources.find.return_value = [
        {"uuid": "src-team", "knowledge_base_uuid": "team-kb"},
        {"uuid": "src-project", "knowledge_base_uuid": "project-kb"},
    ]
    return db


class TestRepairDocument:
    def test_repairs_text_in_place_and_reindexes_document_and_kb_sources(self):
        db = _db()
        doc = _doc()
        with patch("app.celery_app.celery_app.send_task") as send:
            row = repair_document(db, doc)

        assert row["status"] == "repaired" and row["kb_sources_queued"] == 1
        query, update = db.smart_document.update_one.call_args.args
        # Compare-and-set on the text that was read.
        assert query["raw_text"] == doc["raw_text"]
        fields = update["$set"]
        assert fields["raw_text"] == CONTENT
        assert fields["text_markers"] == _interpolate_page_markers(CONTENT, 2)
        assert fields["token_count"] > 0
        assert "unread_pages" in fields["ingestion_warnings"]
        assert fields["ocr_envelope_repaired_at"] is not None

        calls = [(c.args[0], c.kwargs) for c in send.call_args_list]
        assert calls[0][0] == "tasks.document.semantic_ingestion"
        assert calls[0][1]["args"] == ["", "doc-1", "u1"]
        assert calls[0][1]["kwargs"] == {"extraction_revision": 3}
        # The project KB is refreshed by that ingestion's mirror, not queued twice.
        assert calls[1:] == [(
            "tasks.documents.kb_ingest_document",
            {"args": ["src-team"], "kwargs": {"retrieved": False}, "queue": "documents"},
        )]

    def test_text_changed_since_read_is_not_overwritten_or_reindexed(self):
        db = _db(matched=0)
        with patch("app.celery_app.celery_app.send_task") as send:
            row = repair_document(db, _doc())
        assert row["status"] == "changed"
        send.assert_not_called()

    def test_document_being_extracted_is_skipped(self):
        db = _db()
        with patch("app.celery_app.celery_app.send_task") as send:
            row = repair_document(db, _doc(processing=True))
        assert row["status"] == "extracting"
        db.smart_document.update_one.assert_not_called()
        send.assert_not_called()

    def test_dry_run_changes_nothing(self):
        db = _db()
        with patch("app.celery_app.celery_app.send_task") as send:
            row = repair_document(db, _doc(), dry_run=True)
        assert row["status"] == "would_repair" and row["envelopes"] == 1
        db.smart_document.update_one.assert_not_called()
        send.assert_not_called()


class TestSweepTask:
    def _run(self, rows):
        from app.tasks.document_tasks import repair_ocr_envelopes

        db = MagicMock()
        with patch("app.tasks.document_tasks.get_sync_db", return_value=db), \
             patch("app.services.ocr_envelope_repair.repair_all", return_value=rows):
            counts = repair_ocr_envelopes.run()
        return db, counts

    def test_clean_sweep_marks_the_repair_complete(self):
        db, counts = self._run([{"uuid": "a", "status": "repaired"}, {"uuid": "b", "status": "undecodable"}])
        assert counts == {"repaired": 1, "undecodable": 1}
        update = db.system_config.update_one.call_args.args[1]
        assert update["$set"]["ocr_envelope_repair_completed_at"] is not None

    def test_sweep_with_retryable_leftovers_runs_again_next_startup(self):
        db, _ = self._run([{"uuid": "a", "status": "extracting"}])
        db.system_config.update_one.assert_not_called()
