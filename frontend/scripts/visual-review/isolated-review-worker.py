"""Run actual Celery task bodies locally with deterministic, model-free steps.
No broker consumer is started; existing QA queues are left untouched.
"""
import base64
import datetime as dt
import json
from pathlib import Path
import runpy
import sys
from bson import ObjectId
from pymongo import MongoClient
repo=Path(__file__).resolve().parents[3]
action=sys.argv[1]
if action=='approve':
    import httpx
    run=Path('/private/tmp/vandalizer-ra8-backend')
    state=json.loads((run/'review-worker-state.json').read_text())
    runtime=json.loads((run/'runtime.json').read_text())
    with httpx.Client(base_url='http://127.0.0.1:8001/api',timeout=20) as api:
        response=api.post('/auth/login',json={'user_id':'ra8-member@example.test','password':runtime['password']})
        assert response.status_code==200, response.status_code
        response=api.post('/reviews/'+state['approval_uuid']+'/approve',json={'comments':'Controlled review of source and export','edited_artifact':state['edited_artifact']},headers={'X-CSRF-Token':api.cookies['csrf_token']})
        assert response.status_code==200, response.status_code
    out=repo/'artifacts/visual-review/2026-10-01-ra8-isolated-review-worker';out.mkdir(parents=True,exist_ok=True)
    (out/'approve.json').write_text(json.dumps({'mode':'Real local API on the review created by actual task execution','passed_checks':['assigned controlled reviewer records an edited approval']}))
    print('Passed real reviewer decision')
    raise SystemExit
runpy.run_path(str(repo/'frontend/scripts/visual-review/isolated-backend.py'),run_name='qa_worker_bootstrap')
from app.tasks.workflow_tasks import execute_workflow_task, resume_workflow_after_approval
run=Path('/private/tmp/vandalizer-ra8-backend')
client=MongoClient('mongodb://127.0.0.1:27028/')
db=client.vandalizer_ra8_20261001
state_path=run/'review-worker-state.json'
checks=[]
try:
    if action=='start':
        collaboration=json.loads((run/'collaboration-state.json').read_text())
        wid,rid,gate,export,gt,et=[ObjectId() for _ in range(6)]
        now=dt.datetime.now(dt.timezone.utc)
        db.workflow_step_task.insert_many([
            {'_id':gt,'name':'Approval','data':{'review_instructions':'Check the source before exporting the reviewed result.','assignee_role':'specific_users','assigned_to_user_ids':['ra8-member@example.test']}},
            {'_id':et,'name':'DataExport','data':{'format':'json','filename':'reviewed-evidence'}},
        ])
        db.workflow_step.insert_many([{'_id':gate,'name':'Review evidence','tasks':[gt],'data':{}},{'_id':export,'name':'Export reviewed evidence','tasks':[et],'data':{},'is_output':True}])
        db.workflow.insert_one({'_id':wid,'name':'QA reviewed evidence export','user_id':'ra8-owner@example.test','steps':[gate,export],'created_at':now,'updated_at':now,'num_executions':0})
        from app.tasks.document_tasks import perform_extraction_and_update
        text=perform_extraction_and_update.apply(kwargs={'document_uuid':collaboration['shared_document_uuid'],'extension':'pdf'},throw=True).get()
        assert 'Total Senior Personnel' in text
        stored=db.smart_document.find_one({'uuid':collaboration['shared_document_uuid']})
        assert stored['raw_text']==text and stored['num_pages']==2 and not stored['processing']
        checks.append('actual PDF extraction task reads two pages and persists the expected source text; embeddings/classification not run')
        trigger={'doc_uuids':[collaboration['shared_document_uuid']]}
        db.workflow_result.insert_one({'_id':rid,'workflow':wid,'session_id':str(rid),'status':'running','input_context':trigger,'start_time':now})
        outcome=execute_workflow_task.apply(kwargs={'workflow_result_id':str(rid),'workflow_id':str(wid),'trigger_step_data':trigger,'model':''},throw=True).get()
        assert outcome['status']=='pending_approval', outcome
        approval=db.approval_request.find_one({'workflow_result_id':rid})
        assert approval['assigned_to_user_ids']==['ra8-member@example.test']
        state={'workflow_id':str(wid),'result_id':str(rid),'approval_uuid':approval['uuid'],'edited_artifact':{'budget_status':'Manual source check recorded','deadline_status':'Sponsor confirmation required'}}
        state_path.write_text(json.dumps(state))
        checks.append('actual initial task runs Document and Approval, persists the review and pauses before export')
    elif action=='resume':
        state=json.loads(state_path.read_text());rid=ObjectId(state['result_id']);wid=ObjectId(state['workflow_id'])
        outcome=resume_workflow_after_approval.apply(kwargs={'approval_uuid':state['approval_uuid']},throw=True).get()
        assert outcome['status']=='completed', outcome
        result=db.workflow_result.find_one({'_id':rid})
        assert result['status']=='completed' and result['finalized_at']
        final=result['final_output']['output']
        # MultiTaskNode wraps its task output; locate the generated download.
        def downloads(value):
            if isinstance(value,dict):
                if value.get('type')=='file_download':yield value
                for v in value.values():yield from downloads(v)
            elif isinstance(value,list):
                for v in value:yield from downloads(v)
        outputs=list(downloads(final));assert outputs, 'No exported result'
        assert json.loads(base64.b64decode(outputs[0]['data_b64']))==state['edited_artifact']
        assert db.workflow.find_one({'_id':wid})['num_executions']==1
        checks.append('actual resume task exports the exact edited artifact and completes the persisted run')
        resume_workflow_after_approval.apply(kwargs={'approval_uuid':state['approval_uuid']},throw=True).get()
        assert db.workflow.find_one({'_id':wid})['num_executions']==1
        assert db.workflow_result.find_one({'_id':rid})['final_output']==result['final_output']
        checks.append('repeated task delivery preserves the completed output and one execution count')
    else:raise ValueError('Use start or resume')
finally:
    client.close()
    out=repo/'artifacts/visual-review/2026-10-01-ra8-isolated-review-worker';out.mkdir(parents=True,exist_ok=True)
    (out/(action+'.json')).write_text(json.dumps({'mode':'Actual Celery task bodies with Mongo/Redis and deterministic Approval/DataExport steps; no broker consumer or LLM inference','passed_checks':checks},indent=2))
print('Passed',len(checks),'controlled worker checks')
