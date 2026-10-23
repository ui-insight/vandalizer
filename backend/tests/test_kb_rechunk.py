"""Re-chunking knowledge bases indexed by an older chunker
(app.services.kb_rechunk): every ready source rebuilt from its stored text,
swapped in source by source, idempotent, reported per knowledge base."""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services import kb_chunking as kc
from app.services import kb_rechunk as rc
from app.services.document_manager import CHUNK_OVERLAP, CHUNK_SIZE, DocumentManager, _split_text_with_offsets
from app.services.kb_optimization_status import compute_optimization_status
from app.utils import kb_source_currency as currency

T0 = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)


def _para(label: str, n: int, words: str = "") -> str:
    out, i = [], 0
    while len(" ".join(out)) < n:
        out.append(f"{label}w{i}")
        i += 1
    return f"({label}) {words} " + " ".join(out) + "."


REGULATION = (
    "Subpart E—Cost Principles\n\n"
    "§ 200.421 Advertising and public relations.\n\n" + "\n".join(_para(c, 300, "advertising") for c in "abcdef")
    + "\n\n§ 200.423 Alcoholic beverages.\n\nThe cost of alcoholic beverages is unallowable.\n\n"
    "§ 200.424 Alumni activities.\n\n" + _para("z", 200, "alumni") + "\n"
)
POLICY = "45.13 - Program Income\n" + "\n".join(f"{c}. Item. " + _para(c.lower(), 400, "income") for c in "ABCD")


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction=1):
        return _Cursor(sorted(self.rows, key=lambda r: r.get(key) or T0, reverse=direction < 0))

    def __iter__(self):
        return iter(self.rows)


class _Coll:
    """Enough of a pymongo collection: equality filters and $set."""

    def __init__(self, rows=()):
        self.rows = [dict(r) for r in rows]

    def _match(self, row, flt):
        return all(row.get(k) == v for k, v in (flt or {}).items())

    def find(self, flt=None, projection=None):
        return _Cursor([r for r in self.rows if self._match(r, flt)])

    def find_one(self, flt=None, projection=None):
        return next((r for r in self.rows if self._match(r, flt)), None)

    def update_one(self, flt, update):
        row = self.find_one(flt)
        if row is not None:
            row.update(update.get("$set", {}))


class _Db:
    def __init__(self, kbs, sources, docs=()):
        self.knowledge_bases = _Coll(kbs)
        self.knowledge_base_sources = _Coll(sources)
        self.smart_document = _Coll(docs)

    def source(self, uuid):
        return self.knowledge_base_sources.find_one({"uuid": uuid})


