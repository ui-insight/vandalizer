from datetime import datetime, timezone

import pytest
from bs4 import BeautifulSoup

from app.services import artifacts
from app.services.page_printing import render_page
from tests.test_artifacts import db as db, route_env as route_env, make


CHART_HTML = """<html><head><style>
body{font:16px Arial;margin:24px;color:#172554;background:#fff}
h1{font-size:26px}h2{font-size:20px}figure{margin:20px 0}
.bar{height:24px;margin:6px 0;background:#2563eb}
.category{background:#059669}
.next-page{break-before:page}
</style></head><body><h1>NIH R01 Budget Dashboard</h1><h2>Yearly Totals</h2>
<figure><div>Y1 · $121,600</div><div class="bar" style="width:65%"></div>
<div>Y2 · $121,600</div><div class="bar" style="width:65%"></div>
<div>Y3 · $130,000</div><div class="bar" style="width:70%"></div>
<div>Y4 · $135,000</div><div class="bar" style="width:73%"></div>
<div>Y5 · $140,000</div><div class="bar" style="width:76%"></div></figure>
<h2>Category Breakdown</h2><figure>
<div>Salaries · $50,000</div><div class="bar category" style="width:50%"></div>
<div>Fringe · $15,000</div><div class="bar category" style="width:15%"></div>
<div>F&amp;A · $41,600</div><div class="bar category" style="width:42%"></div></figure>
<section class="next-page"><h2>Budget notes</h2><p>Second page content remains separate from the version footer.</p></section>
</body></html>"""


def revision():
    html, _ = artifacts.clean_html(CHART_HTML, "NIH R01 Budget Dashboard")
    return {"html": html, "title": "NIH R01 Budget Dashboard", "created_at": datetime(2026, 10, 29, 12, 30, tzinfo=timezone.utc)}


def test_existing_saved_source_gets_print_support_without_mutation():
    rev = revision()
    original = rev["html"]
    html, csp = render_page(rev, 4)
    soup = BeautifulSoup(html, "html.parser")
    assert rev["html"] == original
    assert "print-color-adjust: exact !important" in soup.select_one("#vandalizer-print-style").text
    assert len(soup.select(".bar")) == 8
    assert soup.select_one("#vandalizer-print-footer")["content"] == "NIH R01 Budget Dashboard · Version 4 · Saved 2026-10-29 12:30 UTC"
    assert csp == artifacts.CONTENT_CSP
    assert not soup.select("script, button")


@pytest.mark.parametrize("view", ["full", "print"])
def test_print_view_only_permits_the_trusted_print_script(view):
    rev = revision()
    rev["title"] = '</style><img src=x onerror="steal()">'
    html, csp = render_page(rev, 4, view)
    soup = BeautifulSoup(html, "html.parser")
    script, = soup.select("script")
    assert f"script-src 'nonce-{script['nonce']}'" in csp
    assert "sandbox allow-scripts allow-modals;" in csp and "allow-same-origin" not in csp
    assert "connect-src 'none'" in csp and "default-src 'none'" in csp
    assert soup.select_one('meta[http-equiv="Content-Security-Policy"]')["content"] == csp
    assert soup.button.text == "Print / Save as PDF"
    assert ("addEventListener('load'" in script.text) == (view == "print")
    assert not soup.select("img")
    assert soup.select_one("#vandalizer-print-footer")["content"] == f'{rev["title"]} · Version 4 · Saved 2026-10-29 12:30 UTC'
    assert render_page(rev, 4, view)[1] != csp  # New nonce on every response.


async def test_print_routes_use_selected_version_and_enforce_access(client, db, route_env):
    doc = make(db, html=CHART_HTML)
    first = doc["latest_revision"]
    doc = artifacts.revise(db, doc, "Shared version", CHART_HTML, first)
    shared = doc["latest_revision"]
    doc = artifacts.publish(db, doc, shared)
    token = doc["public_token"]
    uid = doc["uuid"]
    artifacts.share_team(db, doc, "team-a", shared)
    doc = artifacts.get(db, uid)
    artifacts.revise(db, doc, "Private draft", "<p>Secret</p>", shared)

    for query in ("view=full", "view=print", "download=true&view=print"):
        response = await client.get(f"/api/pages/public/{token}/content?revision={shared}&{query}")
        assert response.status_code == 200
        assert "Shared version · Version 2 · Saved" in response.text
        assert "Private draft" not in response.text and "Secret" not in response.text
        if "download" in query:
            assert "Content-Disposition" in response.headers
            assert "<script" not in response.text
    assert (await client.get(f"/api/pages/public/{token}/content?revision={first}&view=print")).status_code == 409
    private = await client.get(f"/api/pages/{uid}/revisions/{first}/content?view=print")
    assert "Review · Version 1 · Saved" in private.text
    route_env.user.user_id = "other-user"
    assert (await client.get(f"/api/pages/{uid}/revisions/{first}/content?view=print")).status_code == 404
    from app.services.access_control import TeamAccessContext
    route_env.access.return_value = TeamAccessContext(team_uuids={"team-a"})
    assert (await client.get(f"/api/pages/{uid}/revisions/{first}/content?view=print")).status_code == 404
    team = await client.get(f"/api/pages/{uid}/revisions/{shared}/content?view=print")
    assert team.status_code == 200 and "Shared version · Version 2 · Saved" in team.text
