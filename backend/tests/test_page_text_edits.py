"""Edit text: the owner fixes words and numbers on the page itself.

Support ticket: changing one heading on the NIH R01 Budget Dashboard (v5 -> v6)
took a chat round trip; the only manual option was ~160 lines of raw HTML.
"""
import pytest
from fastapi import HTTPException

from app.services import artifacts
from app.services.page_embedding import EMBED_SCRIPT, EMBED_STYLE
from app.services.page_text_edits import TextEdit, apply
from tests.test_artifacts import db as db, route_env as route_env, make
from tests.test_chat_routes import _auth

PAGE = """<!doctype html><html><head><title>NIH R01 Budget Dashboard</title></head><body>
<h1>NIH R01 Budget Dashbord</h1>
<p>Total request: <strong>$1.25M</strong> over five years.</p>
<table><tr><th>Category</th><th>Y1</th><th>Y2</th></tr>
<tr><td>Personnel</td><td>$124k</td><td>$124k</td></tr></table>
</body></html>"""


def test_a_typo_in_a_heading_is_fixed_in_place():
    html, notes = apply(PAGE, [TextEdit("h1", 0, "NIH R01 Budget Dashbord", "NIH R01 Budget Dashboard")])
    assert "<h1>NIH R01 Budget Dashboard</h1>" in html and notes == []


def test_a_number_inside_bold_keeps_its_formatting():
    html, notes = apply(PAGE, [TextEdit("p", 0, "Total request: $1.25M over five years.", "Total request: $1.27M over five years.")])
    assert "<strong>$1.27M</strong>" in html and notes == []


def test_a_change_across_styles_becomes_plain_text_and_says_so():
    html, notes = apply(PAGE, [TextEdit("p", 0, "Total request: $1.25M over five years.", "Requested in total: $1.3M.")])
    assert "<p>Requested in total: $1.3M.</p>" in html and "<strong>" not in html
    assert notes and "Formatting" in notes[0]


def test_the_occurrence_index_picks_the_right_one_of_two_identical_cells():
    html, _ = apply(PAGE, [TextEdit("td", 1, "$124k", "$142k")])
    assert "<td>$124k</td><td>$142k</td>" in html


def test_an_edit_whose_original_is_gone_is_refused_not_guessed():
    with pytest.raises(HTTPException) as err:
        apply(PAGE, [TextEdit("td", 0, "$999k", "$1k")])
    assert err.value.status_code == 409


@pytest.mark.parametrize("tag", ["script", "style", "a", "div"])
def test_only_text_blocks_can_be_edited(tag):
    with pytest.raises(HTTPException) as err:
        apply(PAGE, [TextEdit(tag, 0, "x", "y")])
    assert err.value.status_code == 422


def test_typed_markup_stays_text():
    html, _ = apply(PAGE, [TextEdit("h1", 0, "NIH R01 Budget Dashbord", "<img src=x onerror=alert(1)>")])
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_the_embed_frame_offers_edit_mode():
    assert "vandalizer:edit-mode" in EMBED_SCRIPT and "vandalizer:edit-collect" in EMBED_SCRIPT
    assert "plaintext-only" in EMBED_SCRIPT and ".vandalizer-editable" in EMBED_STYLE


@pytest.mark.asyncio
async def test_saving_edits_makes_a_new_version_and_leaves_the_published_link(client, db, route_env):
    doc = make(db, html=PAGE)
    doc = artifacts.publish(db, doc, doc["latest_revision"])
    published = doc["published_revision"]
    cookies, headers = _auth()
    response = await client.post(f'/api/pages/{doc["uuid"]}/text-edits', cookies=cookies, headers=headers, json={
        "base_revision": doc["latest_revision"],
        "edits": [{"tag": "h1", "index": 0, "original": "NIH R01 Budget Dashbord", "text": "NIH R01 Budget Dashboard"}],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == 2 and body["published_revision"] == published
    saved = artifacts.get(db, doc["uuid"])
    assert "NIH R01 Budget Dashboard</h1>" in artifacts.revision(saved)["html"]
    assert artifacts.revision(saved)["source"]["kind"] == "text_edit"
    assert artifacts.revision(saved, published)["html"].count("Dashbord") == 1
    # The same edit against the old base is refused: someone else saved first.
    stale = await client.post(f'/api/pages/{doc["uuid"]}/text-edits', cookies=cookies, headers=headers, json={
        "base_revision": published,
        "edits": [{"tag": "h1", "index": 0, "original": "NIH R01 Budget Dashbord", "text": "x"}],
    })
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_team_members_cannot_edit(client, db, route_env):
    doc = make(db, html=PAGE)
    route_env.user.user_id = "someone-else"
    cookies, headers = _auth()
    response = await client.post(f'/api/pages/{doc["uuid"]}/text-edits', cookies=cookies, headers=headers, json={
        "base_revision": doc["latest_revision"],
        "edits": [{"tag": "h1", "index": 0, "original": "NIH R01 Budget Dashbord", "text": "x"}],
    })
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_text_edit_keeps_the_owners_rename(client, db, route_env):
    doc = make(db, html=PAGE)
    doc = artifacts.rename(db, doc, "R01 budget for the dean")
    cookies, headers = _auth()
    response = await client.post(f'/api/pages/{doc["uuid"]}/text-edits', cookies=cookies, headers=headers, json={
        "base_revision": doc["latest_revision"],
        "edits": [{"tag": "h1", "index": 0, "original": "NIH R01 Budget Dashbord", "text": "NIH R01 Budget Dashboard"}],
    })
    assert response.status_code == 200, response.text
    assert artifacts.get(db, doc["uuid"])["title"] == "R01 budget for the dean"


def test_the_embed_script_has_no_raw_nul_character():
    # A NUL inside <script> is a parse error the browser rewrites to U+FFFD.
    assert "\x00" not in EMBED_SCRIPT
