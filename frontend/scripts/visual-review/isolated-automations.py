"""Real local automation API and deterministic task bodies; no broker consumer or LLM."""
import datetime as dt
import base64
import json
from pathlib import Path
import runpy
import sys
import uuid
from bson import ObjectId
from pymongo import MongoClient

repo = Path(__file__).resolve().parents[3]
run = Path('/private/tmp/vandalizer-ra8-backend')
action = sys.argv[1]
checks = []
completed = False
if action != 'setup':
    runpy.run_path(str(repo/'frontend/scripts/visual-review/isolated-backend.py'), run_name='qa_worker_bootstrap')
mongo = MongoClient('mongodb://127.0.0.1:27028/')
db = mongo.vandalizer_ra8_20261001
state_path = run/'automation-state.json'
try:
    if action == 'setup':
        import httpx
        runtime = json.loads((run/'runtime.json').read_text())
        collaboration = json.loads((run/'collaboration-state.json').read_text())
        doc = db.smart_document.find_one({'uuid': collaboration['shared_document_uuid']})
        wid, step, task = [ObjectId() for _ in range(3)]
        now = dt.datetime.now(dt.timezone.utc)
        db.workflow_step_task.insert_one({'_id': task, 'name': 'DataExport', 'data': {'format': 'json', 'filename': 'automation-evidence'}})
        db.workflow_step.insert_one({'_id': step, 'name': 'Export source evidence', 'tasks': [task], 'data': {}, 'is_output': True})
        db.workflow.insert_one({'_id': wid, 'name': 'QA automation evidence', 'user_id': 'ra8-owner@example.test', 'steps': [step], 'created_at': now, 'updated_at': now, 'num_executions': 0, 'input_config': {'folder_watch': {'delay_seconds': 0}}, 'resource_config': {'throttling': {'min_delay_between_runs': 0}}})
        with httpx.Client(base_url='http://127.0.0.1:8001/api', timeout=20) as api:
            def call(method, path, data=None, status=200):
                r = api.request(method, path, json=data, headers={'X-CSRF-Token': api.cookies.get('csrf_token', '')})
                assert r.status_code == status, (path, r.status_code, r.text[:180])
                return r.json()
            call('POST', '/auth/login', {'user_id': 'ra8-owner@example.test', 'password': runtime['password']})
            output = {'storage': {'enabled': True, 'destination_folder': doc['folder'], 'format': 'json', 'file_naming': 'qa_{run_id}', 'skip_semantic_ingestion': True}}
            def create(kind, config):
                return call('POST', '/automations', {'name': 'QA '+kind, 'trigger_type': kind, 'trigger_config': config, 'action_type': 'workflow', 'action_id': str(wid), 'output_config': output})
            manual = create('api', {})
            call('POST', f'/automations/{manual["id"]}/run-now', {}, status=400)
            checks.append('manual run refuses missing source documents')
            request = {'document_uuids': [doc['uuid']], 'request_id': str(uuid.uuid4())}
            first = call('POST', f'/automations/{manual["id"]}/run-now', request)
            repeated = call('POST', f'/automations/{manual["id"]}/run-now', request)
            assert first['trigger_event_id'] == repeated['trigger_event_id'] and first['status'] == 'queued'
            event = db.workflow_trigger_event.find_one({'uuid': first['trigger_event_id']}) or db.workflow_trigger_event.find_one({'_id': ObjectId(first['trigger_event_id'])})
            assert event['status'] == 'queued' and not event.get('workflow_result')
            checks.append('same manual request reconnects to one queued event; absent worker is not completed')
            schedule = create('schedule', {'frequency': 'daily', 'time': '09:00', 'timezone': 'America/Los_Angeles', 'document_uuids': [doc['uuid']]})
            from zoneinfo import ZoneInfo
            assert dt.datetime.fromisoformat(schedule['next_run_at']).astimezone(ZoneInfo('America/Los_Angeles')).hour == 9
            checks.append('API next-run time preserves 09:00 in the configured local timezone')
            # Make exactly one schedule slot due without a long wall-clock wait.
            db.automation.update_one({'_id': ObjectId(schedule['id'])}, {'$set': {'enabled': True, 'trigger_config.cron_expression': '* * * * *', 'created_at': now-dt.timedelta(minutes=2), 'schedule_armed_at': now-dt.timedelta(minutes=2), 'last_scheduled_run_at': None}})
            folder = create('folder_watch', {'folder_id': doc['folder'], 'file_types': ['pdf']})
            call('PATCH', f'/automations/{folder["id"]}', {'enabled': True})
            state_path.write_text(json.dumps({'workflow': str(wid), 'manual_event': str(event['_id']), 'schedule': schedule['id'], 'folder': folder['id'], 'document': doc['uuid']}))
    elif action == 'run':
        from app.tasks.passive_tasks import execute_workflow_passive, process_outputs, process_pending_triggers, process_scheduled_automations
        from app.tasks.document_tasks import _check_folder_watch_automations
        state = json.loads(state_path.read_text())
        result = execute_workflow_passive.apply(args=[state['manual_event']], throw=True).get()
        assert result['status'] == 'completed', result
        rid = result['workflow_result_id']
        delivered = process_outputs.apply(args=[rid], throw=True).get()
        assert delivered['storage']['status'] == 'completed', delivered
        stored_path = Path(delivered['storage']['path'])
        assert stored_path.is_file()
        def rendered_text(value):
            if isinstance(value, dict):
                if value.get('type') == 'file_download':
                    return base64.b64decode(value['data_b64']).decode()
                return ' '.join(rendered_text(v) for v in value.values())
            if isinstance(value, list):
                return ' '.join(rendered_text(v) for v in value)
            return str(value)
        assert json.loads(rendered_text(json.loads(stored_path.read_text()))) == [state['document']]
        checks.append('real manual task exports the exact selected source UUID and writes its JSON delivery inside QA storage')
        before = db.workflow_result.count_documents({'trigger_event_id': state['manual_event']})
        execute_workflow_passive.apply(args=[state['manual_event']], throw=True).get()
        assert db.workflow_result.count_documents({'trigger_event_id': state['manual_event']}) == before, 'Repeated task delivery created another run'
        checks.append('repeated completed-event task delivery creates no additional workflow run')
        process_scheduled_automations.apply(throw=True).get()
        schedule_query = {'trigger_context.automation_id': state['schedule']}
        assert db.workflow_trigger_event.count_documents(schedule_query) == 1
        process_scheduled_automations.apply(throw=True).get()
        assert db.workflow_trigger_event.count_documents(schedule_query) == 1
        checks.append('two schedule sweeps claim only one due slot')
        _check_folder_watch_automations(db, state['document'])
        folder_query = {'trigger_context.automation_id': state['folder']}
        assert db.workflow_trigger_event.count_documents(folder_query) == 1
        _check_folder_watch_automations(db, state['document'])
        assert db.workflow_trigger_event.count_documents(folder_query) == 1
        checks.append('repeated ingestion folder-watch hooks create one event for the matching PDF')
        process_pending_triggers.apply(throw=True).get()
        for query in [schedule_query, folder_query]:
            event = db.workflow_trigger_event.find_one(query)
            assert event['status'] == 'queued', event['status']
            result = execute_workflow_passive.apply(args=[str(event['_id'])], throw=True).get()
            assert result['status'] == 'completed', result
            assert process_outputs.apply(args=[result['workflow_result_id']], throw=True).get()['storage']['status'] == 'completed'
        checks.append('schedule and folder events pass readiness evaluation, run and deliver actual stored results')
    else:
        raise ValueError('Use setup or run')
    completed = True
finally:
    mongo.close()
    out = repo/'artifacts/visual-review/2026-10-01-ra8-isolated-automations'
    out.mkdir(parents=True, exist_ok=True)
    (out/(action+'.json')).write_text(json.dumps({'completed': completed, 'mode': 'Real isolated APIs, Mongo/Redis and task bodies; local JSON delivery; schedule timestamp made due; no broker consumer, LLM or external delivery', 'passed_checks': checks}, indent=2))
print('Passed', len(checks), 'automation checks')
