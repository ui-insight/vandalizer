"""PAGE_EMBED_BROWSER_URL=http://127.0.0.1:4191 with a local Vite server."""
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.routers.artifacts import content_response
from app.services import artifacts


HTML = """<style>
body{font:16px/1.6 system-ui;margin:0;background:#faf7ef;color:#222}
header,main,footer{padding:24px}section{margin:36px 0}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:16px}
.card{background:white;padding:24px}.chart{height:450px;background:#fff;padding:18px}.bar{height:30px;background:#eab308;width:70%;margin:20px 0}
table{min-width:780px;border-collapse:collapse;width:100%}td,th{padding:14px;border:1px solid #aaa}details p{height:400px}
</style><header><h1>NIH R01 Budget Dashboard</h1><p>How to read this page</p></header><main>
<div class="cards"><div class="card">Total budget: $620,000</div><div class="card">5 project years</div><div class="card">Grant summary</div></div>
<section><h2>Yearly Totals</h2><div class="chart"><div class="bar">Y1</div><div class="bar">Y2</div><div class="bar">Y3</div></div></section>
<section><h2>Category Breakdown</h2><div class="chart"><div class="bar">Personnel</div><div class="bar">Travel</div><div class="bar">Supplies</div></div></section>
<section><h2>Full Budget Table</h2><table><thead><tr><th>Category</th><th>Y1</th><th>Y2</th><th>Y3</th><th>Y4</th><th>Y5</th></tr></thead><tbody>
<tr><td>Salaries</td><td>$50,000</td><td>$52,000</td><td>$54,000</td><td>$56,000</td><td>$58,000</td></tr>
<tr><td>Fringe</td><td>$15,000</td><td>$15,600</td><td>$16,200</td><td>$16,800</td><td>$17,400</td></tr>
</tbody></table></section><section><h2>Source notes</h2><details><summary>Expand source notes</summary><p>Source detail fills this section.</p></details></section>
<section><h2>Calculated summary</h2><p>All source values remain accessible.</p></section></main><footer>End of budget dashboard</footer>"""


@pytest.mark.skipif(not os.environ.get('PAGE_EMBED_BROWSER_URL'), reason='Requires local Vite and Playwright Chrome')
def test_phone_reader_has_one_vertical_scroll_with_reachable_tables_and_resizing_notes(tmp_path):
    from playwright.sync_api import sync_playwright, expect

    base = os.environ['PAGE_EMBED_BROWSER_URL']
    html, _ = artifacts.clean_html(HTML, 'NIH R01 Budget Dashboard')
    revision = {'html': html, 'title': 'NIH R01 Budget Dashboard', 'created_at': datetime.now(timezone.utc)}
    response = content_response(revision, version=4, view='embed')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.environ.get('PAGE_EMBED_BROWSER_CHANNEL') or None)
        context = browser.new_context(viewport={'width': 393, 'height': 852}, is_mobile=True, has_touch=True)
        page = context.new_page()
        page.route(f'{base}/api/pages/public/phone-fixture', lambda route: route.fulfill(json={
            'title': revision['title'], 'revision': 'r4', 'version': 4, 'updated_at': '2026-10-29T12:00:00Z'}))
        page.route(f'{base}/api/pages/public/phone-fixture/content?revision=r4&view=embed', lambda route: route.fulfill(
            body=response.body.decode().replace('</body>', '<script>window.untrustedRan = true;</script></body>'), headers=dict(response.headers)))
        page.goto(f'{base}/e2e/fixtures/published-page.html')
        element = page.get_by_title('Published page content')
        page.wait_for_function("parseFloat(document.querySelector('.page-published-content')?.style.height) > 1500")
        frame = element.element_handle().content_frame()
        frame.wait_for_function('document.scrollingElement.scrollHeight <= innerHeight + 2')
        assert frame.evaluate('window.untrustedRan') is None
        assert frame.evaluate('(() => { try { parent.document.body; return false; } catch { return true; } })()')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(tmp_path / 'phone-top.png'))
        cdp = context.new_cdp_session(page)
        visited = set()
        for _ in range(10):
            cdp.send('Input.synthesizeScrollGesture', {'x': 195, 'y': 710, 'yDistance': -350, 'gestureSourceType': 'touch', 'speed': 700})
            for title in ('Yearly Totals', 'Category Breakdown', 'Full Budget Table', 'Source notes', 'Calculated summary'):
                box = frame.get_by_role('heading', name=title, exact=True).bounding_box()
                if box and 0 <= box['y'] < 800:
                    visited.add(title)
                    if title == 'Full Budget Table':
                        page.screenshot(path=str(tmp_path / 'phone-table.png'))
            assert frame.evaluate('scrollY') == 0
        assert visited == {'Yearly Totals', 'Category Breakdown', 'Full Budget Table', 'Source notes', 'Calculated summary'}
        assert page.evaluate('scrollY') > 500
        page.screenshot(path=str(tmp_path / 'phone-bottom.png'))
        table = frame.get_by_role('region', name='Table (scroll horizontally)', exact=True)
        table.scroll_into_view_if_needed()
        box = table.bounding_box()
        cdp.send('Input.synthesizeScrollGesture', {'x': min(340, box['x'] + box['width'] - 20), 'y': box['y'] + 40, 'xDistance': -180, 'gestureSourceType': 'touch', 'speed': 500})
        assert table.evaluate('(e) => e.scrollLeft') > 0
        height = float(element.evaluate('(e) => e.style.height').removesuffix('px'))
        frame.get_by_text('Expand source notes', exact=True).click()
        page.wait_for_function('(height) => parseFloat(document.querySelector(".page-published-content").style.height) > height + 300', arg=height)
        frame.get_by_text('Expand source notes', exact=True).click()
        page.wait_for_function('(height) => parseFloat(document.querySelector(".page-published-content").style.height) === height', arg=height)
        page.set_viewport_size({'width': 852, 'height': 393})
        frame.wait_for_function('document.scrollingElement.scrollHeight <= innerHeight + 2')
        expect(frame.get_by_text('End of budget dashboard')).to_be_attached()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        browser.close()
    print(f'Published Page phone QA: {tmp_path}')


