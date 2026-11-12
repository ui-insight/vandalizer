from unittest.mock import MagicMock, patch

from bson import ObjectId

from app.services.passive_triggers import create_folder_watch_trigger


def test_repeated_arrival_reuses_event_but_new_document_folder_or_action_is_distinct():
    events = {}
    db = MagicMock()

    def upsert(query, update, **kwargs):
        return events.setdefault(query['_id'], update['$setOnInsert'].copy())

    db.workflow_trigger_event.find_one_and_update.side_effect = upsert
    workflow = {'_id': ObjectId()}
    document = {'_id': ObjectId(), 'folder': 'inbox'}
    with patch('app.services.passive_triggers.get_sync_db', return_value=db):
        first = create_folder_watch_trigger(workflow, document, automation_id='a')
        first['status'] = 'completed'
        repeated = create_folder_watch_trigger(workflow, document, automation_id='a')
        assert repeated is first and repeated['status'] == 'completed'
        variants = [
            create_folder_watch_trigger(workflow, {**document, '_id': ObjectId()}, automation_id='a'),
            create_folder_watch_trigger(workflow, {**document, 'folder': 'other'}, automation_id='a'),
            create_folder_watch_trigger(workflow, document, automation_id='b'),
            create_folder_watch_trigger({'_id': ObjectId()}, document, automation_id='a'),
        ]
    assert len({first['_id'], *(item['_id'] for item in variants)}) == 5
