"""Separate public links stay bound to one reviewed version and revoke independently."""
from datetime import datetime

import pytest

from app.services import artifacts
from app.services.access_control import TeamAccessContext
from tests.test_artifacts import db as db, route_env as route_env, make
from tests.test_chat_routes import _auth


def three_versions(db):
    one = make(db, html='<h1>Original budget</h1>')
    two = artifacts.revise(db, one, 'Private notes', '<p>Confidential draft</p>', one['latest_revision'])
    three = artifacts.revise(db, two, 'Revised budget', '<h1>Reviewed revised budget</h1>', two['latest_revision'])
    return three, [r['uuid'] for r in three['revisions']]


def link_for(doc, revision):
    return next(p['token'] for p in doc['publications'] if p['revision'] == revision)


@pytest.mark.asyncio
async def test_original_and_revised_budgets_remain_public_side_by_side(client, db, route_env):
    doc, (one, private, three) = three_versions(db)
    cookies, headers = _auth()
    endpoint = f'/api/pages/{doc["uuid"]}/publication'
    main = (await client.put(endpoint, json={'revision': one}, cookies=cookies, headers=headers)).json()
    tokens = []
    for selected in (one, three):
        response = await client.put(endpoint, json={'revision': selected, 'separate_link': True}, cookies=cookies, headers=headers)
        assert response.status_code == 200
        saved = response.json()
        assert saved['published_revision'] == one
        assert saved['public_token'] == main['public_token']
        tokens.append(link_for(saved, selected))
    assert len(set([*tokens, main['public_token']])) == 3
    retry = await client.put(endpoint, json={'revision': one, 'separate_link': True}, cookies=cookies, headers=headers)
    assert len(retry.json()['publications']) == 2
    assert link_for(retry.json(), one) == tokens[0]

    # Updating the legacy/main link must leave both separate links pinned.
    await client.put(endpoint, json={'revision': three}, cookies=cookies, headers=headers)
    artifacts.revise(db, artifacts.get(db, doc['uuid']), 'New private draft', '<p>Secret fourth version</p>', three)
    for token, selected, number, text in [(tokens[0], one, 1, 'Original budget'), (tokens[1], three, 3, 'Reviewed revised budget')]:
        url = f'/api/pages/public/{token}'
        metadata = await client.get(url)
        assert metadata.status_code == 200
        assert set(metadata.json()) == {'title', 'revision', 'version', 'updated_at'}
        assert metadata.json()['revision'] == selected and metadata.json()['version'] == number
        assert datetime.fromisoformat(metadata.json()['updated_at'].replace('Z', '+00:00')) == doc['revisions'][number-1]['created_at']
        assert metadata.headers['cache-control'] == 'no-store'
        for download in (False, True):
            content = await client.get(f'{url}/content', params={'revision': selected, 'download': str(download).lower()})
            assert content.status_code == 200 and text in content.text
            assert 'Confidential' not in content.text and 'Secret' not in content.text
            assert 'private-chat' not in content.text
            assert content.headers['content-security-policy'] == artifacts.CONTENT_CSP
        assert (await client.get(f'{url}/content', params={'revision': private})).status_code == 409
    assert (await client.get(f'/api/pages/public/{main["public_token"]}')).json()['version'] == 3


@pytest.mark.asyncio
async def test_revocation_rotation_and_deletion_do_not_affect_other_links(client, db, route_env):
    doc, (one, _, three) = three_versions(db)
    doc = artifacts.publish(db, doc, one)
    doc = artifacts.publish_separate(db, doc, one)
    doc = artifacts.publish_separate(db, doc, three)
    first, third, main = link_for(doc, one), link_for(doc, three), doc['public_token']
    endpoint = f'/api/pages/{doc["uuid"]}/publication'
    cookies, headers = _auth()
    assert (await client.delete(endpoint, params={'revision': one}, cookies=cookies, headers=headers)).status_code == 200
    assert (await client.get(f'/api/pages/public/{first}')).status_code == 404
    assert (await client.get(f'/api/pages/public/{first}/content')).status_code == 404
    for token in (third, main):
        assert (await client.get(f'/api/pages/public/{token}/content')).status_code == 200
    await client.delete(endpoint, cookies=cookies, headers=headers)
    assert (await client.get(f'/api/pages/public/{main}')).status_code == 404
    assert (await client.get(f'/api/pages/public/{third}')).status_code == 200
    republished = artifacts.publish_separate(db, artifacts.get(db, doc['uuid']), one)
    new = link_for(republished, one)
    assert new != first
    assert (await client.get(f'/api/pages/public/{first}')).status_code == 404
    assert (await client.get(f'/api/pages/public/{new}')).status_code == 200
    await client.delete(f'/api/pages/{doc["uuid"]}', cookies=cookies, headers=headers)
    for token in (new, third):
        assert (await client.get(f'/api/pages/public/{token}')).status_code == 404
        assert (await client.get(f'/api/pages/public/{token}/content')).status_code == 404


@pytest.mark.asyncio
async def test_only_owner_can_publish_or_remove_version_links_and_operator_can_disable_them(client, db, route_env):
    doc, (one, _, three) = three_versions(db)
    doc = artifacts.share_team(db, doc, 'team-a', one)
    doc = artifacts.publish_separate(db, doc, three)
    token = link_for(doc, three)
    endpoint = f'/api/pages/{doc["uuid"]}/publication'
    cookies, headers = _auth()
    route_env.user.user_id = 'other-user'
    route_env.access.return_value = TeamAccessContext(team_uuids={'team-a'})
    metadata = (await client.get(f'/api/pages/{doc["uuid"]}')).json()
    assert 'publications' not in metadata and token not in str(metadata)
    assert three not in str(metadata)
    assert (await client.put(endpoint, json={'revision': one, 'separate_link': True}, cookies=cookies, headers=headers)).status_code == 404
    assert (await client.delete(endpoint, params={'revision': three}, cookies=cookies, headers=headers)).status_code == 404
    route_env.user.user_id = 'testuser'
    assert (await client.put(endpoint, json={'revision': 'missing', 'separate_link': True}, cookies=cookies, headers=headers)).status_code == 404
    route_env.settings.artifact_public_sharing_enabled = False
    assert (await client.put(endpoint, json={'revision': one, 'separate_link': True}, cookies=cookies, headers=headers)).status_code == 403
    assert (await client.get(f'/api/pages/public/{token}')).status_code == 404
    assert (await client.get(f'/api/pages/public/{token}/content')).status_code == 404
    # Owners can still revoke links while publication is disabled.
    assert (await client.delete(endpoint, params={'revision': three}, cookies=cookies, headers=headers)).status_code == 200
    assert artifacts.get(db, doc['uuid'])['team_revision'] == one


def test_stale_owner_snapshots_cannot_overwrite_or_duplicate_version_links(db):
    doc, (one, _, three) = three_versions(db)
    first = artifacts.publish_separate(db, doc, one)
    artifacts.publish_separate(db, doc, three)
    retried = artifacts.publish_separate(db, doc, one)
    assert len(retried['publications']) == 2
    assert link_for(first, one) == link_for(retried, one)
    assert retried['published_revision'] is None


def test_legacy_page_without_publications_supports_separate_links(db):
    doc = make(db)
    del db.html_artifacts.docs[0]['publications']
    legacy = artifacts.get(db, doc['uuid'])
    saved = artifacts.publish_separate(db, legacy, legacy['latest_revision'])
    assert len(saved['publications']) == 1
    assert saved['publications'][0]['revision'] == legacy['latest_revision']
