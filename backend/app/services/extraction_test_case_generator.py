"""Test-case auto-generator — proposes expected values for an extraction's
fields from a set of source documents.

The wizard's step 1 calls this so users with zero test cases aren't dead
in the water. Generated proposals are NOT immediately saved — the user
reviews and approves before they become ``ExtractionTestCase`` records.
This avoids the "extract once, save as truth" bias where current config
mistakes get baked into the ground truth.

Strategy: call the user's current model in a "proposal mode" with the
field definitions + the full document text, ask for confident answers
only (skip uncertain fields, return ``""`` instead of guessing). Each
document becomes one proposed test case.

Phase 1B: proposals are returned as plain dicts. Approval persists them
as ``ExtractionTestCase`` records via ``persist_approved_proposals``.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

from app.models.document import SmartDocument
from app.models.extraction_test_case import ExtractionTestCase
from app.models.system_config import SystemConfig
from app.services.config_service import get_user_model_name
from app.services.extraction_engine import ExtractionEngine
from app.services.search_set_service import (
    get_extraction_field_metadata,
    get_extraction_keys,
    get_search_set,
)

logger = logging.getLogger(__name__)


# Coverage tiers map to max-documents-to-process. We don't iterate inside a
# document — each doc produces exactly one proposal — so the tier just caps
# how many proposals we generate per generate-call.
COVERAGE_LIMITS: dict[str, int] = {
    "quick": 3,
    "standard": 5,
    "exhaustive": 10,
}


async def generate_proposals(
    search_set_uuid: str,
    user_id: str,
    document_uuids: list[str],
    coverage: str = "standard",
    model_name: str | None = None,
) -> dict:
    """Generate proposed test cases for review.

    Returns:
        {
          "proposals": [{proposal_id, label, source_type, document_uuid,
                         source_text, expected_values}],
          "errors": [{document_uuid, reason}],  # docs we couldn't process
        }

    Proposals are NOT saved. The caller passes approved proposals back to
    ``persist_approved_proposals`` to convert them into ExtractionTestCase
    records.
    """
    ss = await get_search_set(search_set_uuid)
    if not ss:
        raise ValueError(f"SearchSet not found: {search_set_uuid}")

    keys = await get_extraction_keys(search_set_uuid)
    if not keys:
        raise ValueError("No extraction fields defined")

    field_metadata = await get_extraction_field_metadata(search_set_uuid)

    limit = COVERAGE_LIMITS.get(coverage, COVERAGE_LIMITS["standard"])
    document_uuids = list(document_uuids)[:limit]
    if not document_uuids:
        return {"proposals": [], "errors": []}

    if not model_name:
        model_name = await get_user_model_name(user_id)

    sys_config = await SystemConfig.get_config()
    sys_config_doc = sys_config.model_dump() if sys_config else {}
    engine = ExtractionEngine(system_config_doc=sys_config_doc)

    proposals: list[dict] = []
    errors: list[dict] = []

    for doc_uuid in document_uuids:
        try:
            proposal = await _propose_for_document(
                doc_uuid=doc_uuid,
                keys=keys,
                field_metadata=field_metadata,
                model_name=model_name,
                engine=engine,
            )
            if proposal is not None:
                proposals.append(proposal)
        except Exception as e:
            logger.warning("Proposal generation failed for doc %s: %s", doc_uuid, e)
            errors.append({"document_uuid": doc_uuid, "reason": str(e)[:200]})

    return {"proposals": proposals, "errors": errors}


async def _propose_for_document(
    *,
    doc_uuid: str,
    keys: list[str],
    field_metadata: list[dict],
    model_name: str,
    engine: ExtractionEngine,
) -> dict | None:
    """Run extraction once on a document and shape the result as a proposal."""
    import asyncio

    doc = await SmartDocument.find_one(SmartDocument.uuid == doc_uuid)
    if not doc or not doc.raw_text:
        return None

    # Extract with no config overrides — we want the cleanest, most-conservative
    # values for the user to review. The user can edit before approving.
    result = await asyncio.to_thread(
        engine.extract,
        extract_keys=keys,
        model=model_name,
        doc_texts=[doc.raw_text],
        field_metadata=field_metadata,
    )

    # Flatten the list-of-dicts result into a single dict[field, value]
    expected_values: dict[str, str] = {}
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                for k, v in item.items():
                    if v is None:
                        continue
                    expected_values[str(k)] = str(v).strip()

    # Ensure every requested key is present (empty string when not extracted —
    # the user can fill in or remove during review).
    for key in keys:
        if key not in expected_values:
            expected_values[key] = ""

    return {
        "proposal_id": uuid4().hex,
        "label": _derive_label(doc),
        "source_type": "document",
        "document_uuid": doc_uuid,
        "source_text": doc.raw_text,  # snapshot — test case is reproducible even if doc changes
        "expected_values": expected_values,
        "auto_generated": True,
    }


def _derive_label(doc: SmartDocument) -> str:
    """Compact human-readable label for a document-derived proposal."""
    title = (getattr(doc, "title", None) or "").strip()
    if title:
        # Strip extension and condense whitespace
        title = re.sub(r"\.\w{2,5}$", "", title)
        title = re.sub(r"\s+", " ", title)
        return title[:120]
    # Fallback: first non-empty line of raw text
    text = (getattr(doc, "raw_text", None) or "").strip()
    if text:
        first_line = text.split("\n", 1)[0].strip()
        return first_line[:80] or "Untitled document"
    return "Untitled document"


async def persist_approved_proposals(
    *,
    search_set_uuid: str,
    user_id: str,
    proposals: list[dict],
) -> list[ExtractionTestCase]:
    """Convert approved proposals into persisted ExtractionTestCase records.

    Each proposal becomes one ExtractionTestCase. The ``proposal_id`` field
    is discarded; a fresh UUID is assigned on insert.

    Validates each proposal has the required minimum shape; silently skips
    malformed entries rather than raising — the caller probably picked from
    a UI list and a bad entry shouldn't kill the whole approve operation.
    """
    saved: list[ExtractionTestCase] = []
    for p in proposals:
        if not isinstance(p, dict):
            continue
        source_type = p.get("source_type", "document")
        expected = p.get("expected_values") or {}
        if not isinstance(expected, dict) or not any(v for v in expected.values()):
            # Skip proposals with no actual content
            continue
        label = (p.get("label") or "").strip() or "Untitled"
        tc = ExtractionTestCase(
            search_set_uuid=search_set_uuid,
            label=label[:200],
            source_type=str(source_type),
            source_text=p.get("source_text"),
            document_uuid=p.get("document_uuid"),
            expected_values={str(k): str(v) for k, v in expected.items()},
            user_id=user_id,
        )
        await tc.insert()
        saved.append(tc)
    return saved
