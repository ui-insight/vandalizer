"""Design isolation, new-file grounding, sharing, and immutable Page approval."""
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup
from fastapi import HTTPException

from app.schemas.page_template import SaveTemplate, TemplateCell, TemplateTable, TemplateValue
from app.services import artifacts, chat_page_previews, page_templates
from app.services.access_control import TeamAccessContext
from app.services.chat_artifact_tools import create_html_artifact
from app.services.chat_deps import AgenticChatDeps
from tests import test_artifacts
from tests.test_artifacts import Collection, route_env as route_env
from tests.test_chat_routes import _auth, _make_user

artifact_db = test_artifacts.db

ORIGINAL = '''<style>.old-smith{color:#123456;display:grid;grid-template-columns:1fr 1fr}
#award-R01-SECRET .bar{width:67%;background:navy}p:after{content:"SECRET-77889"}
.leak[data-name="Smith"]{color:red}</style><main id="award-R01-SECRET" class="old-smith">
<h1>Dr Smith award R01-SECRET</h1><nav><a href="#chart">Budget</a></nav>
<section id="chart"><h2>Budget by category</h2><div class="bar" style="width:67%;background:navy" title="SECRET-77889">$77889</div>
<table><thead><tr><th>Category</th><th>Amount</th></tr></thead><tbody><tr><td>Personnel</td><td>$77889</td></tr></tbody></table>
<a href="https://private.test/SECRET-77889">Source notes</a><img src="data:image/png;base64,U0VDUkVU" alt="Smith" />
<aside class="guidance"><h2>Guidance</h2><p>Contact Dr Smith about $77889 by 2099.</p></aside></section></main>'''


class Cursor(list):
    def sort(self, keys):
        for key, direction in reversed(keys):
            super().sort(key=lambda item: item.get(key, ''), reverse=direction < 0)
        return self

    def skip(self, count):
        return Cursor(self[count:])

    def limit(self, count):
        return Cursor(self[:count])


class Templates(Collection):
    def matches(self, doc, query):
        for key, value in query.items():
            if isinstance(value, dict) and '$regex' in value:
                if not re.search(value['$regex'], doc.get(key, ''), re.I):
                    return False
            elif not super().matches(doc, {key: value}):
                return False
        return True

    def find(self, query):
        return Cursor([doc for doc in self.docs if self.matches(doc, query)])

    def count_documents(self, query):
        return len(self.find(query))


@pytest.fixture
def db(artifact_db):
    artifact_db.page_templates = Templates()
    artifact_db.page_template_drafts = Collection()
    return artifact_db


@pytest.fixture
def routes(db, route_env):
    with patch('app.routers.page_templates.get_sync_db', return_value=db):
        yield route_env


def make_template(db, owner='testuser'):
    draft = page_templates.prepare(db, owner, ORIGINAL)
    return page_templates.save(db, owner, 'Design owner', SaveTemplate(draft_id=draft['draft_id'], name='NIH Budget Dashboard', guidance='Review the source before making decisions.'))


def source(text='New award\nPersonnel $250\nEquipment $500', uuid='new-file'):
    return SimpleNamespace(uuid=uuid, title='New budget.xlsx', raw_text=text, processing=False, soft_deleted=False)


def test_design_clears_text_attributes_links_images_css_content_and_chart_values(db):
    template = make_template(db)
    stored = json.dumps(template, default=str)
    for old in ('Smith', 'SECRET', '77889', '2099', 'private.test', 'U0VDUkVU', '67%'):
        assert old not in stored
    assert 'grid-template-columns:1fr 1fr' in template['html']
    assert '#123456' in template['html'] and 'background:navy' in template['html']
    assert 'Budget by category' in template['html']
    preview, count = page_templates.render(template, {})
    soup = BeautifulSoup(preview, 'html.parser')
    assert count == 0 and page_templates.MISSING in soup.get_text()
    assert soup.find(id=soup.select_one('a[href^="#"]')['href'][1:])
    assert soup.select_one('aside').get_text(' ', strip=True) == 'Guidance Review the source before making decisions.'
    assert 'width:auto;background:none;border:1px dashed gray' in preview
    assert not soup.select('img, [title], [data-template-bar], [data-template-table]')


