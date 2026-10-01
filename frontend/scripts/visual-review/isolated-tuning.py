"""Real configuration persistence using explicitly synthetic candidate scores."""
import datetime as dt
import json
from pathlib import Path
import uuid
import httpx
from bson import ObjectId
from pymongo import MongoClient
run=Path('/private/tmp/vandalizer-ra8-backend');runtime=json.loads((run/'runtime.json').read_text())
mongo=MongoClient('mongodb://127.0.0.1:27028/');db=mongo.vandalizer_ra8_20261001
checks=[];completed=False;clients=[]
def call(c,method,path,data=None,status=200):
    csrf=c.cookies.get('csrf_token');r=c.request(method,'/api'+path,json=data,headers={'X-CSRF-Token':csrf} if csrf else {})
    assert r.status_code==status,f'{path}: expected {status}, got {r.status_code}'
    return r.json()
try:
    for role in ['owner','outsider']:
        c=httpx.Client(base_url='http://127.0.0.1:8001',timeout=20);clients.append(c)
        call(c,'POST','/auth/login',{'user_id':f'ra8-{role}@example.test','password':runtime['password']})
    owner,outsider=clients;wid=ObjectId();now=dt.datetime.now(dt.timezone.utc)
    db.workflow.insert_one({'_id':wid,'name':'QA synthetic tuning candidate','user_id':'ra8-owner@example.test','steps':[],'created_at':now,'updated_at':now,'config_override':None})
    def candidate(status='completed',model='qa-candidate-a'):
        uid='qa-tuning-'+uuid.uuid4().hex
        db.workflow_optimization_runs.insert_one({'uuid':uid,'workflow_id':str(wid),'user_id':'ra8-owner@example.test','status':status,'started_at':now,'completed_at':now if status=='completed' else None,'baseline_default_score':.6,'optimized_score':.8,'best_config':{'step_overrides':{'Review evidence':{'model':model}}},'overfitting_warning':True,'previous_override':None})
        return uid
    first=candidate();queued=candidate('queued')
    apply=lambda uid:f'/workflows/{wid}/optimize/{uid}/apply'
    revert=lambda uid:f'/workflows/{wid}/optimize/{uid}/revert'
    call(outsider,'POST',apply(first),{},status=404);checks.append('unrelated account cannot apply candidate')
    call(owner,'POST',apply(queued),{},status=400);checks.append('unfinished candidate cannot apply')
    call(owner,'POST',apply(first),{});original=db.workflow.find_one({'_id':wid})['config_override']
    assert original['from_run_uuid']==first
    call(owner,'POST',apply(first),{})
    assert db.workflow_optimization_runs.find_one({'uuid':first})['previous_override'] is None,'Repeated apply must preserve the true pre-apply config'
    checks.append('apply and repeat preserve one live config and its original revert snapshot')
    call(owner,'POST',revert(first));assert db.workflow.find_one({'_id':wid})['config_override'] is None
    checks.append('revert restores the exact pre-apply configuration')
    call(owner,'POST',f'/optimizer/inbox/workflow/{first}/dismiss');assert db.workflow_optimization_runs.find_one({'uuid':first})['dismissed_at']
    call(owner,'POST',f'/optimizer/inbox/workflow/{first}/restore');assert db.workflow_optimization_runs.find_one({'uuid':first})['dismissed_at'] is None
    checks.append('dismiss and restore preserve the candidate history')
    call(owner,'POST',apply(first),{});second=candidate(model='qa-candidate-b');call(owner,'POST',apply(second),{})
    current=db.workflow.find_one({'_id':wid})['config_override']
    call(owner,'POST',revert(first),status=409);assert db.workflow.find_one({'_id':wid})['config_override']==current
    checks.append('stale revert cannot overwrite a newer applied candidate')
    call(owner,'POST',revert(second));assert db.workflow.find_one({'_id':wid})['config_override']==original
    call(owner,'POST',revert(first));assert db.workflow.find_one({'_id':wid})['config_override'] is None
    checks.append('successive reversions restore each actual prior configuration')
    completed=True
finally:
    for c in clients:c.close()
    mongo.close();out=Path('artifacts/visual-review/2026-10-01-ra8-isolated-tuning');out.mkdir(parents=True,exist_ok=True)
    (out/'api-evidence.json').write_text(json.dumps({'completed':completed,'mode':'Real local APIs and Mongo config/history writes; seeded synthetic scores and model names, no optimization or model execution','passed_checks':checks},indent=2))
