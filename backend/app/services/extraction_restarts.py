"""Atomically claim a document restart before dispatching any background work."""
from app.models.document import SmartDocument
from app.services.extraction_staleness import extraction_is_stale


class ExtractionRestartConflict(RuntimeError):
    def __init__(self):
        super().__init__('Document changed or another retry started. Refresh its status before retrying.')


# Match the identity, permission context and evidence used to decide this retry.
# Other fields are neither overwritten nor required to stop changing.
_FIELDS = (
    'uuid', 'user_id', 'team_id', 'folder', 'title', 'path', 'downloadpath',
    'extension', 'soft_deleted', 'task_status', 'processing', 'updated_at',
    'raw_text', 'token_count', 'text_markers', 'error_message',
    'extraction_nonletter_ratio', 'text_layer_rejected', 'ingestion_warnings',
    '_extraction_restart_revision',
)


async def claim_extraction_restart(doc: SmartDocument, changes: dict) -> None:
    from app.services.document_service import extraction_in_flight

    collection = SmartDocument.get_motor_collection()
    raw = await collection.find_one({'_id': doc.id})
    if raw is None or type(raw.get('_extraction_restart_revision', 0)) is not int or raw.get('_extraction_restart_revision', 0) < 0:
        raise ExtractionRestartConflict()
    current = SmartDocument.model_validate(raw)
    for field in _FIELDS:
        # Very old records can lack their timestamp. A model's generated
        # fallback is not a stored revision; the CAS below matches its absence.
        if field == 'updated_at' and field not in raw:
            continue
        if getattr(current, field) != getattr(doc, field):
            raise ExtractionRestartConflict()
    if current.soft_deleted or (extraction_in_flight(current) and not extraction_is_stale(current.updated_at, current.created_at)):
        raise ExtractionRestartConflict()
    expected = {'_id': doc.id, **{
        field: {'$eq': raw[field]} if field in raw else {'$exists': False}
        for field in _FIELDS
    }}
    values = {**changes, '_extraction_restart_revision': current._extraction_restart_revision + 1}
    result = await collection.update_one(expected, {'$set': values})
    if result.matched_count != 1:
        raise ExtractionRestartConflict()
    for field, value in values.items():
        setattr(doc, field, value)
