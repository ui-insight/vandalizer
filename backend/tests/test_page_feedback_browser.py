"""The embed script's pick and show-spot modes, in a real browser.

PAGE_FEEDBACK_BROWSER=1 (Chrome via Playwright; PAGE_EMBED_BROWSER_CHANNEL
defaults to "chrome"). The page HTML is the real content_response output with
its CSP, inside a frame sandboxed exactly as the app sandboxes it.
"""
import json
import os
from datetime import datetime, timezone

import pytest

from app.routers.artifacts import content_response
from app.services import artifacts

HTML = """<h1>NIH R01 Budget</h1><p>Total budget: $620,000</p>
<table><thead><tr><th>Category</th><th>Y1</th><th>Y2</th></tr></thead><tbody>
<tr><td>Equipment</td><td>$0</td><td>$20,000</td></tr>
<tr><td>Travel</td><td>$5,000</td><td>$5,000</td></tr></tbody></table>
<p>Source notes follow.</p>"""

PARENT = """<!doctype html><html><body>
<iframe id="f" src="http://pages.test/content" sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" style="width:800px;height:600px"></iframe>
<script>
window.picks = []; window.shown = [];
addEventListener('message', e => {
  if (e.data && e.data.type === 'vandalizer:page-pick') window.picks.push(e.data);
  if (e.data && e.data.type === 'vandalizer:spot-shown') window.shown.push(e.data);
});
window.send = (msg) => document.getElementById('f').contentWindow.postMessage(msg, '*');
</script></body></html>"""


@pytest.mark.skipif(not os.environ.get('PAGE_FEEDBACK_BROWSER'), reason='Requires Playwright with Chrome')
def test_pick_reports_the_clicked_cell_and_show_spot_finds_it_again():
    from playwright.sync_api import sync_playwright

    html, _ = artifacts.clean_html(HTML, 'NIH R01 Budget')
    response = content_response({'html': html, 'title': 'NIH R01 Budget', 'created_at': datetime.now(timezone.utc)}, version=2, view='embed')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.environ.get('PAGE_EMBED_BROWSER_CHANNEL') or 'chrome')
        page = browser.new_page()
        page.route('http://app.test/', lambda route: route.fulfill(body=PARENT, content_type='text/html'))
        page.route('http://pages.test/content', lambda route: route.fulfill(body=response.body, headers=dict(response.headers)))
        page.goto('http://app.test/')
        frame = page.frame_locator('#f')
        cell = frame.get_by_role('cell', name='$20,000')
        cell.wait_for()

        # Not picking: a click is an ordinary click and reports nothing.
        cell.click()
        assert page.evaluate('window.picks') == []

        page.evaluate("send({type: 'vandalizer:pick-mode', on: true})")
        cell.click()
        page.wait_for_function('window.picks.length === 1')
        pick = page.evaluate('window.picks[0]')
        assert pick['text'] == '$20,000' and pick['path']

        # Turning picking off stops reporting.
        page.evaluate("send({type: 'vandalizer:pick-mode', on: false})")
        frame.get_by_role('cell', name='Travel').click()
        assert page.evaluate('window.picks.length') == 1

        # The owner's "Show on page": the same spot is outlined.
        page.evaluate(f"send({{type: 'vandalizer:show-spot', path: {json.dumps(pick['path'])}, text: '$20,000'}})")
        page.wait_for_function('window.shown.length === 1')
        assert page.evaluate('window.shown[0].found') is True
        assert cell.evaluate("e => e.classList.contains('vandalizer-feedback-spot')")

        # A later version moved the cell: the stored path misses, the text finds it.
        page.evaluate("send({type: 'vandalizer:show-spot', path: '0/0/0', text: '$20,000'})")
        page.wait_for_function('window.shown.length === 2')
        assert page.evaluate('window.shown[1].found') is True

        # Text that's no longer on the page: reported as not found.
        page.evaluate("send({type: 'vandalizer:show-spot', path: '', text: 'Equipment Y2 $40,000'})")
        page.wait_for_function('window.shown.length === 3')
        assert page.evaluate('window.shown[2].found') is False
        browser.close()
