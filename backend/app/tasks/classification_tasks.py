"""Celery tasks for document classification."""

import asyncio
import logging

from app.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="tasks.document.classify", bind=True, autoretry_for=(Exception,), max_retries=2, default_retry_delay=30)
def classify_document_task(self, document_uuid: str):
    """Auto-classify a document after text extraction."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_classify(document_uuid))
    finally:
        loop.close()


async def _classify(document_uuid: str):
    from app.database import init_db
    from app.config import Settings

    settings = Settings()
    await init_db(settings)

    from app.models.document import SmartDocument
    from app.models.system_config import SystemConfig
    from app.services.classification_service import classify_document, apply_classification

    doc = await SmartDocument.find_one(SmartDocument.uuid == document_uuid)
    if not doc:
        logger.warning("Document %s not found for classification", document_uuid)
        return

    config = await SystemConfig.get_config()
    cls_config = config.get_classification_config()

    if not cls_config.get("enabled") or not cls_config.get("auto_classify_on_upload"):
        # Apply default classification
        if not doc.classification:
            await apply_classification(
                doc,
                classification=cls_config.get("default_classification", "unrestricted"),
                confidence=1.0,
                classified_by="default",
            )
        return

    result = await classify_document(doc)
    await apply_classification(
        doc,
        classification=result["classification"],
        confidence=result["confidence"],
        classified_by="auto",
    )
    logger.info(
        "Document %s classified as %s (confidence: %.2f)",
        document_uuid,
        result["classification"],
        result["confidence"],
    )
