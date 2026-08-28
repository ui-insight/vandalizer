"""Celery tasks for upload validation via LLM (chord pattern).

Ported from Flask app/utilities/upload_manager.py.
Uses pymongo (sync) for DB access.
"""

import logging
import os
import time

from celery import chord

from app.celery_app import celery_app
from app.tasks import TRANSIENT_EXCEPTIONS
from app.services.ocr_client import OcrUnavailableError

logger = logging.getLogger(__name__)

BUDGET_SKIPPED_FEEDBACK = (
    "compliance validation was skipped because the trial token budget is exhausted."
)


def _get_db():
    """Get sync pymongo database handle (shared per-process client)."""
    from app.tasks import get_sync_db

    return get_sync_db()


_DEFAULT_COMPLIANCE_RULES = (
    "Check that the document does not contain any sensitive PII data "
    "that should not be processed by an external LLM. Flag SSNs, credit "
    "card numbers, medical records, or classified information."
)


def _get_compliance_settings() -> dict:
    """Fetch compliance settings from SystemConfig.compliance_config.

    Falls back to the legacy `upload_compliance` string field for older
    configs that haven't been migrated. Returns a dict with at least
    `enabled`, `rules`, `chunk_size`, and `chunk_overlap`.
    """
    db = _get_db()
    sys_cfg = db.system_config.find_one() or {}
    compliance = sys_cfg.get("compliance_config") or {}
    legacy_rules = sys_cfg.get("upload_compliance")
    return {
        "enabled": bool(compliance.get("enabled", False)),
        "check_on_upload": bool(compliance.get("check_on_upload", True)),
        "rules": compliance.get("rules") or legacy_rules or _DEFAULT_COMPLIANCE_RULES,
        "chunk_size": int(compliance.get("chunk_size") or 8000),
        "chunk_overlap": int(compliance.get("chunk_overlap") or 200),
    }


def _get_compliance_rules() -> str:
    """Return the compliance rule prompt (used by chunk validation)."""
    return _get_compliance_settings()["rules"]


def _get_secure_agent():
    """Get a validation agent (uses default model)."""
    from app.services.llm_service import create_chat_agent

    db = _get_db()
    sys_cfg = db.system_config.find_one() or {}
    models = sys_cfg.get("available_models", [])
    model_name = models[0]["name"] if models else "gpt-4o-mini"

    return create_chat_agent(
        model_name,
        system_prompt=(
            "You are a document compliance validator. Analyze text for policy "
            "violations and sensitive data exposure. Respond with a JSON object: "
            '{"valid": true/false, "feedback": "explanation"}. Be concise.'
        ),
        system_config_doc=sys_cfg,
    )


@celery_app.task(
    bind=True,
    name="tasks.upload.validation.chunk",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=5,
    rate_limit="1/s",
)
def validate_chunk(
    self,
    document_path: str,
    compliance: str,
    chunk_text: str,
    index: int,
    total: int,
    user_id: str | None = None,
) -> dict:
    """Validate a single text chunk against compliance requirements.

    ``user_id`` attributes the LLM spend to the uploader. A trial account that
    has exhausted its token budget gets the chunk marked *skipped* rather than
    a retry storm: a compliance check the deployment could not afford to run is
    reported as such, the same way a disabled check is, and the chord still
    completes so the document does not sit in ``validating`` forever.
    """
    logger.info("Validating chunk %d/%d of %s", index, total, document_path)
    try:
        agent = _get_secure_agent()
        prompt = (
            f"Validate chunk {index}/{total} of document {document_path}.\n"
            f"Compliance Requirements:\n{compliance}\n"
            f"Document Text Chunk:\n{chunk_text}"
        )
        from app.exceptions import TrialSpendBlockedError
        from app.services.metering import metered
        try:
            with metered("upload_validation", user_id=user_id):
                result = agent.run_sync(prompt)
        except TrialSpendBlockedError as blocked:
            # Any trial gate — exhausted budget, unconfirmed email, fleet pause
            # — is a "couldn't afford to run it" not a failure. Skip the chunk
            # so the chord completes and the document doesn't sit in
            # ``validating`` forever, and report the gate's own reason so the
            # feedback says which one it was.
            logger.info(
                "Trial spend blocked for %s (%s) — skipping compliance chunk %d/%d of %s",
                user_id, type(blocked).__name__, index, total, document_path,
            )
            return {
                "valid": True,
                "feedback": blocked.message or BUDGET_SKIPPED_FEEDBACK,
                "index": index,
                "skipped": True,
            }
        output = result.output

        # Parse structured output or treat as text
        if hasattr(output, "valid"):
            return {"valid": output.valid, "feedback": output.feedback, "index": index}

        # Try JSON parsing from string output
        import json
        try:
            parsed = json.loads(str(output))
            return {
                "valid": parsed.get("valid", True),
                "feedback": parsed.get("feedback", ""),
                "index": index,
            }
        except (json.JSONDecodeError, TypeError):
            # Default to valid if we can't parse
            return {"valid": True, "feedback": str(output), "index": index}

    except Exception as e:
        logger.warning("Retrying chunk %d due to error: %s", index, e)
        raise self.retry(exc=e)


