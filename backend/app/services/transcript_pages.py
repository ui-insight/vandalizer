"""Stable, owner-scoped snapshots of the visible chat transcript."""
import hashlib
import json

from fastapi import HTTPException

from app.schemas.chat_export import ChatExportRequest
from app.services import artifacts
from app.services.chat_export import render_chat_export


def page_title(messages, conversation_title=None, requested_title=None):
    generic = {'chat transcript', 'new chat', 'new conversation', 'untitled', 'attachments added', 'document attached', 'link attached'}
    candidates = [requested_title, conversation_title]
    candidates.extend(message.content for message in messages if message.role == 'user')
    candidates.extend(message.content for message in messages if message.role == 'assistant')
    for candidate in candidates:
        title = ' '.join((candidate or '').split())
        if title and title.casefold() not in generic:
            return title if len(title) <= 200 else title[:199].rstrip() + '…'
    return 'Saved conversation'


def save(db, user_id, body, conversation_title=None):
    # Validate the same content/size bounds as downloads, before any lookup.
    transcript = ChatExportRequest(format='html', messages=body.messages)
    content = json.dumps([message.model_dump() for message in transcript.messages],
                         sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    # A title/renderer update or a fresh browser request must not create another
    # Page. Different conversations and different visible content stay separate.
    snapshot = hashlib.sha256(json.dumps([body.conversation_uuid or body.request_id, content], ensure_ascii=False).encode()).hexdigest()
    base_request_id = f'chat-transcript:{snapshot}'
    request_id = base_request_id
    while True:
        uuid = hashlib.sha256(f'{user_id}\0{request_id}'.encode()).hexdigest()[:32]
        existing = db.html_artifacts.find_one({'uuid': uuid, 'user_id': user_id})
        if existing is None:
            break
        if existing.get('deleted_at'):
            # An explicit save may replace a deleted snapshot. Never restore
            # its old public links, team access, or deleted content.
            request_id = f'{base_request_id}:after:{existing["uuid"]}'
            continue
        return existing, True
    title = page_title(transcript.messages, conversation_title, body.title)
    html = render_chat_export(transcript, title=title).decode()
    try:
        return artifacts.create(db, user_id, title, html, request_id, {
            'kind': 'chat_export', 'conversation_uuid': body.conversation_uuid,
            'project_uuid': body.project_uuid,
        }), False
    except HTTPException as exc:
        # A concurrent save can win with a different conversation title. The
        # content-scoped identity is the same; return its immutable snapshot.
        if exc.status_code == 409:
            existing = db.html_artifacts.find_one({'uuid': uuid, 'user_id': user_id, 'deleted_at': None})
            if existing:
                return existing, True
        raise
