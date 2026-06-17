
from app.celery_app import celery


def dispatch_upload_tasks(
    document_uuid: str,
    extension: str,
    document_path: str,
    user_id: str = "",
) -> str:
    """
    Dispatch extraction + update + semantic_ingestion to Celery workers.
      extraction → update_document_fields → semantic_ingestion (on success)
      cleanup_document (on error)
    Validation runs independently in the background.
    """
    extraction = celery.signature(
        "tasks.document.extraction",
        kwargs={"document_uuid": document_uuid, "extension": extension},
        queue="documents",
    )
    update = celery.signature(
        "tasks.document.update",
        kwargs={"document_uuid": document_uuid},
        queue="documents",
        immutable=True,
    )
    cleanup = celery.signature(
        "tasks.document.cleanup",
        kwargs={"document_uuid": document_uuid},
        queue="documents",
        immutable=True,
    )

    # Semantic ingestion MUST run only after extraction has written raw_text.
    # Previously it was dispatched fire-and-forget with countdown=10, racing the
    # extraction task: it routinely read an empty document, produced zero chunks,
    # and "succeeded" — leaving the doc permanently unindexed (0 chunks isn't an
    # error, so it never retries). Chain it onto extraction→update so ordering is
    # guaranteed; the task reads raw_text from the DB, now populated by extraction.
    if user_id:
        ingestion = celery.signature(
            "tasks.document.semantic_ingestion",
            kwargs={
                "raw_text": "",  # task reads raw_text from DB
                "document_uuid": document_uuid,
                "user_id": user_id,
            },
            queue="documents",
            immutable=True,
        )
        workflow = extraction | update | ingestion
    else:
        workflow = extraction | update
    result = workflow.apply_async(link_error=cleanup)

    # Run classification independently in the background
    celery.send_task(
        "tasks.document.classify",
        kwargs={"document_uuid": document_uuid},
        queue="documents",
        countdown=15,  # delay to let text extraction finish
    )

    # Run validation independently in the background
    celery.send_task(
        "tasks.upload.validation",
        kwargs={
            "document_uuid": document_uuid,
            "document_path": document_path,
            "background": True,
        },
        queue="uploads",
    )

    return str(result.id)
