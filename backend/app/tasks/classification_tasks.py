"""Celery tasks for document classification."""

import logging

from app.celery_app import celery
from app.tasks import TRANSIENT_EXCEPTIONS, run_task_async

logger = logging.getLogger(__name__)


@celery.task(name="tasks.document.classify", bind=True, retry_backoff=True, max_retries=2, default_retry_delay=30)
def classify_document_task(self, document_uuid: str):
    """Auto-classify a document after text extraction.

    Auto-classification is best-effort enrichment: a model failure must not
    crash document processing or page Sentry as an unhandled task. Transient
    connection blips (``ModelAPIError`` — pydantic-ai's connect/transport
    wrapper — and the OS-level transients) get a couple retries; a permanent
    model error (``ModelHTTPError``, e.g. a 401 from a misconfigured API key,
    a ``ModelAPIError`` subclass so it must be caught first) or exhausted
    retries leave the document unclassified and are logged at warning. We do
    not stamp a guessed classification on failure — silently marking a
    possibly-sensitive document "unrestricted" is worse than leaving it
    unclassified for a later re-run or manual reclassification.
    """
    from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

    try:
        run_task_async(_classify(document_uuid))
    except ModelHTTPError as exc:
        logger.warning(
            "Auto-classification skipped for %s — model returned HTTP %s "
            "(likely misconfigured model/API key); leaving unclassified: %s",
            document_uuid, getattr(exc, "status_code", "?"), exc,
        )
    except (ModelAPIError, *TRANSIENT_EXCEPTIONS) as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        logger.warning(
            "Auto-classification skipped for %s after %d retries — transient "
            "model error; leaving unclassified: %s",
            document_uuid, self.request.retries, exc,
        )


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

    from app.services.metering import metered_async
    async with metered_async(
        "classification", user_id=doc.user_id, team_id=doc.team_id
    ):
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
