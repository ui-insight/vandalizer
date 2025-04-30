#!/usr/bin/env python3

from app.celery_worker import celery_app
from app.models import SmartDocument
from devtools import debug
from app.utilities.agents import validate_document
import time
from celery.result import AsyncResult
from celery import chord, group
import asyncio
from app.utilities.agents import upload_agent, chat_agent
from app.utilities.document_readers import extract_text_from_doc
from app.utilities import config


import asyncio


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def validate_chunk(
    self, document_path: str, compliance: str, chunk_text: str, index: int, total: int
) -> dict:
    """
    Validate a single text chunk against compliance requirements.
    Returns a dict with keys: valid (bool), feedback (str), index (int).
    """
    try:
        prompt = f"""
        Validate chunk {index}/{total} of document {document_path}.
        Compliance Requirements:\n{compliance}
        Document Text Chunk:\n{chunk_text}
        """
        # Run the agent synchronously in its own event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(upload_agent.run(prompt))
        output = result.data
        return {"valid": output.valid, "feedback": output.feedback, "index": index}
    except Exception as exc:
        debug(f"Retrying chunk {index} due to error: {exc}")
        raise self.retry(exc=exc)


@celery_app.task
def summarize_results(results: list, document_uuid: str) -> dict:
    """
    Summarize validation feedback from all chunks and update the SmartDocument.
    """
    feedback_list = []
    all_valid = True
    for res in results:
        if not res["valid"]:
            all_valid = False
            feedback_list.append(f"Chunk {res['index']}: {res['feedback']}")

    if all_valid:
        combined = "All document sections passed validation."
    else:
        combined = "\n\n".join(feedback_list)

    # Summarize via chat_agent
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    summary = loop.run_until_complete(
        chat_agent.run(f"Summarize the following validation feedback:\n{combined}")
    )

    # Persist to DB
    doc = SmartDocument.objects(uuid=document_uuid).first()
    doc.valid = all_valid
    doc.validation_feedback = summary.data
    doc.save()
    debug(f"Document {document_uuid} validation updated: valid={all_valid}")
    return {"valid": all_valid, "feedback": summary.data}


@celery_app.task
def perform_document_validation(
    document_text: str,
    document_uuid: str,
    document_path: str,
    chunk_size: int = 8000,
):
    """
    Entry point: splits document, launches chunk validations, and the summarizer via a chord.
    """

    # Extract text if needed
    text = document_text or extract_text_from_doc(document_path)
    compliance = config.upload_compliance

    # Split into chunks
    chunked = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    total = len(chunked)
    debug(f"Launching {total} chunk validation tasks")

    # Build list of validate_chunk subtasks
    header = [
        validate_chunk.s(document_path, compliance, chunk_text, idx + 1, total)
        for idx, chunk_text in enumerate(chunked)
    ]

    # Use a chord to run summary after all chunks finish
    callback = summarize_results.s(document_uuid)
    chord(header)(callback)  # Executes validate_chunk tasks, then summarize_results

    return text
