"""Edit text in a real browser: typed changes round-trip to the saved HTML.

PAGE_FEEDBACK_BROWSER=1 (Chrome via Playwright; PAGE_EMBED_BROWSER_CHANNEL
defaults to "chrome"). The page is the real content_response output with its
CSP, inside a frame sandboxed as the app sandboxes it. The browser wraps
tables and adds <tbody>; the edits must still land on the right cells.
"""
import os
from datetime import datetime, timezone

import pytest

from app.routers.artifacts import content_response
from app.services import artifacts
from app.services.page_text_edits import TextEdit, apply

HTML = """<h1>NIH R01 Budget Dashbord</h1><p>Total request: <strong>$1.25M</strong> over five years.</p>
<table><tr><th>Category</th><th>Y1</th><th>Y2</th></tr>
<tr><td>Personnel</td><td>$124k</td><td>$124k</td></tr></table>"""

PARENT = """<!doctype html><html><body>
<iframe id="f" src="http://pages.test/content" sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" style="width:800px;height:600px"></iframe>
<script>
window.counts = []; window.edits = null;
addEventListener('message', e => {
  if (e.data && e.data.type === 'vandalizer:edit-count') window.counts.push(e.data.count);
  if (e.data && e.data.type === 'vandalizer:edits') window.edits = e.data.edits;
});
window.send = (msg) => document.getElementById('f').contentWindow.postMessage(msg, '*');
</script></body></html>"""


@pytest.mark.skipif(not os.environ.get('PAGE_FEEDBACK_BROWSER'), reason='Requires Playwright with Chrome')
def test_typed_fixes_land_on_the_right_blocks_of_the_saved_html():
    from playwright.sync_api import sync_playwright

    saved, _ = artifacts.clean_html(HTML, 'NIH R01 Budget Dashboard')
    response = content_response({'html': saved, 'title': 'NIH R01 Budget Dashboard', 'created_at': datetime.now(timezone.utc)}, version=5, view='embed')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.environ.get('PAGE_EMBED_BROWSER_CHANNEL') or 'chrome')
        page = browser.new_page()
        page.route('http://app.test/', lambda route: route.fulfill(body=PARENT, content_type='text/html'))
        page.route('http://pages.test/content', lambda route: route.fulfill(body=response.body, headers=dict(response.headers)))
        page.goto('http://app.test/')
        frame = page.frame_locator('#f')
        heading = frame.get_by_role('heading', name='NIH R01 Budget Dashbord')
        heading.wait_for()
        # Not editing: the page is read-only.
        assert heading.evaluate('e => e.isContentEditable') is False
        page.evaluate("send({type: 'vandalizer:edit-mode', on: true})")
        heading.click()
        page.keyboard.press('End')
        for key in ('ArrowLeft', 'ArrowLeft'):
            page.keyboard.press(key)
        page.keyboard.type('a')  # Dashbord -> Dashboard
        page.keyboard.press('Enter')  # single-line blocks ignore Enter
        second = frame.get_by_role('cell', name='$124k').nth(1)
        second.click()
        for key in ('End', 'Backspace', 'Backspace', 'Backspace'):
            page.keyboard.press(key)
        page.keyboard.type('42k')  # $124k -> $142k, second cell only
        page.wait_for_function('window.counts.length > 0 && window.counts[window.counts.length - 1] === 2')
        page.evaluate("send({type: 'vandalizer:edit-collect'})")
        page.wait_for_function('window.edits !== null')
        edits = page.evaluate('window.edits')
        browser.close()
    assert {e['text'] for e in edits} == {'NIH R01 Budget Dashboard', '$142k'}
    html, notes = apply(saved, [TextEdit(**e) for e in edits])
    assert '<h1>NIH R01 Budget Dashboard</h1>' in html and notes == []
    assert '<td>$124k</td><td>$142k</td>' in html
