"""Celery tasks for upload validation via LLM (chord pattern).

Ported from Flask app/utilities/upload_manager.py.
Uses pymongo (sync) for DB access.
"""

import logging
import os
import time

from celery import chord

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _get_db():
    """Get sync pymongo database handle."""
    from pymongo import MongoClient

    from app.config import Settings
    settings = Settings()
    client = MongoClient(settings.mongo_host)
    return client[settings.mongo_db]


def _get_compliance_rules() -> str:
    """Fetch compliance rules from SystemConfig."""
    db = _get_db()
    sys_cfg = db.system_config.find_one() or {}
    return sys_cfg.get("upload_compliance", (
        "Check that the document does not contain any sensitive PII data "
        "that should not be processed by an external LLM. Flag SSNs, credit "
        "card numbers, medical records, or classified information."
    ))


def _get_secure_agent():
    """Get a validation agent (uses default model)."""
    from app.services.llm_service import create_chat_agent, get_agent_model

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
    autoretry_for=(Exception,),
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
) -> dict:
    """Validate a single text chunk against compliance requirements."""
    logger.info("Validating chunk %d/%d of %s", index, total, document_path)
    try:
        agent = _get_secure_agent()
        prompt = (
            f"Validate chunk {index}/{total} of document {document_path}.\n"
            f"Compliance Requirements:\n{compliance}\n"
            f"Document Text Chunk:\n{chunk_text}"
        )
        result = agent.run_sync(prompt)
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
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=5,
    rate_limit="1/s",
)
def summarize_results(
    self,
    results: list,
    document_uuid: str,
    background: bool = False,
) -> dict:
    """Aggregate validation feedback from all chunks and update SmartDocument."""
    feedback_list = []
    all_valid = True
    for res in results:
        if not res.get("valid", True):
            all_valid = False
            feedback_list.append(f"Chunk {res.get('index')}: {res.get('feedback', '')}")

    if all_valid:
        combined = "All document sections passed validation."
    else:
        combined = "\n\n".join(feedback_list)

    # Summarize via LLM
    try:
        agent = _get_secure_agent()
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
    if not background:
        update_fields["task_status"] = "complete"

    db.smart_document.update_one(
        {"uuid": document_uuid},
        {"$set": update_fields},
    )

    logger.info(
        "Document %s validation updated: valid=%s, background=%s",
        document_uuid, all_valid, background,
    )
    return summary


@celery_app.task(
    bind=True,
    name="tasks.upload.validation",
    autoretry_for=(Exception,),
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
) -> str:
    """Entry point: split document text, launch chunk validations via chord."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    db = _get_db()

    update_fields = {"validating": True}
    if not background:
        update_fields["task_status"] = "security"
    db.smart_document.update_one({"uuid": document_uuid}, {"$set": update_fields})

    start = time.perf_counter()

    # Get text
    text = document_text
    if not text:
        doc = db.smart_document.find_one({"uuid": document_uuid})
        text = doc.get("raw_text", "") if doc else ""

    if not text:
        # Try reading from file
        from app.services.document_readers import extract_text_from_file
        ext = os.path.splitext(document_path)[1].lstrip(".")
        text = extract_text_from_file(document_path, ext)

    compliance = _get_compliance_rules()

    # Split into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
    )
    chunks = text_splitter.split_text(text)
    total = len(chunks)
    logger.info("Launching %d chunk validation tasks for %s", total, document_uuid)

    # Build chord: validate all chunks, then summarize
    header = [
        validate_chunk.s(document_path, compliance, chunk_text, idx + 1, total)
        for idx, chunk_text in enumerate(chunks)
    ]
    callback = summarize_results.s(document_uuid, background)
    chord(header)(callback)

    elapsed = time.perf_counter() - start
    logger.info("perform_document_validation[%s] dispatched in %.2fs", document_uuid, elapsed)

    return text
