#!/usr/bin/env python3

from app.celery_worker import celery_app
from app.models import SmartDocument
from devtools import debug
from app.utilities.agents import validate_document
import time
from celery.result import AsyncResult

import asyncio


@celery_app.task
def perform_document_validation(document_uuid, doc_path, doc_text, task_id):
    # wait until the processing is completed
    if task_id:
        task_result = AsyncResult(task_id)
        while not task_result.ready():
            debug("Waiting for the document processing to complete...")
            time.sleep(2)

    debug(f"perform_document_validation called with parameters:")
    debug(f"document_uuid: {document_uuid}")
    debug(f"doc_path: {doc_path}")
    debug(f"doc_text length: {len(doc_text) if doc_text else 'None or empty'}")
    debug(f"task_id: {task_id}")

    loop = asyncio.new_event_loop()
    result = None
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(validate_document(doc_path, doc_text))
    finally:
        loop.close()

    # Run the async function in the event loop
    # result = loop.run_until_complete(validate_document(doc_path, doc_text))
    # result = asyncio.run(validate_document(doc_path, doc_text))
    if result is None:
        document = SmartDocument.objects(uuid=document_uuid).first()
        document.valid = False
        document.validation_feedback = "Error: failure during document validation"
        document.save()
    elif result.valid:
        document = SmartDocument.objects(uuid=document_uuid).first()
        document.valid = True
        document.validation_feedback = result.feedback
        document.save()
    else:
        debug("Document validation failed:", result.feedback)
        document = SmartDocument.objects(uuid=document_uuid).first()
        document.valid = False
        document.validation_feedback = result.feedback
        document.save()