def test_bare_body_text_and_unusual_source_labels_are_fields_not_saved_data():
    result = page_templates.design('<body>SECRET-123<p>Unfamiliar confidential label</p><small>Smith</small></body>')
    assert all(value not in json.dumps(result) for value in ['SECRET', '123', 'confidential', 'Smith'])
    assert len(result['fields']) == 3


def test_standard_words_in_data_cells_are_not_carried_over_as_design_labels():
    template = page_templates.design('<h2>Budget</h2><table><thead><tr><th>Category</th><th>Amount</th></tr></thead><tr><td><a href="#x">Personnel</a></td><td>$100</td></tr></table><dl><dt>Sponsor</dt><dd>Travel</dd></dl>')
    html, count = page_templates.render(template, {})
    soup = BeautifulSoup(html, 'html.parser')
    assert count == 0
    assert 'Personnel' not in html and 'Travel' not in html and '$100' not in html
    assert soup.select_one('h2').text == 'Budget'
    assert [cell.text for cell in soup.select('td')] == [page_templates.MISSING, page_templates.MISSING]
    assert template['fields'][0]['label'] == 'Category'


def test_values_need_evidence_from_new_file_and_missing_fields_have_no_fallback(db):
    template = make_template(db)
    field = template['fields'][0]['id']
    for value, quote in [('$77889', 'Personnel $77889'), ('$250', 'Equipment $250'), ('25', 'Personnel $250'), (' ', ' ')]:
        with pytest.raises(HTTPException, match='not supported'):
            page_templates.fill(template, source(), [TemplateValue(field_id=field, value=value, quote=quote)])
    html, check = page_templates.fill(template, source(), [TemplateValue(field_id=field, value='New award', quote='New award')])
    assert check['filled'] == 1 and check['retained'] == 0 and check['missing'] == len(template['fields']) - 1
    assert check['source_title'] == 'New budget.xlsx'
    assert '$77889' not in html and page_templates.MISSING in html
    assert 'New award' in html


def test_new_table_rows_replace_old_shape_and_keep_every_new_value(db):
    template = make_template(db)
    table = template['tables'][0]
    def row(label, value):
        return [TemplateCell(value=label, quote=f'{label} {value}'), TemplateCell(value=value, quote=f'{label} {value}')]
    html, check = page_templates.fill(template, source(), [], [TemplateTable(table_id=table['id'], rows=[row('Personnel', '$250'), row('Equipment', '$500')])])
    soup = BeautifulSoup(html, 'html.parser')
    assert [row.get_text('|') for row in soup.select('tbody tr')] == ['Personnel|$250', 'Equipment|$500']
    assert check['filled'] == 4 and check['retained'] == 0
    assert check['missing'] == len(template['fields']) - len(table['field_ids'])
    assert '$77889' not in html


def test_a_missing_table_shows_missing_cells_instead_of_an_empty_chart(db):
    template = make_template(db)
    table = template['tables'][0]
    html, check = page_templates.fill(template, source(), [], [TemplateTable(table_id=table['id'], rows=[])])
    soup = BeautifulSoup(html, 'html.parser')
    assert [cell.text for cell in soup.select('tbody td')] == [page_templates.MISSING] * table['columns']
    assert check['filled'] == 0 and check['missing'] >= table['columns']


def test_repeated_source_values_and_untrusted_markup_remain_literal(db):
    template = make_template(db)
    ids = [field['id'] for field in template['fields']]
    value = '<script>danger()</script>'
    html, check = page_templates.fill(template, source(value), [TemplateValue(field_id=field, value=value, quote=value) for field in ids])
    assert check['filled'] == len(ids)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert not BeautifulSoup(html, 'html.parser').find('script')