@celery_app.task(
    bind=True,
    name="tasks.upload.validation.summary",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=5,
    rate_limit="1/s",
)
def summarize_results(
    self,
    results: list,
    document_uuid: str,
    background: bool = False,
    user_id: str | None = None,
) -> dict:
    """Aggregate validation feedback from all chunks and update SmartDocument."""
    feedback_list = []
    all_valid = True
    skipped = 0
    for res in results:
        if res.get("skipped"):
            skipped += 1
            continue
        if not res.get("valid", True):
            all_valid = False
            feedback_list.append(f"Chunk {res.get('index')}: {res.get('feedback', '')}")

    if skipped:
        # Say what was not checked instead of reporting a clean pass over
        # sections nobody read.
        feedback_list.append(
            f"{skipped} of {len(results)} sections were not checked: {BUDGET_SKIPPED_FEEDBACK}"
        )
    if all_valid and not skipped:
        combined = "All document sections passed validation."
    else:
        combined = "\n\n".join(feedback_list)

    # Summarize via LLM
    from app.exceptions import TrialBudgetExceededError, TrialSpendBlockedError
    try:
        if skipped:
            # Whatever gate skipped the chunks still applies; don't spend more
            # summarizing the fact.
            raise TrialBudgetExceededError(BUDGET_SKIPPED_FEEDBACK)
        agent = _get_secure_agent()
        from app.services.metering import metered
        with metered("upload_validation", user_id=user_id):
            summary_result = agent.run_sync(
                f"Analyze this validation feedback and return a structured response.\n"
                f'Validation results: {"PASSED" if all_valid else "FAILED"}\n\n'
                f"Validation feedback:\n{combined}\n\n"
                f"Return:\n"
                f"- valid: {str(all_valid).lower()}\n"
                f'- feedback: {"Confirm all sections passed validation" if all_valid else "Concise summary of failures and required fixes"}'
            )
        output = summary_result.output

        if hasattr(output, "model_dump"):
            summary = output.model_dump()
        else:
            summary = {"valid": all_valid, "feedback": str(output)}

    except TrialSpendBlockedError:
        summary = {"valid": all_valid, "feedback": combined[:2000]}
    except Exception as e:
        logger.error("Error summarizing results: %s", e)
        summary = {"valid": all_valid, "feedback": combined[:2000]}

    # Persist to DB
    db = _get_db()
    update_fields = {
        "valid": all_valid,
        "validation_feedback": summary.get("feedback", ""),
        "validating": False,
    }

    db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": update_fields},
    )
    # Compliance validation says nothing about whether the text could be read,
    # so it must not overwrite an extraction failure with a green checkmark.
    if not background:
        from app.tasks.document_tasks import mark_complete_unless_errored

        mark_complete_unless_errored(db, document_uuid)

    logger.info(
        "Document %s validation updated: valid=%s, background=%s",
        document_uuid, all_valid, background,
    )
    return summary


