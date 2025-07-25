#!/usr/bin/env python3

import asyncio
import time

from celery import chord
from devtools import debug
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.celery_worker import celery_app
from app.models import SmartDocument
from app.utilities.agents import create_chat_agent, upload_agent
from app.utilities.config import settings
from app.utilities.document_readers import extract_text_from_doc

load_dotenv()


chat_agent = create_chat_agent(settings.base_model)


@celery_app.task(bind=True, name="tasks.upload.validation.chunk",
                    autoretry_for=(Exception,),
                 max_retries=3, default_retry_delay=5, rate_limit="1/s")
def validate_chunk(
    self, document_path: str, compliance: str, chunk_text: str, index: int, total: int
) -> dict:
    """
    Validate a single text chunk against compliance requirements.
    Returns a dict with keys: valid (bool), feedback (str), index (int).
    """
    debug(
        f"Validating chunk {index}/{total} of document {document_path}, model: {upload_agent.model}"
    )
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
        output = result.output
        debug(f"Chunk {index}/{total} validation result: {output}")
        return {"valid": output.valid, "feedback": output.feedback, "index": index}
    except Exception as e:
        debug(f"Retrying chunk {index} due to error: {e}")
        raise self.retry(exc=e)


@celery_app.task(bind=True, name="tasks.upload.validation.summary",
                 autoretry_for=(Exception,),
                 max_retries=3, default_retry_delay=5, rate_limit="1/s")
def summarize_results(self, results: list, document_uuid: str) -> dict:
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
    try:
        summary = loop.run_until_complete(
            upload_agent.run(f"""Act as a compliance officer. Given the following validation feedback, write an active, clear summary describing why the document failed validation and what must be done to fix it. Be concise and direct. Avoid repetition.

    Validation feedback:
    {combined}
    """)
        )
    except Exception as e:
        debug(f"Error summarizing results: {e}")
        self.retry(exc=e)

    summary = summary.output.model_dump()
    debug(summary)

    # Persist to DB
    doc = SmartDocument.objects(uuid=document_uuid).first()
    doc.valid = all_valid
    doc.validation_feedback = summary.get("feedback", "")
    doc.validating = False
    doc.task_status = "complete"
    doc.save()
    debug(f"Document {document_uuid} validation updated: valid={all_valid}")
    return summary


@celery_app.task(bind=True, name="tasks.upload.validation",
                 autoretry_for=(Exception,),
                 max_retries=3, default_retry_delay=5, rate_limit="1/s")
def perform_document_validation(
    self,
    document_text: str,
    document_uuid: str,
    document_path: str,
    chunk_size: int = 8000,
    chunk_overlap: int = 200,
):
    """
    Entry point: splits document, launches chunk validations, and the summarizer via a chord.
    """

    document = SmartDocument.objects(uuid=document_uuid).first()
    if document is not None:
        document.task_status = "security"
        document.validating = True
        document.save()

    start = time.perf_counter()
    # Extract text if needed
    text = document_text
    if text is None:
        text = extract_text_from_doc(document_path)
    compliance = settings.upload_compliance

    debug(text[:100])

    # Split into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    chunks = text_splitter.split_text(text)
    total = len(chunks)
    debug(f"Launching {total} chunk validation tasks")

    # Build list of validate_chunk subtasks
    header = [
        validate_chunk.s(document_path, compliance, chunk_text, idx + 1, total)
        for idx, chunk_text in enumerate(chunks)
    ]

    # Use a chord to run summary after all chunks finish
    callback = summarize_results.s(document_uuid)
    chord(header)(callback)  # Executes validate_chunk tasks, then summarize_results

    elapsed = time.perf_counter() - start
    debug(f"perform_document_validation[{document_uuid}] took {elapsed:.2f}s")

    return text
