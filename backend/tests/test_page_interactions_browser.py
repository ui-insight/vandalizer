"""Opt-in Chromium check: PAGE_INTERACTION_BROWSER_TESTS=1 pytest tests/test_page_interactions_browser.py."""
import os
from html import escape

import pytest
from bs4 import BeautifulSoup

from app.services import artifacts, chat_page_previews
from app.services.page_links import PAGE_LINK_SANDBOX
from app.routers.artifacts import content_response
from tests.test_artifacts import db as db
from tests.test_page_interactions import DASHBOARD


@pytest.mark.skipif(os.environ.get('PAGE_INTERACTION_BROWSER_TESTS') != '1', reason='Requires local Playwright Chromium')
@pytest.mark.parametrize('parent_csp', [None, "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'"])
def test_clickable_controls_in_preview_saved_and_public_pages(db, parent_csp):
    from playwright.sync_api import sync_playwright, expect

    preview = chat_page_previews.prepare(db, 'owner', 'chat', 'Budget', DASHBOARD, None, None, {'kind': 'chat'})
    saved = chat_page_previews.save(db, 'owner', 'chat', preview['_id'])
    doc = artifacts.get(db, saved['artifact_uuid'])
    public = artifacts.publish(db, doc, saved['revision'])
    response = content_response(artifacts.revision(doc))
    public_response = content_response(artifacts.revision(public, public['published_revision']))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=os.environ.get('PAGE_INTERACTION_BROWSER_CHANNEL') or None)
        context = browser.new_context()
        # All navigation stays in this synthetic test; no network or mail is sent.
        context.route('https://source.test/award', lambda route: route.fulfill(
            body='<h1>Award source</h1><script>window.destinationWorks = true;</script>', content_type='text/html'))
        for view, rendered in [('preview', None), ('saved', response), ('public', public_response)]:
            page = context.new_page()
            errors = []
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            if rendered is None:
                # Same fragment normalization as PagePreview, also covered by its component test.
                soup = BeautifulSoup(preview['prepared_html'], 'html.parser')
                for link in soup.select('a[href^="#"]'):
                    link['href'] = 'about:srcdoc' + link['href']
                html = str(soup).replace('</body>', '<script>window.untrustedRan = true;</script></body>')
                frame = f'<iframe title="Page preview" sandbox="{PAGE_LINK_SANDBOX}" srcdoc="{escape(html, quote=True)}" style="width:900px;height:600px"></iframe>'
            else:
                content_url = f'http://pages.test/{view}/content'
                page.route(content_url, lambda route, request, rendered=rendered: route.fulfill(
                    body=rendered.body.decode().replace('</body>', '<script>window.untrustedRan = true;</script></body>'),
                    headers=dict(rendered.headers)))
                frame = f'<iframe title="Page preview" sandbox="{PAGE_LINK_SANDBOX}" src="{content_url}" style="width:900px;height:600px"></iframe>'
            page.route(f'http://pages.test/{view}', lambda route, request, frame=frame: route.fulfill(body=frame, content_type='text/html', headers={'Content-Security-Policy': parent_csp} if parent_csp else {}))
            page.goto(f'http://pages.test/{view}')
            content = page.frame_locator('iframe')
            expect(content.get_by_role('heading', name='Budget dashboard')).to_be_visible()
            content.get_by_role('link', name='Total budget: $150,000').click()
            expect(content.locator('#budget-chart')).to_be_in_viewport()
            assert page.frames[1].url.endswith('#budget-chart')
            assert page.frames[1].evaluate('window.untrustedRan') is None
            content.get_by_role('link', name='Back to top').click()
            expect(content.locator('#top')).to_be_in_viewport()
            content.get_by_role('link', name='Notes', exact=True).click()
            expect(content.get_by_text('Source figures are in USD.')).not_to_be_visible()
            content.locator('summary').filter(has_text='Source notes').click()
            expect(content.get_by_text('Source figures are in USD.')).to_be_visible()
            content.locator('summary').filter(has_text='Calculated summary').press('Enter')
            expect(content.get_by_text('$100,000 + $50,000 = $150,000')).to_be_visible()
            content.locator('summary').filter(has_text='Calculated summary').press('Enter')
            expect(content.get_by_text('$100,000 + $50,000 = $150,000')).not_to_be_visible()
            with page.expect_popup() as opened:
                content.get_by_role('link', name='Award source').click()
            destination = opened.value
            expect(destination.get_by_role('heading', name='Award source')).to_be_visible()
            assert destination.evaluate('window.opener === null && document.referrer === "" && window.destinationWorks === true')
            destination.close()
            content.get_by_role('link', name='Contact grants team').click()
            assert not any('external protocol blocked by sandbox' in message.lower() for message in errors)
            assert page.url == f'http://pages.test/{view}'
            page.close()
        browser.close()