def test_numeric_quotes_cannot_support_partial_amounts_signs_or_percentages(db):
    template = make_template(db)
    field = template['fields'][0]['id']
    for value, quote in [('250', '250.50'), ('250', '1,250'), ('250', '-250'), ('250', '250%'), ('$250', '$250.50')]:
        with pytest.raises(HTTPException, match='not supported'):
            page_templates.fill(template, source(quote), [TemplateValue(field_id=field, value=value, quote=quote)])


@pytest.mark.asyncio
async def test_prepare_save_private_browse_team_access_and_revocation(client, db, routes):
    original = artifacts.create(db, 'testuser', 'Private old award', ORIGINAL, 'page')
    cookies, headers = _auth()
    endpoint = '/api/page-templates'
    draft = await client.post(endpoint + '/prepare', json={'artifact_uuid': original['uuid'], 'revision': original['latest_revision']}, cookies=cookies, headers=headers)
    assert draft.status_code == 200
    assert '77889' not in draft.text
    payload = {'draft_id': draft.json()['draft_id'], 'name': 'NIH Budget Dashboard', 'description': 'Reusable budget review', 'guidance': 'Review the source.'}
    saved = await client.post(endpoint, json=payload, cookies=cookies, headers=headers)
    assert saved.status_code == 200 and saved.json()['team_id'] is None
    uuid = saved.json()['uuid']
    assert (await client.post(endpoint, json=payload, cookies=cookies, headers=headers)).json()['uuid'] == uuid
    listed = await client.get(endpoint, params={'search': 'NIH'})
    assert listed.json()['total'] == 1 and listed.json()['items'][0]['owner_name']
    assert 'html' not in listed.json()['items'][0]
    for suffix in ('', '/content'):
        assert (await client.get(f'{endpoint}/{uuid}{suffix}')).status_code == 200
    assert (await client.put(f'{endpoint}/{uuid}/team', json={'team_id': 'team-a'}, cookies=cookies, headers=headers)).status_code == 404
    routes.access.return_value = TeamAccessContext(team_uuids={'team-a'})
    assert (await client.put(f'{endpoint}/{uuid}/team', json={'team_id': 'team-a'}, cookies=cookies, headers=headers)).status_code == 200
    routes.user.user_id = 'teammate'
    assert (await client.get(endpoint)).json()['total'] == 1
    assert (await client.get(f'{endpoint}/{uuid}')).json()['can_manage'] is False
    assert (await client.get(f'{endpoint}/{uuid}/content')).status_code == 200
    assert (await client.delete(f'{endpoint}/{uuid}', cookies=cookies, headers=headers)).status_code == 404
    assert (await client.get(f'/api/pages/{original["uuid"]}')).status_code == 404
    routes.access.return_value = TeamAccessContext()
    assert (await client.get(endpoint)).json()['items'] == []
    assert (await client.get(f'{endpoint}/{uuid}/content')).status_code == 404
    routes.user.user_id = 'testuser'
    assert (await client.delete(f'{endpoint}/{uuid}', cookies=cookies, headers=headers)).status_code == 200
    assert (await client.get(f'{endpoint}/{uuid}/content')).status_code == 404
    assert artifacts.get(db, original['uuid'])['latest_revision'] == original['latest_revision']


