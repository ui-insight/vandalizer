"""FERPA-aware document classification service."""

import datetime
import logging
from typing import Optional

from app.models.document import SmartDocument
from app.models.system_config import SystemConfig
from app.services.llm_service import create_chat_agent

logger = logging.getLogger(__name__)

CLASSIFICATION_SYSTEM_PROMPT = """\
You are a data classification specialist for a university research administration system.
Classify the document into exactly ONE of these categories:

- unrestricted: Public or general information with no sensitivity
- internal: Internal university business, not public but not regulated
- ferpa: Contains student education records protected by FERPA (grades, transcripts, student IDs, enrollment, financial aid, disciplinary records)
- cui: Controlled Unclassified Information (federal contract data, export-controlled research data, PII beyond FERPA)
- itar: International Traffic in Arms Regulations data (defense articles, technical data related to defense)

Respond with ONLY a JSON object: {"classification": "<level>", "confidence": <0.0-1.0>, "reason": "<brief reason>"}
Do not include any other text.
"""

MAX_TEXT_LENGTH = 15000


def _prepare_text_sample(raw_text: str) -> str:
    """Take head + tail of document text for classification."""
    if len(raw_text) <= MAX_TEXT_LENGTH:
        return raw_text
    half = MAX_TEXT_LENGTH // 2
    return raw_text[:half] + "\n\n[...truncated...]\n\n" + raw_text[-half:]


async def classify_document(
    document: SmartDocument,
    model: Optional[str] = None,
    system_config_doc: Optional[dict] = None,
) -> dict:
    """Classify a document using LLM analysis.

    Returns dict with classification, confidence, reason.
    """
    if not document.raw_text:
        return {
            "classification": "unrestricted",
            "confidence": 0.5,
            "reason": "No text content available for classification",
        }

    text_sample = _prepare_text_sample(document.raw_text)
    prompt = f"Classify this document:\n\nTitle: {document.title}\nFile type: {document.extension}\n\nContent:\n{text_sample}"

    config = await SystemConfig.get_config()
    if not model:
        ext_cfg = config.get_extraction_config()
        model = ext_cfg.get("model") or "gpt-4o-mini"

    agent = create_chat_agent(
        model,
        system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
        system_config_doc=system_config_doc,
    )
    # Must use the async API: classify_document runs inside an already-running
    # event loop (the Celery classify task drives it with run_until_complete).
    # agent.run_sync() would start a second loop → "This event loop is already
    # running" and classification fails on every document.
    result = await agent.run(prompt)
    output = result.output

    import json
    try:
        parsed = json.loads(output)
        classification = parsed.get("classification", "unrestricted")
        confidence = float(parsed.get("confidence", 0.5))
        reason = parsed.get("reason", "")
    except (json.JSONDecodeError, TypeError, ValueError):
        # Fallback: try to extract classification from text
        valid_levels = {"unrestricted", "internal", "ferpa", "cui", "itar"}
        classification = "unrestricted"
        for level in valid_levels:
            if level in (output or "").lower():
                classification = level
                break
        confidence = 0.3
        reason = "Parsed from free-text response"

    return {
        "classification": classification,
        "confidence": confidence,
        "reason": reason,
    }


async def apply_classification(
    document: SmartDocument,
    classification: str,
    confidence: float,
    classified_by: str = "auto",
) -> Optional[SmartDocument]:
    """Write only classification fields, rejecting obsolete automatic results.

    A classifier can wait for a model while extraction, a retry or a manual
    classification changes the document. Saving the whole original model here
    would restore stale text and processing state (and could resurrect a delete).
    """
    expected = {
        '_id': document.id, 'uuid': document.uuid,
        'user_id': document.user_id, 'team_id': document.team_id, 'folder': document.folder,
        'soft_deleted': {'$ne': True},
    }
    if classified_by in {'auto', 'default'}:
        # An explicit human decision takes precedence over background enrichment.
        if document.classification and document.classified_by not in {None, 'auto', 'default'}:
            return None
        for field in (
            'raw_text', 'title', 'extension', 'path', 'downloadpath',
            'classification', 'classification_confidence', 'classified_at', 'classified_by',
        ):
            expected[field] = {'$eq': getattr(document, field)}
        revision = document._extraction_restart_revision
        if revision == 0:
            expected['$or'] = [
                {'_extraction_restart_revision': {'$exists': False}},
                {'_extraction_restart_revision': 0},
            ]
        else:
            expected['_extraction_restart_revision'] = revision
    values = {
        'classification': classification,
        'classification_confidence': confidence,
        'classified_at': datetime.datetime.now(tz=datetime.timezone.utc),
        'classified_by': classified_by,
    }
    result = await SmartDocument.get_motor_collection().update_one(expected, {'$set': values})
    if result.matched_count != 1:
        return None
    for field, value in values.items():
        setattr(document, field, value)
    return document
