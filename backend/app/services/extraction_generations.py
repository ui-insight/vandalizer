"""Database predicates for one dispatched generation of document processing."""


def extraction_generation_filter(document_uuid: str, extraction_revision: int = 0) -> dict:
    """Legacy queued messages belong to generation zero, never the latest retry.

    Only the restart/reaper CAS advances the counter. All background writes
    carry the dispatched value; reading today's counter would adopt old work.
    """
    if type(extraction_revision) is not int or extraction_revision < 0:
        raise ValueError('Invalid extraction revision')
    query = {'uuid': document_uuid, 'soft_deleted': {'$ne': True}}
    if extraction_revision == 0:
        query['$or'] = [
            {'_extraction_restart_revision': {'$exists': False}},
            {'_extraction_restart_revision': 0},
        ]
    else:
        query['_extraction_restart_revision'] = extraction_revision
    return query
