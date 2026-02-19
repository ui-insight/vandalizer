from celery import chain, signature

from app.celery_app import celery


def dispatch_upload_tasks(document_uuid: str, extension: str, document_path: str) -> str:
    """
    Dispatch extraction + update to existing Celery workers, mirroring the
    Flask upload route's task chaining:
      extraction → update_document_fields (on success)
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

    return result.id