@pytest.mark.skipif(not os.environ.get('PAGE_EMBED_QA_HTML') or not os.environ.get('PAGE_EMBED_BROWSER_URL'), reason='Optional local copy of the reported public HTML and local Vite server')
def test_reported_page_html_at_phone_size(tmp_path):
    from playwright.sync_api import sync_playwright

    base = os.environ['PAGE_EMBED_BROWSER_URL']
    revision = {'html': Path(os.environ['PAGE_EMBED_QA_HTML']).read_text(), 'title': 'NIH R01 Budget Dashboard — 5-Year Breakdown', 'created_at': datetime.now(timezone.utc)}
    response = content_response(revision, version=4, view='embed')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=os.environ.get('PAGE_EMBED_BROWSER_CHANNEL') or None)
        page = browser.new_page(viewport={'width': 393, 'height': 852}, is_mobile=True, has_touch=True)
        page.route(f'{base}/api/pages/public/phone-fixture', lambda route: route.fulfill(json={
            'title': revision['title'], 'revision': 'r4', 'version': 4, 'updated_at': '2026-10-28T23:23:36.895000+00:00'}))
        page.route(f'{base}/api/pages/public/phone-fixture/content?revision=r4&view=embed', lambda route: route.fulfill(body=response.body, headers=dict(response.headers)))
        page.goto(f'{base}/e2e/fixtures/published-page.html')
        page.wait_for_function("parseFloat(document.querySelector('.page-published-content')?.style.height) > 1500")
        frame = page.get_by_title('Published page content').element_handle().content_frame()
        frame.wait_for_function('document.scrollingElement.scrollHeight <= innerHeight + 2')
        cdp = page.context.new_cdp_session(page)
        visited = set()
        for _ in range(12):
            cdp.send('Input.synthesizeScrollGesture', {'x': 195, 'y': 710, 'yDistance': -300, 'gestureSourceType': 'touch', 'speed': 700})
            for title in ('Yearly Totals', 'Full Budget Table (source values)', 'Calculated summary'):
                box = frame.get_by_role('heading', name=title, exact=True).bounding_box()
                if box and 0 <= box['y'] < 800:
                    visited.add(title)
                    if 'Full Budget' in title:
                        page.screenshot(path=str(tmp_path / 'reported-table.png'))
            assert frame.evaluate('scrollY') == 0
        assert len(visited) == 3
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(tmp_path / 'reported-bottom.png'))
        browser.close()
    print(f'Reported Page phone QA: {tmp_path}')
