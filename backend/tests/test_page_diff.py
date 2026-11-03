"""Compare two saved versions of a Page (support ticket: NIH R01 budget dashboard)."""
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

from app.services import artifacts
from app.services.page_diff import compare
from tests.test_artifacts import _auth, db as db, make, route_env as route_env  # noqa: F401

V1 = """<html><head><title>NIH R01 Budget Dashboard</title><style>.kpi{color:#1e3a8a}h2{font-size:20px}</style></head><body>
<h1>NIH R01 Budget Dashboard</h1>
<div class="kpi"><div class="label">Total budget</div><div class="value">$1,250,000</div></div>
<h2>Budget by year</h2>
<table><tr><th>Category</th><th>Y1</th><th>Y2</th></tr>
<tr><td>Personnel</td><td>$200,000</td><td>$150,000</td></tr>
<tr><td>Equipment</td><td>$15,000</td><td>$15,000</td></tr></table>
<p>Indirect costs are 21% of direct costs.</p>
<p>Prepared by OSP.</p></body></html>"""

V4 = (V1.replace("$1,250,000", "$1,255,000")
      .replace("<td>$15,000</td><td>$15,000</td>", "<td>$15,000</td><td>$20,000</td>")
      .replace("#1e3a8a", "#b8860b")
      .replace("<p>Prepared by OSP.</p>", "<h2>How to read this page</h2><p>Each bar shows one category.</p><p>Prepared by OSP.</p>"))


def test_changed_numbers_sections_and_design_are_grouped():
    diff = compare(V1, V4)
    assert [(n["label"], n["old"], n["new"]) for n in diff["numbers"]] == [
        ("Equipment · Y2", "$15,000", "$20,000"),
        ("Total budget", "$1,250,000", "$1,255,000"),  # a lone KPI value takes its label
    ]
    assert diff["sections_added"] == ["How to read this page"] and diff["sections_removed"] == []
    # A re-theme is one design line, not a content change.
    assert diff["design"] == ["Colours changed: #1e3a8a → #b8860b"]
    assert diff["summary"].startswith("2 figures changed (Equipment · Y2: $15,000 → $20,000, Total budget: $1,250,000 → $1,255,000)")
    assert "added section “How to read this page”" in diff["summary"] and diff["summary"].endswith("design changed")


def test_rows_text_and_removed_sections():
    v2 = (V1.replace("<tr><td>Equipment</td><td>$15,000</td><td>$15,000</td></tr>", "<tr><td>Travel</td><td>$8,000</td><td>$6,000</td></tr>")
          .replace("Prepared by OSP.", "Prepared by the Office of Sponsored Programs.")
          .replace("<h2>Budget by year</h2>", ""))
    diff = compare(V1, v2)
    labels = [t["label"] for t in diff["text"]]
    assert "Added row: Travel" in labels and "Removed row: Equipment" in labels
    assert any(t["old"] == "Prepared by OSP." and t["new"].startswith("Prepared by the Office") for t in diff["text"])
    assert diff["sections_removed"] == ["Budget by year"]


def test_identical_versions_have_no_changes():
    diff = compare(V1, V1)
    assert diff["summary"] == "No visible changes."
    assert not diff["numbers"] and not diff["text"] and not diff["design"]


def test_each_new_version_records_what_it_changed(db):  # noqa: F811
    first = make(db, html=V1)
    second = artifacts.revise(db, first, "Review", V4, first["latest_revision"])
    stored = artifacts.revision(second)
    assert stored["change_summary"].startswith("2 figures changed")
    listed = artifacts.metadata(second, owner=True)["revisions"]
    assert "change_summary" not in listed[0] and listed[1]["change_summary"] == stored["change_summary"]
    # Team members see one version and no edit history.
    assert all("change_summary" not in r for r in artifacts.metadata({**second, "team_id": "t"}, owner=False)["revisions"])


def test_versions_saved_before_summaries_get_one_once():
    doc = {"uuid": "p", "revisions": [{"uuid": "a", "html": V1}, {"uuid": "b", "html": V4}], "latest_revision": "b"}
    fake = SimpleNamespace(html_artifacts=MagicMock())
    artifacts.fill_change_summaries(fake, doc)
    assert doc["revisions"][1]["change_summary"].startswith("2 figures changed")
    query, update = fake.html_artifacts.update_one.call_args.args
    assert update == {"$set": {"revisions.$[r].change_summary": doc["revisions"][1]["change_summary"]}}
    assert fake.html_artifacts.update_one.call_args.kwargs == {"array_filters": [{"r.uuid": "b"}]}
    fake.html_artifacts.update_one.reset_mock()
    artifacts.fill_change_summaries(fake, doc)
    fake.html_artifacts.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_compare_route_is_owner_only(client, db, route_env):  # noqa: F811
    first = make(db, html=V1)
    second = artifacts.revise(db, first, "Review", V4, first["latest_revision"])
    cookies, headers = _auth()
    url = f"/api/pages/{first['uuid']}/compare"
    params = {"base": first["latest_revision"], "target": second["latest_revision"]}
    response = await client.get(url, params=params, cookies=cookies, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert (body["base"]["version"], body["target"]["version"]) == (1, 2)
    assert body["numbers"][0] == {"label": "Equipment · Y2", "old": "$15,000", "new": "$20,000", "section": "Budget by year"}
    other = make(db, key="theirs", owner="someone-else", html=V1)
    denied = await client.get(f"/api/pages/{other['uuid']}/compare", params={"base": other["latest_revision"], "target": other["latest_revision"]},
                              cookies=cookies, headers=headers)
    assert denied.status_code == 404


def _context(user_id="testuser"):
    return SimpleNamespace(deps=SimpleNamespace(user_id=user_id))


@pytest.mark.asyncio
async def test_chat_reads_old_versions_and_answers_what_changed(db):  # noqa: F811
    from app.services.chat_artifact_tools import compare_page_versions, get_html_artifact

    page = make(db, html=V1)
    for html in (V1.replace("$200,000", "$201,000"), V1.replace("$200,000", "$202,000"), V4):
        page = artifacts.revise(db, page, "Review", html, page["latest_revision"])
    with patch("app.services.chat_artifact_tools.get_sync_db", return_value=db):
        old = await get_html_artifact(_context(), page["uuid"], version=1)
        assert old["version"] == 1 and old["is_latest"] is False and "$1,250,000" in old["html"]
        diff = await compare_page_versions(_context(), page["uuid"], from_version=1, to_version=4)
        assert (diff["from_version"], diff["to_version"]) == (1, 4)
        assert ("Equipment · Y2", "$15,000", "$20,000") in [(n["label"], n["old"], n["new"]) for n in diff["numbers"]]
        assert [v["version"] for v in diff["versions_between"]] == [2, 3, 4]
        missing = await compare_page_versions(_context(), page["uuid"], from_version=1, to_version=9)
        assert "no version 9" in missing["error"]
        assert "do not own" in (await compare_page_versions(_context("intruder"), page["uuid"], 1))["error"]
