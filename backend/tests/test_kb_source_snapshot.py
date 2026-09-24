"""Each KB validation run records the KB as it found it.

Support ticket: exports carried no source list, source versions or
per-source chunk counts, so an older run could not be reproduced or
compared once the KB changed.
"""

import datetime
from types import SimpleNamespace

from app.services.kb_source_snapshot import build_source_snapshot, legacy_source_snapshot

T = datetime.datetime(2026, 9, 1, 12, 0, tzinfo=datetime.timezone.utc)


def _src(uuid, **kw):
    fields = dict(
        uuid=uuid, source_type="document", document_uuid=f"doc-{uuid}", url=None,
        custom_name=None, document_title=f"{uuid}.pdf", url_title=None,
        source_reference=None, status="ready", chunk_count=10, truncated=False,
        created_at=T, processed_at=T, last_ingested_at=T, last_retrieved_at=T,
        content_retrieved_at=T, content_hash=f"sha-{uuid}", content=None,
        last_refresh_attempted_at=None, last_refresh_outcome=None, last_refresh_error=None,
    )
    fields.update(kw)
    return SimpleNamespace(**fields)


def test_records_each_source_with_its_version_and_chunks():
    snap = build_source_snapshot([
        _src("b", source_type="url", document_uuid=None, document_title=None,
             url="https://nsf.gov/pappg", url_title="NSF PAPPG", chunk_count=40),
        _src("a", custom_name="Budget guide"),
    ])
    assert snap["recorded"] is True
    assert snap["total_sources"] == 2
    assert snap["total_chunks"] == 50
    a, b = snap["sources"]  # sorted by uuid
    assert a["source_uuid"] == "a" and a["name"] == "Budget guide"
    assert a["document_uuid"] == "doc-a"
    assert a["content_hash"] == "sha-a" and a["content_hash_recorded"] is True
    assert a["last_ingested_at"] == T.isoformat()
    assert b["url"] == "https://nsf.gov/pappg" and b["chunk_count"] == 40


def test_fingerprint_is_the_kb_state_and_nothing_else():
    base = [_src("a"), _src("b")]
    fp = build_source_snapshot(base)["fingerprint"]

    assert build_source_snapshot(list(reversed(base)))["fingerprint"] == fp
    # A rename is not a new KB state; the indexed text is unchanged.
    assert build_source_snapshot([_src("a", custom_name="Renamed"), _src("b")])["fingerprint"] == fp

    for changed in (
        [_src("a"), _src("b"), _src("c")],                     # a source added
        [_src("a")],                                           # one removed
        [_src("a", content_hash="sha-new"), _src("b")],        # a source re-fetched
        [_src("a", chunk_count=12), _src("b")],                # re-chunked
        [_src("a", status="error"), _src("b")],                # a source failed
    ):
        assert build_source_snapshot(changed)["fingerprint"] != fp


def test_an_older_run_exports_what_it_kept_and_says_so():
    snap = legacy_source_snapshot({
        "source_health": {"total": 1, "details": [
            {"uuid": "a", "source_type": "document", "name": "a.pdf", "status": "healthy"},
        ]},
        "chunk_coverage": {"total_chunks": 10},
    })
    assert snap["recorded"] is False and snap["fingerprint"] is None
    assert snap["total_chunks"] == 10
    assert snap["sources"] == [{"source_uuid": "a", "source_type": "document", "name": "a.pdf", "health": "healthy"}]
    assert legacy_source_snapshot({}) is None
