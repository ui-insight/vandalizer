"""Tests for app.services.extraction_test_case_generator — the wizard's step 1.

If this produces garbage, users abandon at the first screen. We verify:
- Proposals are shaped correctly (no missing keys, full source snapshot)
- Coverage tier caps proposal count
- Per-doc failures don't kill the batch
- Approval persists with the right user/searchset binding
- Approval skips empty proposals
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import extraction_test_case_generator as gen
from app.services.extraction_test_case_generator import (
    COVERAGE_LIMITS,
    _derive_label,
    generate_proposals,
    persist_approved_proposals,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_derive_label_uses_title_minus_extension():
    doc = MagicMock()
    doc.title = "NSF Grant Proposal.pdf"
    doc.raw_text = "irrelevant"
    assert _derive_label(doc) == "NSF Grant Proposal"


def test_derive_label_falls_back_to_first_text_line():
    doc = MagicMock()
    doc.title = ""
    doc.raw_text = "Subject: Award letter\nMore text below."
    assert _derive_label(doc) == "Subject: Award letter"


def test_derive_label_handles_completely_empty_doc():
    doc = MagicMock()
    doc.title = None
    doc.raw_text = None
    assert _derive_label(doc) == "Untitled document"


def test_derive_label_truncates_long_titles():
    doc = MagicMock()
    doc.title = "x" * 500
    doc.raw_text = ""
    assert len(_derive_label(doc)) <= 120


def test_coverage_limits_ordered():
    """Quick < Standard < Exhaustive — sanity check on tier ordering."""
    assert COVERAGE_LIMITS["quick"] < COVERAGE_LIMITS["standard"] < COVERAGE_LIMITS["exhaustive"]


# ---------------------------------------------------------------------------
# generate_proposals
# ---------------------------------------------------------------------------


def _make_doc(uuid: str = "doc-1", title: str = "Test Doc", raw: str = "Body text here.") -> MagicMock:
    doc = MagicMock()
    doc.uuid = uuid
    doc.title = title
    doc.raw_text = raw
    return doc


@pytest.mark.asyncio
async def test_generate_proposals_raises_when_search_set_missing():
    with patch.object(gen, "get_search_set", new=AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="not found"):
            await generate_proposals(
                search_set_uuid="ghost", user_id="u1", document_uuids=["d1"],
            )


@pytest.mark.asyncio
async def test_generate_proposals_raises_without_keys():
    ss = MagicMock(); ss.uuid = "ss-1"
    with (
        patch.object(gen, "get_search_set", new=AsyncMock(return_value=ss)),
        patch.object(gen, "get_extraction_keys", new=AsyncMock(return_value=[])),
    ):
        with pytest.raises(ValueError, match="fields"):
            await generate_proposals(
                search_set_uuid="ss-1", user_id="u1", document_uuids=["d1"],
            )


@pytest.mark.asyncio
async def test_generate_proposals_returns_one_proposal_per_doc():
    ss = MagicMock(); ss.uuid = "ss-1"
    docs = {
        "d1": _make_doc("d1", "Award A.pdf", "Award letter for $1000 to Dr. Smith."),
        "d2": _make_doc("d2", "Award B.pdf", "Award letter for $2000 to Dr. Jones."),
    }
    extract_results = {
        "d1": [{"PI Name": "Dr. Smith", "Amount": "$1000"}],
        "d2": [{"PI Name": "Dr. Jones", "Amount": "$2000"}],
    }

    mock_engine_instance = MagicMock()
    def fake_extract(*, extract_keys, model, doc_texts, field_metadata, **_):
        # Match by doc text content
        for uuid, doc in docs.items():
            if doc.raw_text in doc_texts:
                return extract_results[uuid]
        return []
    mock_engine_instance.extract = fake_extract

    async def find_doc(query):
        # query is a Beanie expression like SmartDocument.uuid == "d1"; we
        # short-circuit by inspecting the test docs in order. Real query parsing
        # is exercised in integration tests.
        for uuid, doc in docs.items():
            if str(query.right.value) == uuid if hasattr(query, "right") else True:
                pass
        return None  # placeholder; replaced via side_effect below

    with (
        patch.object(gen, "get_search_set", new=AsyncMock(return_value=ss)),
        patch.object(gen, "get_extraction_keys", new=AsyncMock(return_value=["PI Name", "Amount"])),
        patch.object(gen, "get_extraction_field_metadata", new=AsyncMock(return_value=[])),
        patch.object(gen, "get_user_model_name", new=AsyncMock(return_value="m")),
        patch.object(gen, "SystemConfig") as MockSC,
        patch.object(gen, "ExtractionEngine", return_value=mock_engine_instance),
        patch.object(gen, "SmartDocument") as MockDoc,
    ):
        sys_cfg = MagicMock(); sys_cfg.model_dump = MagicMock(return_value={})
        MockSC.get_config = AsyncMock(return_value=sys_cfg)
        # find_one is called once per doc_uuid in input order
        MockDoc.find_one = AsyncMock(side_effect=[docs["d1"], docs["d2"]])
        MockDoc.uuid = MagicMock()

        out = await generate_proposals(
            search_set_uuid="ss-1", user_id="u1",
            document_uuids=["d1", "d2"],
            coverage="standard",
        )

    assert len(out["proposals"]) == 2
    p1, p2 = out["proposals"]
    # Per-proposal shape
    for p in out["proposals"]:
        assert "proposal_id" in p
        assert p["source_type"] == "document"
        assert "document_uuid" in p
        assert "source_text" in p
        assert "expected_values" in p
        assert p["auto_generated"] is True
        # Every requested key is present (empty string when not extracted)
        assert set(p["expected_values"].keys()) == {"PI Name", "Amount"}
    # Values come through
    assert p1["expected_values"]["PI Name"] == "Dr. Smith"
    assert p2["expected_values"]["PI Name"] == "Dr. Jones"


@pytest.mark.asyncio
async def test_generate_proposals_caps_at_coverage_limit():
    """Quick coverage limit (3) should cap doc count even when more are passed."""
    ss = MagicMock(); ss.uuid = "ss-1"
    doc = _make_doc("d", "T", "body")

    call_count = {"n": 0}
    def fake_extract(**kw):
        call_count["n"] += 1
        return [{"PI Name": "x"}]
    mock_engine = MagicMock(); mock_engine.extract = fake_extract

    with (
        patch.object(gen, "get_search_set", new=AsyncMock(return_value=ss)),
        patch.object(gen, "get_extraction_keys", new=AsyncMock(return_value=["PI Name"])),
        patch.object(gen, "get_extraction_field_metadata", new=AsyncMock(return_value=[])),
        patch.object(gen, "get_user_model_name", new=AsyncMock(return_value="m")),
        patch.object(gen, "SystemConfig") as MockSC,
        patch.object(gen, "ExtractionEngine", return_value=mock_engine),
        patch.object(gen, "SmartDocument") as MockDoc,
    ):
        sys_cfg = MagicMock(); sys_cfg.model_dump = MagicMock(return_value={})
        MockSC.get_config = AsyncMock(return_value=sys_cfg)
        MockDoc.find_one = AsyncMock(return_value=doc)
        MockDoc.uuid = MagicMock()

        # Pass 10 docs; quick tier caps at 3
        out = await generate_proposals(
            search_set_uuid="ss-1", user_id="u1",
            document_uuids=["d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8", "d9", "d10"],
            coverage="quick",
        )

    assert len(out["proposals"]) == COVERAGE_LIMITS["quick"]
    assert call_count["n"] == COVERAGE_LIMITS["quick"]


@pytest.mark.asyncio
async def test_generate_proposals_skips_missing_docs():
    """A doc whose lookup returns None is silently skipped, not crashing the batch."""
    ss = MagicMock(); ss.uuid = "ss-1"
    real_doc = _make_doc("d-real")

    def fake_extract(**kw):
        return [{"x": "y"}]
    mock_engine = MagicMock(); mock_engine.extract = fake_extract

    with (
        patch.object(gen, "get_search_set", new=AsyncMock(return_value=ss)),
        patch.object(gen, "get_extraction_keys", new=AsyncMock(return_value=["x"])),
        patch.object(gen, "get_extraction_field_metadata", new=AsyncMock(return_value=[])),
        patch.object(gen, "get_user_model_name", new=AsyncMock(return_value="m")),
        patch.object(gen, "SystemConfig") as MockSC,
        patch.object(gen, "ExtractionEngine", return_value=mock_engine),
        patch.object(gen, "SmartDocument") as MockDoc,
    ):
        sys_cfg = MagicMock(); sys_cfg.model_dump = MagicMock(return_value={})
        MockSC.get_config = AsyncMock(return_value=sys_cfg)
        # First doc missing, second exists
        MockDoc.find_one = AsyncMock(side_effect=[None, real_doc])
        MockDoc.uuid = MagicMock()

        out = await generate_proposals(
            search_set_uuid="ss-1", user_id="u1",
            document_uuids=["d-missing", "d-real"],
        )

    # One proposal for the real doc; missing doc just doesn't produce one
    assert len(out["proposals"]) == 1
    assert out["proposals"][0]["document_uuid"] == "d-real"


@pytest.mark.asyncio
async def test_generate_proposals_records_per_doc_errors():
    """Per-doc extraction failures are captured in errors, not raised."""
    ss = MagicMock(); ss.uuid = "ss-1"
    doc = _make_doc()

    mock_engine = MagicMock()
    mock_engine.extract = MagicMock(side_effect=RuntimeError("model down"))

    with (
        patch.object(gen, "get_search_set", new=AsyncMock(return_value=ss)),
        patch.object(gen, "get_extraction_keys", new=AsyncMock(return_value=["x"])),
        patch.object(gen, "get_extraction_field_metadata", new=AsyncMock(return_value=[])),
        patch.object(gen, "get_user_model_name", new=AsyncMock(return_value="m")),
        patch.object(gen, "SystemConfig") as MockSC,
        patch.object(gen, "ExtractionEngine", return_value=mock_engine),
        patch.object(gen, "SmartDocument") as MockDoc,
    ):
        sys_cfg = MagicMock(); sys_cfg.model_dump = MagicMock(return_value={})
        MockSC.get_config = AsyncMock(return_value=sys_cfg)
        MockDoc.find_one = AsyncMock(return_value=doc)
        MockDoc.uuid = MagicMock()

        out = await generate_proposals(
            search_set_uuid="ss-1", user_id="u1",
            document_uuids=["d1"],
        )

    assert out["proposals"] == []
    assert len(out["errors"]) == 1
    assert out["errors"][0]["document_uuid"] == "d1"
    assert "model down" in out["errors"][0]["reason"]


# ---------------------------------------------------------------------------
# persist_approved_proposals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_approved_proposals_creates_test_cases():
    proposals = [
        {
            "proposal_id": "p1",
            "label": "Award A",
            "source_type": "document",
            "document_uuid": "d1",
            "source_text": "Body A",
            "expected_values": {"PI Name": "Smith", "Amount": "$1000"},
        },
        {
            "proposal_id": "p2",
            "label": "Award B",
            "source_type": "document",
            "document_uuid": "d2",
            "source_text": "Body B",
            "expected_values": {"PI Name": "Jones"},
        },
    ]

    inserted: list = []

    class FakeExtractionTestCase:
        def __init__(self, **data):
            self.uuid = "tc-" + data.get("label", "?")
            for k, v in data.items():
                setattr(self, k, v)
        async def insert(self):
            inserted.append(self)

    with patch.object(gen, "ExtractionTestCase", FakeExtractionTestCase):
        saved = await persist_approved_proposals(
            search_set_uuid="ss-1", user_id="u1", proposals=proposals,
        )

    assert len(saved) == 2
    assert len(inserted) == 2
    assert all(tc.search_set_uuid == "ss-1" for tc in saved)
    assert all(tc.user_id == "u1" for tc in saved)


@pytest.mark.asyncio
async def test_persist_approved_proposals_skips_empty():
    """Proposals with no non-empty values are skipped — they'd be dead test cases."""
    proposals = [
        {
            "label": "Empty",
            "source_type": "document",
            "document_uuid": "d1",
            "source_text": "x",
            "expected_values": {"PI Name": "", "Amount": ""},
        },
        {
            "label": "Has values",
            "source_type": "document",
            "document_uuid": "d2",
            "source_text": "y",
            "expected_values": {"PI Name": "Smith"},
        },
    ]

    class FakeExtractionTestCase:
        def __init__(self, **data):
            for k, v in data.items():
                setattr(self, k, v)
        async def insert(self):
            pass

    with patch.object(gen, "ExtractionTestCase", FakeExtractionTestCase):
        saved = await persist_approved_proposals(
            search_set_uuid="ss-1", user_id="u1", proposals=proposals,
        )

    # Only the proposal with non-empty values survives
    assert len(saved) == 1
    assert saved[0].label == "Has values"


@pytest.mark.asyncio
async def test_persist_approved_proposals_skips_malformed():
    """Non-dict entries in the list are skipped, not raised."""
    class FakeExtractionTestCase:
        def __init__(self, **data):
            for k, v in data.items():
                setattr(self, k, v)
        async def insert(self):
            pass

    with patch.object(gen, "ExtractionTestCase", FakeExtractionTestCase):
        saved = await persist_approved_proposals(
            search_set_uuid="ss-1", user_id="u1",
            proposals=[
                None,
                "not a dict",
                {"label": "Real", "source_type": "document", "expected_values": {"x": "y"}},
            ],
        )
    assert len(saved) == 1
    assert saved[0].label == "Real"