@pytest.mark.asyncio
async def test_chat_preview_source_authorization_and_forged_draft_are_rejected(client, db, routes):
    preview = chat_page_previews.prepare(db, 'testuser', 'chat', 'Page', ORIGINAL, None, None, {})
    cookies, headers = _auth()
    endpoint = '/api/page-templates'
    assert (await client.post(endpoint + '/prepare', json={'preview_id': preview['_id']}, cookies=cookies, headers=headers)).status_code == 200
    routes.user.user_id = 'stranger'
    assert (await client.post(endpoint + '/prepare', json={'preview_id': preview['_id']}, cookies=cookies, headers=headers)).status_code == 404
    assert (await client.post(endpoint, json={'draft_id': 'invented', 'name': 'Forged'}, cookies=cookies, headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_template_use_ignores_model_html_and_saves_verified_private_preview(db, routes):
    template = make_template(db)
    conversation = SimpleNamespace(uuid='template-chat', pending_confirmations=[], save=AsyncMock())
    deps = AgenticChatDeps(user=_make_user(), user_id='testuser', team_id=None, team_access=TeamAccessContext(), organization_id=None, system_config_doc={}, model_name='test', conversation=conversation, turn_marker=1, context_document_uuids=['new-file'])
    context = SimpleNamespace(deps=deps)
    value = TemplateValue(field_id=template['fields'][0]['id'], value='New award', quote='New award')
    with patch('app.services.chat_artifact_tools.get_sync_db', return_value=db), patch('app.services.access_control.get_authorized_document', AsyncMock(return_value=source())):
        preview = await create_html_artifact(context, 'New Page', '<p>OLD $77889</p>', template_uuid=template['uuid'], source_document_uuid='new-file', template_values=[value])
        assert preview['needs_confirmation']
        assert '$77889' not in preview['artifact_preview_html']
        assert preview['template_check']['filled'] == 1
        saved = chat_page_previews.save(db, 'testuser', 'template-chat', preview['preview_id'])
        assert saved['template_check'] == preview['template_check']
        page = artifacts.get(db, saved['artifact_uuid'])
        assert not page['team_id'] and not page['public_token']
        assert artifacts.revision(page)['html'] == preview['artifact_preview_html']
        assert chat_page_previews.save(db, 'testuser', 'template-chat', preview['preview_id'])['artifact_uuid'] == page['uuid']
        other = await create_html_artifact(context, 'New Page', template_uuid=template['uuid'], source_document_uuid='wrong-file', template_values=[value])
        assert 'error' in other


def test_preview_identity_binds_template_and_new_source_even_when_values_match(db):
    first = chat_page_previews.prepare(db, 'u', 'c', 'Same', '<p>250</p>', None, None, {'template_uuid': 't', 'template_check': {'source_document_uuid': 'one'}})
    second = chat_page_previews.prepare(db, 'u', 'c', 'Same', '<p>250</p>', None, None, {'template_uuid': 't', 'template_check': {'source_document_uuid': 'two'}})
    assert first['_id'] != second['_id']


def test_theme_and_responsive_layout_survive_without_flattening_media_rules():
    template = page_templates.design('<style>body{font:16px/1.6 system-ui;color:navy}.cards{display:grid;grid-template-columns:1fr 1fr}@media (max-width:600px){.cards{grid-template-columns:1fr}}@font-face{font-family:SECRET;src:url(https://secret.test/font)}</style><div class="cards"><p>Private source</p></div>')
    assert 'font:16px/1.6 system-ui' in template['html']
    assert '@media (max-width:600px){.tc1{grid-template-columns:1fr}}' in template['html']
    assert 'SECRET' not in template['html'] and 'secret.test' not in template['html']


def test_template_tool_schema_exposes_source_checked_values_and_table_rows():
    from pydantic_ai import Tool
    schema = Tool(create_html_artifact).tool_def.parameters_json_schema
    assert {'template_uuid', 'source_document_uuid', 'template_values', 'template_tables'} <= set(schema['properties'])


def test_unconfirmed_template_save_can_retry_the_same_identity(db):
    draft = page_templates.prepare(db, 'testuser', ORIGINAL)
    body = SaveTemplate(draft_id=draft['draft_id'], name='Retryable template')
    save = db.page_templates.find_one_and_update

    def saved_but_unconfirmed(*args, **kwargs):
        save(*args, **kwargs)
        return None

    with patch.object(db.page_templates, 'find_one_and_update', side_effect=saved_but_unconfirmed):
        with pytest.raises(HTTPException) as exc:
            page_templates.save(db, 'testuser', 'Owner', body)
    assert exc.value.status_code == 503
    recovered = page_templates.save(db, 'testuser', 'Owner', body)
    assert recovered['name'] == body.name
    assert len(db.page_templates.docs) == 1
