"""Actual upload/storage and project-role enforcement; ingestion worker stays off."""
import base64
import datetime as dt
import json
from pathlib import Path
import httpx
from pymongo import MongoClient
run=Path('/private/tmp/vandalizer-ra8-backend')
runtime=json.loads((run/'runtime.json').read_text())
state=json.loads((run/'collaboration-state.json').read_text())
db_client=MongoClient('mongodb://127.0.0.1:27028/')
db=db_client.vandalizer_ra8_20261001
checks=[];clients={};completed=False

def call(c,method,path,data=None,codes=(200,),label=None):
    csrf=c.cookies.get('csrf_token')
    r=c.request(method,'/api'+path,json=data,headers={'X-CSRF-Token':csrf} if csrf else {})
    assert r.status_code in codes,f'{label or path}: {r.status_code} {r.text[:180]}'
    if label:checks.append(label);print('Passed:',label,flush=True)
    return r
try:
    for role in ['owner','member','viewer','outsider']:
        c=httpx.Client(base_url='http://127.0.0.1:8001',timeout=30);clients[role]=c
        call(c,'POST','/auth/login',{'user_id':f'ra8-{role}@example.test','password':runtime['password']})
    owner,editor,viewer,outsider=[clients[k] for k in ['owner','member','viewer','outsider']]
    pid=state['project']['uuid'];root=state['project']['root_folder_uuid']
    # Restore the viewer when this script follows the API removal checks directly.
    if viewer.get('/api/projects/'+pid).status_code==404:
        link=call(owner,'POST',f'/projects/{pid}/invite-link',{'role':'viewer','max_uses':1}).json()
        call(viewer,'POST','/projects/join/accept/'+link['token'])
    pdf=Path('backend/certification-data/documents/budget-justification.pdf').read_bytes()
    body={'fileName':'QA shared budget.pdf','extension':'pdf','folder':root,'contentAsBase64String':base64.b64encode(pdf).decode()}
    uploaded=call(editor,'POST','/files/upload',body,label='project editor uploads an actual PDF into the project').json()
    doc=uploaded['uuid'];state['shared_document_uuid']=doc
    assert db.smart_document.find_one({'uuid':doc})['processing'], 'Without a worker, upload must remain processing'
    checks.append('accepted upload remains processing while the worker is unavailable')
    for client,label in [(owner,'owner'),(editor,'editor'),(viewer,'viewer')]:
        result=call(client,'GET','/documents/list?folder='+root,label=f'{label} lists project files from another uploader').json()
        assert doc in [d['uuid'] for d in result['documents']]
        response=call(client,'GET','/files/download?docid='+doc,label=f'{label} downloads the original project PDF')
        assert response.content==pdf
        call(client,'GET','/folders/breadcrumbs/'+root,label=f'{label} reads the project folder path')
    call(viewer,'POST','/files/upload',body,codes=(400,),label='viewer cannot upload into the project')
    call(viewer,'POST','/folders/create',{'name':'Unauthorized folder','parent_id':root},codes=(400,),label='viewer cannot create a project subfolder')
    call(viewer,'PATCH','/files/rename',{'uuid':doc,'newName':'Unauthorized rename'},codes=(404,),label='viewer cannot rename a project file')
    call(editor,'PATCH','/files/rename',{'uuid':doc,'newName':'QA reviewed budget.pdf'},label='editor can rename the shared file')
    call(outsider,'GET','/files/download?docid='+doc,codes=(404,),label='nonmember cannot download a project file')
    call(owner,'DELETE',f'/projects/{pid}/members/ra8-member@example.test')
    call(editor,'GET','/files/download?docid='+doc,codes=(404,),label='removed uploader loses project file access')
    call(editor,'PATCH','/files/rename',{'uuid':doc,'newName':'Removed uploader rename'},codes=(404,),label='removed uploader cannot edit their former project file')
    call(owner,'GET','/files/download?docid='+doc,label='project owner retains the removed contributor’s file')
    link=call(owner,'POST',f'/projects/{pid}/invite-link',{'role':'editor','max_uses':1}).json()
    call(editor,'POST','/projects/join/accept/'+link['token'])
    (run/'collaboration-state.json').write_text(json.dumps(state))
    completed=True
finally:
    for c in clients.values():c.close()
    db_client.close()
    out=Path('artifacts/visual-review/2026-10-01-ra8-isolated-project-files');out.mkdir(parents=True,exist_ok=True)
    (out/'api-evidence.json').write_text(json.dumps({'completed':completed,'mode':'Real upload/storage, Mongo persistence and role enforcement; extraction/model workers disabled','passed_checks':checks,'count':len(checks),'timestamp':dt.datetime.now(dt.timezone.utc).isoformat()},indent=2))
