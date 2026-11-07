from bs4 import BeautifulSoup

from app.routers.artifacts import content_response
from app.services import artifacts
from tests.test_artifacts import db as db, route_env as route_env, make


def test_embed_uses_only_trusted_sizing_script_and_preserves_saved_source(db):
    doc = make(db, html='<h1>Budget</h1><table><tr><td>$121,600</td></tr></table><script>steal()</script>')
    revision = artifacts.revision(doc)
    original = revision['html']
    response = content_response(revision, view='embed')
    soup = BeautifulSoup(response.body, 'html.parser')
    script, = soup.select('script')
    csp = response.headers['content-security-policy']
    assert f"script-src 'nonce-{script['nonce']}'" in csp
    assert 'sandbox allow-scripts' in csp and 'allow-same-origin' not in csp
    assert "connect-src 'none'" in csp and "frame-src 'none'" in csp
    assert 'allow-modals' not in csp
    assert soup.select_one('meta[http-equiv="Content-Security-Policy"]')['content'] == csp
    assert 'vandalizer:page-height' in script.text and 'steal()' not in response.body.decode()
    assert soup.td.text == '$121,600' and revision['html'] == original
    assert content_response(revision, view='embed').headers['content-security-policy'] != csp
    for options in ({}, {'download': True, 'view': 'embed'}):
        static = content_response(revision, **options)
        assert '<script' not in static.body.decode()
        assert "script-src 'none'" in static.headers['content-security-policy']


async def test_embedded_public_content_is_bound_to_the_published_version(client, db, route_env):
    doc = make(db)
    shared = doc['latest_revision']
    doc = artifacts.publish(db, doc, shared)
    token = doc['public_token']
    artifacts.revise(db, doc, 'Private draft', '<p>Secret figures</p>', shared)
    response = await client.get(f'/api/pages/public/{token}/content?revision={shared}&view=embed')
    assert response.status_code == 200
    assert 'vandalizer-embed-script' in response.text
    assert 'Secret figures' not in response.text and 'Private draft' not in response.text
    assert (await client.get(f'/api/pages/public/{token}/content?revision=stale&view=embed')).status_code == 409
    route_env.user.user_id = 'other'
    assert (await client.get(f'/api/pages/{doc["uuid"]}/revisions/{shared}/content?view=embed')).status_code == 404
    artifacts.unpublish(db, artifacts.get(db, doc['uuid']))
    assert (await client.get(f'/api/pages/public/{token}/content?view=embed')).status_code == 404