@celery_app.task(
    bind=True,
    name="tasks.upload.validation",
    autoretry_for=TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    max_retries=3,
    default_retry_delay=5,
    rate_limit="1/s",
)
def perform_document_validation(
    self,
    document_uuid: str,
    document_path: str,
    document_text: str = None,
    chunk_size: int = 8000,
    chunk_overlap: int = 200,
    background: bool = False,
    user_id: str | None = None,
) -> str:
    """Entry point: split document text, launch chunk validations via chord."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    db = _get_db()

    settings = _get_compliance_settings()
    if not settings["enabled"] or not (settings["rules"] or "").strip():
        # Compliance checks are off — mark the document as valid and skip.
        skip_fields = {
            "valid": True,
            "validation_feedback": "Compliance checks disabled.",
            "validating": False,
        }
        db.smart_document.update_one(
            {"uuid": document_uuid},
            {"$set": skip_fields},
        )
        # Skipping a check the deployment turned off is not evidence that the
        # document was read successfully.
        if not background:
            from app.tasks.document_tasks import mark_complete_unless_errored

            mark_complete_unless_errored(db, document_uuid)
        logger.info("Compliance disabled — skipping validation for %s", document_uuid)
        return ""

    db.smart_document.update_one(
        {"uuid": document_uuid}, {"$set": {"validating": True}}
    )
    if not background:
        # Same guard as every other status write: an in-progress marker on a
        # document that already failed extraction erases the failure.
        from app.tasks.document_tasks import advance_task_status

        advance_task_status(db, document_uuid, "security")

    start = time.perf_counter()

    # Get text
    text = document_text
    if not text:
        doc = db.smart_document.find_one({"uuid": document_uuid})
        text = doc.get("raw_text", "") if doc else ""

    if not text:
        # Try reading from file. Resolve the path the same way the extraction
        # task does: prefer the doc's stored (relative) path joined onto
        # upload_dir. Callers pass ``document_path`` inconsistently — some an
        # absolute local path, some the bare relative ``doc.path`` — and a
        # relative path fails to open from the worker's CWD (the "[Errno 2] No
        # such file" OCR failures on tasks.upload.validation).
        from app.config import Settings
        from app.services.document_readers import extract_text_from_file

        rel_or_abs = (doc.get("path") if doc else "") or document_path or ""
        file_path = (
            rel_or_abs
            if os.path.isabs(rel_or_abs)
            else os.path.join(Settings().upload_dir, rel_or_abs)
        )
        ext = os.path.splitext(file_path)[1].lstrip(".")
        try:
            text = extract_text_from_file(file_path, ext)
        except OcrUnavailableError as e:
            # A transient OCR outage is worth waiting out: the retry runs
            # minutes later, by which point the extraction task has usually
            # written raw_text and this task never needs OCR at all. Only once
            # retries are spent does it degrade to "nothing to validate" like
            # any other read failure — see the catch-all below.
            if self.request.retries < self.max_retries:
                logger.warning(
                    "OCR unavailable for validation of %s (attempt %d/%d) — retrying: %s",
                    document_uuid, self.request.retries + 1, self.max_retries, e,
                )
                raise
            logger.warning(
                "OCR still unavailable for validation of %s after %d attempts; "
                "validating empty text",
                document_uuid, self.max_retries,
            )
            text = ""
        except Exception as e:
            # The extraction task owns reporting read failures (it marks the
            # document errored and notifies). For compliance validation a
            # failed read just means nothing to validate: empty text produces
            # zero chunks and the chord callback still runs, so the
            # "validating" flag clears instead of stalling forever.
            logger.warning(
                "Validation text read failed for %s: %s", document_uuid, e,
            )
            text = ""

    compliance = settings["rules"]
    effective_chunk_size = chunk_size or settings["chunk_size"]
    effective_chunk_overlap = chunk_overlap if chunk_overlap is not None else settings["chunk_overlap"]

    # Split into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=effective_chunk_size, chunk_overlap=effective_chunk_overlap,
    )
    chunks = text_splitter.split_text(text)
    total = len(chunks)
    logger.info("Launching %d chunk validation tasks for %s", total, document_uuid)

    # Build chord: validate all chunks, then summarize
    header = [
        validate_chunk.s(document_path, compliance, chunk_text, idx + 1, total, user_id=user_id)
        for idx, chunk_text in enumerate(chunks)
    ]
    callback = summarize_results.s(document_uuid, background, user_id=user_id)
    chord(header)(callback)

    elapsed = time.perf_counter() - start
    logger.info("perform_document_validation[%s] dispatched in %.2fs", document_uuid, elapsed)

    return text