class _Chroma:
    """A KB collection: rows by id, filtered by source."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.fail_add = False

    def add(self, ids, documents, metadatas, embeddings=None):
        if self.fail_add:
            raise RuntimeError("embedding service went away")
        for i, doc, meta in zip(ids, documents, metadatas):
            self.rows.setdefault(i, {"document": doc, "metadata": meta})

    def get(self, where=None, include=None, ids=None, limit=None):
        keep = [(i, r) for i, r in self.rows.items()
                if not where or r["metadata"].get("source_id") == where.get("source_id")]
        return {"ids": [i for i, _ in keep], "metadatas": [r["metadata"] for _, r in keep],
                "documents": [r["document"] for _, r in keep]}

    def delete(self, ids=None, where=None):
        for i in list(ids or []):
            self.rows.pop(i, None)

    def of(self, source_id):
        return [r for r in self.rows.values() if r["metadata"]["source_id"] == source_id]


def _old_chunks(chroma, source_id, name, text):
    """Chunks as the fixed 1,000/200 window wrote them."""
    for i, (chunk, _) in enumerate(_split_text_with_offsets(text, CHUNK_SIZE, CHUNK_OVERLAP)):
        chroma.rows[f"{source_id}_chunk_{i}"] = {
            "document": chunk, "metadata": {"source_id": source_id, "source_name": name, "chunk_index": i},
        }


@pytest.fixture
def world():
    chroma = _Chroma()
    dm = object.__new__(DocumentManager)
    dm.chunk_size, dm.chunk_overlap = CHUNK_SIZE, CHUNK_OVERLAP
    dm.client = MagicMock(get_max_batch_size=MagicMock(return_value=5000))
    dm.embedding_function = lambda texts: [[0.0, 1.0] for _ in texts]
    # Indexed under the name the user saw then; the row has been renamed since.
    _old_chunks(chroma, "src-reg", "Subpart E—Cost Principles", REGULATION)
    _old_chunks(chroma, "src-doc", "APM 45.13.pdf", POLICY)
    _old_chunks(chroma, "src-held", "Held page", "held text " * 50)
    _old_chunks(chroma, "src-edited", "Edited page", "the text that was indexed " * 50)
    sources = [
        {"uuid": "src-reg", "knowledge_base_uuid": "kb", "source_type": "url", "status": "ready",
         "content": REGULATION, "custom_name": "UG Subpart E", "content_hash": currency.content_fingerprint(REGULATION),
         "content_retrieved_at": T0, "created_at": T0},
        {"uuid": "src-doc", "knowledge_base_uuid": "kb", "source_type": "document", "status": "ready",
         "document_uuid": "doc-1", "created_at": T0},
        {"uuid": "src-held", "knowledge_base_uuid": "kb", "source_type": "url", "status": "held",
         "content": "held text " * 50, "created_at": T0},
        {"uuid": "src-edited", "knowledge_base_uuid": "kb", "source_type": "url", "status": "ready",
         "content": "a later text " * 50, "content_hash": currency.content_fingerprint("the text that was indexed " * 50),
         "created_at": T0},
        {"uuid": "src-failed", "knowledge_base_uuid": "kb", "source_type": "url", "status": "error", "created_at": T0},
    ]
    kb = {"uuid": "kb", "title": "OMB UG", "rag_config_override": {"k": 6, "min_similarity": 0.4}}
    db = _Db([kb], sources, [{"uuid": "doc-1", "title": "APM 45.13.pdf", "raw_text": POLICY,
                              "text_markers": [{"char_offset": 0, "kind": "page", "value": 3}]}])
    with patch.object(DocumentManager, "get_kb_collection", return_value=chroma), \
         patch.object(DocumentManager, "get_kb_collection_readonly", return_value=chroma):
        yield db, dm, chroma


def _actions(report):
    return {s.source_uuid: s.action for s in report.sources}


class TestRechunk:
    def test_a_dry_run_reports_and_writes_nothing(self, world):
        db, dm, chroma = world
        before = dict(chroma.rows)
        [report] = rc.rechunk_all(db, dm, dry_run=True)
        assert _actions(report) == {
            "src-reg": rc.WOULD_REBUILD, "src-doc": rc.WOULD_REBUILD,
            "src-held": rc.SKIPPED, "src-edited": rc.SKIPPED, "src-failed": rc.SKIPPED,
        }
        assert report.chunks_after == len(kc.chunk_source(REGULATION)) + len(kc.chunk_source(POLICY))
        assert chroma.rows == before
        assert db.source("src-reg").get("chunker_version") is None
        assert "rechunked_at" not in db.knowledge_bases.find_one({"uuid": "kb"})

    def test_ready_sources_are_rebuilt_from_their_stored_text(self, world):
        db, dm, chroma = world
        report = rc.rechunk_kb(db, dm, "kb")
        assert _actions(report)["src-reg"] == _actions(report)["src-doc"] == rc.REBUILT
        for sid in ("src-reg", "src-doc"):
            rows = chroma.of(sid)
            assert rows and all(r["metadata"]["chunker_version"] == kc.CHUNKER_VERSION for r in rows)
            row = db.source(sid)
            assert row["chunk_count"] == len(rows) and row["chunker_version"] == kc.CHUNKER_VERSION
            assert row["status"] == "ready" and row["last_ingested_at"] > T0
        # The text is the same as before, so its retrieval date stays.
        assert db.source("src-reg")["content_retrieved_at"] == T0
        # Citations keep the name the source was indexed under.
        assert {r["metadata"]["source_name"] for r in chroma.of("src-reg")} == {"Subpart E—Cost Principles"}
        # A document's page markers still place its chunks.
        assert {r["metadata"].get("page") for r in chroma.of("src-doc")} == {3}
        [beer] = [r for r in chroma.of("src-reg") if r["metadata"]["section_key"] == "200.423"]
        assert beer["document"].endswith("The cost of alcoholic beverages is unallowable.")
        kb = db.knowledge_bases.find_one({"uuid": "kb"})
        assert kb["rechunked_at"] is not None
        assert kb["total_chunks"] == len(chroma.of("src-reg")) + len(chroma.of("src-doc"))

    def test_what_is_not_ready_or_no_longer_matches_is_left_alone(self, world):
        db, dm, chroma = world
        held, edited = list(chroma.of("src-held")), list(chroma.of("src-edited"))
        report = rc.rechunk_kb(db, dm, "kb")
        reasons = {s.source_uuid: s.reason for s in report.sources}
        assert reasons["src-held"] == "status is held" and reasons["src-failed"] == "status is error"
        assert "differs from the indexed text" in reasons["src-edited"]
        assert chroma.of("src-held") == held and chroma.of("src-edited") == edited

    def test_a_second_run_finds_everything_current_and_writes_nothing(self, world):
        db, dm, chroma = world
        rc.rechunk_kb(db, dm, "kb")
        after = dict(chroma.rows)
        stamped = db.source("src-reg")["last_ingested_at"]
        report = rc.rechunk_kb(db, dm, "kb")
        assert _actions(report)["src-reg"] == _actions(report)["src-doc"] == rc.CURRENT
        assert chroma.rows == after
        assert db.source("src-reg")["last_ingested_at"] == stamped

    def test_two_sets_of_current_chunks_are_rebuilt_into_one(self, world):
        """Two writers racing on one source can leave both sets indexed."""
        db, dm, chroma = world
        rc.rechunk_kb(db, dm, "kb")
        dm.add_to_kb("kb", "src-reg", "Subpart E—Cost Principles", REGULATION, id_prefix="src-reg_race")
        assert len(chroma.of("src-reg")) == 2 * db.source("src-reg")["chunk_count"]
        report = rc.rechunk_kb(db, dm, "kb")
        assert _actions(report)["src-reg"] == rc.REBUILT
        assert len(chroma.of("src-reg")) == db.source("src-reg")["chunk_count"]

    def test_a_failed_swap_leaves_the_old_chunks_answering(self, world):
        db, dm, chroma = world
        old = sorted(r["document"] for r in chroma.of("src-reg"))
        chroma.fail_add = True
        report = rc.rechunk_kb(db, dm, "kb")
        outcome = next(s for s in report.sources if s.source_uuid == "src-reg")
        assert outcome.action == rc.FAILED and "embedding service went away" in outcome.reason
        assert sorted(r["document"] for r in chroma.of("src-reg")) == old
        assert db.source("src-reg")["status"] == "ready"
        assert "rechunked_at" not in db.knowledge_bases.find_one({"uuid": "kb"})

    def test_tuned_settings_are_kept_and_reported(self, world):
        db, dm, _ = world
        report = rc.rechunk_kb(db, dm, "kb")
        assert report.tuned_settings == {"k": 6, "min_similarity": 0.4}
        assert db.knowledge_bases.find_one({"uuid": "kb"})["rag_config_override"] == {"k": 6, "min_similarity": 0.4}
        assert report.as_dict()["counts"][rc.REBUILT] == 2


class TestOptimizedBadge:
    def _status(self, rechunked_at):
        return compute_optimization_status(
            rag_config_override={"min_similarity": 0.4}, override_set_at=T0, override_run_uuid=None,
            applied_run=None, latest_completed_run=None, sources=[], queries=[], rechunked_at=rechunked_at,
        )

    def test_settings_tuned_before_a_rechunk_read_stale(self):
        status = self._status(T0 + datetime.timedelta(days=3))
        assert status.state == "stale"
        assert any("re-chunked" in r for r in status.stale_reasons)

    def test_settings_tuned_after_a_rechunk_stand(self):
        assert self._status(T0 - datetime.timedelta(days=3)).state == "applied"
        assert self._status(None).state == "applied"
