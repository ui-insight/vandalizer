"""Controlled review decisions against the real isolated backend and queue.
Seeds paused synthetic runs directly; does not claim initial execution or model work.
"""
import asyncio
import datetime as dt
import json
from pathlib import Path
import uuid
import httpx
from bson import ObjectId
from pymongo import MongoClient
import redis
run = Path('/private/tmp/vandalizer-ra8-backend')
runtime = json.loads((run/'runtime.json').read_text())
db_client = MongoClient('mongodb://127.0.0.1:27028/')
db = db_client.vandalizer_ra8_20261001
queue = redis.Redis(host='127.0.0.1', port=6379)
checks = []
completed = False

def seed(status='pending', assigned='ra8-member@example.test', expires=None):
    wid, rid = ObjectId(), ObjectId()
    aid = 'qa-review-'+uuid.uuid4().hex
    now = dt.datetime.now(dt.timezone.utc)
    db.workflow.insert_one({'_id':wid,'name':'QA Sponsor review','user_id':'ra8-owner@example.test','steps':[],'created_at':now,'updated_at':now})
    db.workflow_result.insert_one({'_id':rid,'workflow':wid,'session_id':str(rid),'status':'pending_approval','start_time':now})
    db.approval_request.insert_one({'uuid':aid,'workflow_id':wid,'workflow_result_id':rid,'step_index':0,'step_name':'Check budget','workflow_name':'QA Sponsor review','requester_user_id':'ra8-owner@example.test','assigned_to_user_ids':[assigned],'status':status,'artifact_kind':'markdown','data_for_review':{'value':'Budget requires confirmation.'},'review_instructions':'Confirm with the sponsor before approval.','created_at':now,'expires_at':expires})
    return aid, rid

async def main():
    global completed
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8001/api', timeout=20) as client:
        r = await client.post('/auth/login', json={'user_id':'ra8-member@example.test','password':runtime['password']})
        assert r.status_code == 200, 'Local login failed: '+str(r.status_code)
        headers={'X-CSRF-Token':client.cookies['csrf_token']}
        async def decide(aid, action='approve', body=None):
            return await client.post(f'/reviews/{aid}/{action}', json=body or {}, headers=headers)
        aid,rid=seed()
        queued=queue.llen('workflows')
        responses=await asyncio.gather(*(decide(aid, body={'comments':'Checked once','edited_artifact':{'value':'Corrected budget evidence.'}}) for _ in range(2)))
        codes=sorted(r.status_code for r in responses)
        assert codes == [200,400], f'Concurrent decisions should accept once: {codes}'
        assert queue.llen('workflows') == queued+1, 'Accepted decision must queue one resume'
        record=db.approval_request.find_one({'uuid':aid})
        assert record['edited_artifact']['value']=='Corrected budget evidence.'
        assert db.workflow_result.find_one({'_id':rid})['status']=='pending_approval'
        checks.append('simultaneous edited approvals persist once and queue one resume; unavailable worker stays pending')
        aid,rid=seed()
        r=await decide(aid,'reject',{'comments':'Sponsor confirmation is missing'})
        assert r.status_code==200
        assert db.workflow_result.find_one({'_id':rid})['status']=='failed'
        assert (await decide(aid)).status_code==400
        checks.append('rejection fails the paused run and cannot subsequently approve')
        aid,_=seed(assigned='ra8-viewer@example.test')
        assert (await decide(aid)).status_code==403
        checks.append('unassigned account cannot decide')
        db.approval_request.update_one({'uuid':aid},{'$set':{'assigned_to_user_ids':['ra8-member@example.test']}})
        assert (await decide(aid)).status_code==200
        checks.append('reassigned controlled account can decide')
        aid,_=seed(expires=dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=1))
        assert (await decide(aid)).status_code==400, 'Past-deadline pending review must not accept a decision before the periodic sweep'
        checks.append('past-deadline review refuses a stale human decision')
        completed=True
try:
    asyncio.run(main())
finally:
    db_client.close();queue.close()
    out=Path('artifacts/visual-review/2026-10-01-ra8-isolated-reviews');out.mkdir(parents=True,exist_ok=True)
    (out/'api-evidence.json').write_text(json.dumps({'completed':completed,'mode':'Real local API, persisted synthetic paused runs and Redis queue; worker/model resume not yet exercised','passed_checks':checks},indent=2))
