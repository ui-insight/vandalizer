"""Native navigation survives sanitizing, approval, saving and publication."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from app.services import artifacts
from app.services.chat_artifact_tools import create_html_artifact, get_html_artifact, revise_html_artifact
from app.services.chat_deps import AgenticChatDeps
from app.services.access_control import TeamAccessContext
from app.services.page_links import prepare_page_links
from tests.test_artifacts import db as db, route_env as route_env
from tests.test_chat_routes import _auth, _make_user

DASHBOARD = '''<style>a:focus-visible,summary:focus-visible{outline:3px solid navy}section{margin-top:800px}</style>
<main><h1 id="top">Budget dashboard</h1>
<nav aria-label="Contents"><a href="#budget-chart">Budget chart</a><a href="#notes">Notes</a></nav>
<a class="kpi" href="#budget-chart">Total budget: $150,000</a>
<section id="budget-chart"><h2>Budget by category</h2><div style="width:70%;background:navy">Personnel $100,000</div>
<table><tr><th>Personnel</th><td>$100,000</td></tr><tr><th>Equipment</th><td>$50,000</td></tr></table></section>
<section id="notes"><h2>Notes and calculations</h2>
<details><summary>Source notes</summary><p>Source figures are in USD.</p><a href="https://source.test/award">Award source</a></details>
<details><summary>Calculated summary</summary><p>$100,000 + $50,000 = $150,000</p></details>
<a href="mailto:grants@example.test">Contact grants team</a><a href="#top">Back to top</a></section></main>'''


def assert_controls(html):
    soup = BeautifulSoup(html, 'html.parser')
    for link in soup.select('a[href^="#"]'):
        assert soup.find(id=link['href'][1:]) is not None
        assert not link.has_attr('target')
    assert [node.text for node in soup.select('details > summary')] == ['Source notes', 'Calculated summary']
    assert soup.select_one('a.kpi')['href'] == '#budget-chart'
    for link in soup.select('a[href^="https:"], a[href^="mailto:"]'):
        assert link['target'] == '_blank'
        assert set(link['rel']) == {'noopener', 'noreferrer'}
    assert soup.select_one('table').text == 'Personnel$100,000Equipment$50,000'


def test_safe_controls_survive_repeated_sanitization_without_warnings():
    html, warnings = artifacts.clean_html(DASHBOARD, 'Budget')
    assert warnings == []
    assert_controls(html)
    assert artifacts.clean_html(html, 'Budget') == (html, [])


def test_link_targets_cannot_navigate_app_or_retain_an_opener():
    html, warnings = artifacts.clean_html('''<a href="#notes" target="_top">Notes</a><h2 id="notes">Notes</h2>
    <a href="https://source.test" target="_parent" rel="opener" referrerpolicy="unsafe-url">Source</a>
    <a href="javascript:alert(1)" onclick="alert(2)">Unsafe</a><a href="data:text/html,unsafe">Data</a>
    <script>alert(3)</script><form><input></form>''', 'Safety')
    soup = BeautifulSoup(html, 'html.parser')
    assert warnings and not soup.select('script, form, input, [onclick], [referrerpolicy]')
    links = soup.find_all('a')
    assert links[0].get('target') is None
    assert links[1]['target'] == '_blank' and set(links[1]['rel']) == {'noopener', 'noreferrer'}
    assert links[2].get('href') is None and links[3].get('href') is None
    csp = soup.select_one('meta[http-equiv="Content-Security-Policy"]')['content']
    assert "sandbox allow-popups allow-popups-to-escape-sandbox;" in csp
    assert "script-src 'none'" in csp and "connect-src 'none'" in csp and "form-action 'none'" in csp
    assert 'allow-same-origin' not in csp and 'allow-top-navigation' not in csp


def test_delivery_normalizes_legacy_links_without_changing_the_stored_revision():
    original = '<a href="https://source.test">Source</a><a href="#notes" target="_blank">Notes</a><h2 id="notes">Notes</h2>'
    html, csp = prepare_page_links(original, artifacts.CONTENT_CSP)
    assert 'target="_blank"' in html and 'noopener noreferrer' in html
    assert BeautifulSoup(html, 'html.parser').select_one('a[href="#notes"]').get('target') is None
    assert prepare_page_links(html, csp) == (html, csp)
    # Delivery can preserve the independent trusted print handler's permissions.
    _, print_csp = prepare_page_links(original, "sandbox allow-scripts allow-modals; script-src 'nonce-test'")
    assert 'allow-scripts allow-modals' in print_csp and "script-src 'nonce-test'" in print_csp


@pytest.mark.asyncio
async def test_chat_preview_save_revision_and_public_content_keep_native_controls(client, db, route_env):
    conversation = SimpleNamespace(uuid='interactive-budget', pending_confirmations=[], save=AsyncMock())
    deps = AgenticChatDeps(user=_make_user(), user_id='testuser', team_id=None, team_access=TeamAccessContext(),
        organization_id=None, system_config_doc={}, model_name='test', conversation=conversation, turn_marker=1)
    context = SimpleNamespace(deps=deps)
    with patch('app.services.chat_artifact_tools.get_sync_db', return_value=db):
        preview = await create_html_artifact(context, 'Budget', DASHBOARD)
        assert preview['needs_confirmation'] and preview['warnings'] == []
        assert_controls(preview['artifact_preview_html'])
        deps.turn_marker = 2
        saved = await create_html_artifact(context, 'Budget', DASHBOARD, confirmed=True)
        read = await get_html_artifact(context, saved['artifact_uuid'])
        assert read['html'] == preview['artifact_preview_html']
        revised_html = read['html'].replace('Source figures are in USD.', 'Source figures are in US dollars.')
        revised_preview = await revise_html_artifact(context, saved['artifact_uuid'], saved['revision'], 'Budget', revised_html)
        assert_controls(revised_preview['artifact_preview_html'])
        deps.turn_marker = 3
        saved = await revise_html_artifact(context, saved['artifact_uuid'], saved['revision'], 'Budget', revised_html, confirmed=True)
    cookies, headers = _auth()
    publication = await client.put(f'/api/pages/{saved["artifact_uuid"]}/publication', json={'revision': saved['revision']}, cookies=cookies, headers=headers)
    token = publication.json()['public_token']
    for url in (f'/api/pages/{saved["artifact_uuid"]}/revisions/{saved["revision"]}/content', f'/api/pages/public/{token}/content'):
        for download in (False, True):
            response = await client.get(url, params={'download': str(download).lower()})
            assert response.status_code == 200
            assert_controls(response.text)
            assert "script-src 'none'" in response.headers['content-security-policy']
            assert 'sandbox allow-popups allow-popups-to-escape-sandbox;' in response.headers['content-security-policy']
            assert response.headers['referrer-policy'] == 'no-referrer'
