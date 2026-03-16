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
    result = agent.run_sync(prompt)
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
) -> SmartDocument:
    """Apply a classification to a document and save."""
    document.classification = classification
    document.classification_confidence = confidence
    document.classified_at = datetime.datetime.now(tz=datetime.timezone.utc)
    document.classified_by = classified_by
    await document.save()
    return document
