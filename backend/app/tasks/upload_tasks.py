
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

    workflow = extraction | update
    result = workflow.apply_async(link_error=cleanup)

    # Dispatch semantic ingestion after extraction completes.
    # This uses send_task so it works whether tasks are local or in Flask workers.
    if user_id:
        celery.send_task(
            "tasks.document.semantic_ingestion",
            kwargs={
                "raw_text": "",  # task will read from DB if empty
                "document_uuid": document_uuid,
                "user_id": user_id,
            },
            queue="documents",
            countdown=10,  # slight delay to let extraction finish
        )

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
