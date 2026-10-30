"""First-class private/team design templates. No publication or source access grants."""
import functools
import re
from datetime import datetime, timezone

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.dependencies import get_current_user
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.page_template import SaveTemplate, TemplateAccess, TemplateSource
from app.services import access_control, artifacts, page_templates
from app.services.page_links import prepare_page_links
from app.tasks import get_sync_db

router = APIRouter()


async def run(fn, *args):
    return await anyio.to_thread.run_sync(functools.partial(fn, get_sync_db(), *args))


async def authorized(uuid, user, manage=False):
    template = await run(page_templates.get, uuid)
    if template['user_id'] == user.user_id:
        return template
    if not manage and access_control.can_view_team(template.get('team_id'), await access_control.get_team_access_context(user)):
        return template
    raise HTTPException(404, 'Template not found')


async def browse(user, search='', page=1):
    access = await access_control.get_team_access_context(user)
    query = {'deleted_at': None, '$or': [{'user_id': user.user_id}, {'team_id': {'$in': list(access.team_uuids | access.team_object_ids)}}]}
    if search.strip():
        query['name'] = {'$regex': re.escape(search.strip()), '$options': 'i'}
    def load(db):
        items = list(db.page_templates.find(query).sort([('created_at', -1), ('uuid', 1)]).skip((page - 1) * 20).limit(20))
        return {'items': [page_templates.metadata(item, user.user_id) for item in items], 'total': db.page_templates.count_documents(query), 'page': page, 'page_size': 20}
    return await run(load)


@router.get('')
async def list_templates(search: str = Query(default='', max_length=200), page: int = Query(default=1, ge=1, le=100000), user: User = Depends(get_current_user)):
    return await browse(user, search, page)


@router.post('/prepare')
@limiter.limit('20/minute')
async def prepare_template(request: Request, body: TemplateSource, user: User = Depends(get_current_user)):
    if body.artifact_uuid:
        from app.routers.artifacts import authorized as authorize_page
        page = await authorize_page(body.artifact_uuid, user)
        html = artifacts.revision(page, body.revision)['html']
    else:
        preview = await run(lambda db: db.chat_page_previews.find_one({'_id': body.preview_id, 'user_id': user.user_id}))
        if not preview:
            raise HTTPException(404, 'Page preview not found')
        html = preview['prepared_html']
    return await run(page_templates.prepare, user.user_id, html)


@router.post('')
@limiter.limit('20/minute')
async def save_template(request: Request, body: SaveTemplate, user: User = Depends(get_current_user)):
    template = await run(page_templates.save, user.user_id, user.name or 'Workspace member', body)
    return page_templates.metadata(template, user.user_id)


@router.get('/{uuid}', response_model=None)
async def get_template(uuid: str, user: User = Depends(get_current_user)) -> dict[str, object]:
    template = await authorized(uuid, user)
    return {**page_templates.metadata(template, user.user_id), 'fields': template['fields'], 'guidance': template.get('guidance', '')}


@router.get('/{uuid}/content')
async def template_content(uuid: str, user: User = Depends(get_current_user)):
    template = await authorized(uuid, user)
    html, _ = page_templates.render(template, {})
    html, csp = prepare_page_links(html, artifacts.CONTENT_CSP)
    return HTMLResponse(html, headers={'Content-Security-Policy': csp, 'Cache-Control': 'no-store',
        'X-Frame-Options': 'SAMEORIGIN', 'Referrer-Policy': 'no-referrer', 'X-Robots-Tag': 'noindex, nofollow'})


@router.put('/{uuid}/team', response_model=None)
async def share_template(uuid: str, body: TemplateAccess, user: User = Depends(get_current_user)) -> dict[str, object]:
    await authorized(uuid, user, manage=True)
    if body.team_id and not access_control.can_view_team(body.team_id, await access_control.get_team_access_context(user)):
        raise HTTPException(404, 'Team not found')
    await run(lambda db: db.page_templates.update_one({'uuid': uuid, 'user_id': user.user_id, 'deleted_at': None}, {'$set': {'team_id': body.team_id}}))
    return {'ok': True}


@router.delete('/{uuid}', response_model=None)
async def delete_template(uuid: str, user: User = Depends(get_current_user)) -> dict[str, object]:
    await authorized(uuid, user, manage=True)
    await run(lambda db: db.page_templates.update_one({'uuid': uuid, 'user_id': user.user_id}, {'$set': {'deleted_at': datetime.now(timezone.utc), 'team_id': None, 'html': '', 'fields': [], 'tables': []}}))
    return {'ok': True}
