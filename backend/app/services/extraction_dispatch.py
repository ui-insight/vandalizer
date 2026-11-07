"""Record a queue response without restoring the pre-dispatch document."""
from app.models.document import SmartDocument
from app.services.extraction_generations import extraction_generation_filter


async def record_extraction_dispatch(document: SmartDocument, task_id: str) -> bool:
    """Keep a task ID only while its original extraction is still processing.

    A worker can complete, fail or be superseded before apply_async returns.
    Neither its fields nor a terminal task_id may be replaced by that response.
    """
    query = {
        **extraction_generation_filter(document.uuid, document._extraction_restart_revision),
        '_id': document.id, 'processing': True, 'task_id': None,
        'user_id': document.user_id, 'team_id': document.team_id,
    }
    result = await SmartDocument.get_motor_collection().update_one(query, {'$set': {'task_id': task_id}})
    if not result.matched_count:
        return False
    document.task_id = task_id
    return True
