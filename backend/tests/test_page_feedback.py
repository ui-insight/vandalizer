"""Viewers can ask a Page's owner about it; the owner answers in Vandalizer.

Support ticket: team members and public-link viewers (grant admins, PIs,
sponsors) had no way to ask a question or flag a figure, the owner had nowhere
to see feedback, and a public page didn't say who owned it.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from app.services import artifacts, page_feedback
from app.services.access_control import TeamAccessContext
from tests.test_artifacts import QueryCollection, db as db, route_env as route_env, make
from tests.test_chat_routes import _auth

PAGE = """<main><h1>NIH R01 Budget</h1><h2>Equipment</h2>
<table><tr><th>Category</th><th>Y1</th><th>Y2</th></tr>
<tr><td>Equipment</td><td>$15k</td><td>$20k</td></tr>
<tr><td>Personnel</td><td>$250k</td><td>$124k</td></tr></table></main>"""


@pytest.fixture
def feedback_db(db):
    db.user.docs.append({"user_id": "testuser", "name": "Jane Doe", "organization_id": "osp"})
    db.organization.docs += [
        {"uuid": "uidaho", "name": "University of Idaho", "parent_id": None},
        {"uuid": "osp", "name": "Office of Sponsored Programs", "parent_id": "uidaho"},
    ]
    db.html_artifacts.update_one = QueryCollection.update_one.__get__(db.html_artifacts)
    return db


@pytest.fixture
def notify():
    with patch("app.services.notification_service.create_notification", AsyncMock()) as create, \
         patch("app.services.email_service.send_email", AsyncMock(return_value=True)) as send:
        yield SimpleNamespace(create=create, send=send)


def test_anchors_list_sections_and_figure_cells():
    anchors = page_feedback.anchors(PAGE)
    labels = [a["label"] for a in anchors]
    assert "Section: Equipment" in labels
    assert "Equipment · Y2 · $20k" in labels
    assert "Personnel · Y1 · $250k" in labels
    assert not any("Category" in label for label in labels)  # header row isn't a figure


def test_mark_highlights_exactly_the_anchored_cell():
    anchor = next(a for a in page_feedback.anchors(PAGE) if a["label"] == "Equipment · Y2 · $20k")
    soup = BeautifulSoup(PAGE, "html.parser")
    page_feedback.mark(soup, anchor["id"])
    marked = soup.find(id="vandalizer-feedback-mark")
    assert marked.get_text() == "$20k" and "outline" in marked["style"]


def test_shared_by_names_the_owner_and_their_organization(feedback_db):
    doc = make(feedback_db, html=PAGE)
    assert page_feedback.shared_by(feedback_db, doc) == (
        "Shared by Jane Doe, University of Idaho Office of Sponsored Programs")
    doc["sharing_contact"] = {"hide_owner_name": True, "contact_label": "OSP pre-award team"}
    assert page_feedback.shared_by(feedback_db, doc) == "Shared by OSP pre-award team"
    doc["sharing_contact"] = {"hide_owner_name": True}
    assert page_feedback.shared_by(feedback_db, doc) is None


@pytest.mark.asyncio
async def test_a_team_member_asks_and_the_owner_is_notified_with_a_link_to_the_spot(client, feedback_db, route_env, notify):
    doc = make(feedback_db, html=PAGE)
    cookies, headers = _auth()
    route_env.access.return_value = TeamAccessContext(team_uuids={"team-a"})
    assert (await client.put(f'/api/pages/{doc["uuid"]}/team', json={"team_id": "team-a"},
                             cookies=cookies, headers=headers)).status_code == 200
    route_env.user.user_id = "QA1"
    route_env.user.name = "Pat Admin"
    info = (await client.get(f'/api/pages/{doc["uuid"]}')).json()
    assert info["shared_by"] == "Shared by Jane Doe, University of Idaho Office of Sponsored Programs"
    anchors = (await client.get(f'/api/pages/{doc["uuid"]}/questions/anchors')).json()["anchors"]
    spot = next(a for a in anchors if a["label"] == "Equipment · Y2 · $20k")
    response = await client.post(f'/api/pages/{doc["uuid"]}/questions', cookies=cookies, headers=headers,
                                 json={"message": "Is Y2 equipment $20k or $15k? The budget says $15k.", "anchor_id": spot["id"]})
    assert response.status_code == 200, response.text
    question = response.json()
    assert question["anchor_label"] == "Equipment · Y2 · $20k" and question["status"] == "open"
    owner_id, kind, title = notify.create.await_args.args
    assert (owner_id, kind, title) == ("testuser", "page_question", "Question on Review")
    assert notify.create.await_args.kwargs["link"] == f'/pages/{doc["uuid"]}?question={question["uuid"]}'
    assert "Pat Admin · about Equipment · Y2 · $20k" in notify.create.await_args.kwargs["body"]
    # The owner's link opens the page with that cell highlighted.
    route_env.user.user_id = "testuser"
    content = await client.get(f'/api/pages/{doc["uuid"]}/revisions/{doc["latest_revision"]}/content?mark={spot["id"]}')
    assert 'id="vandalizer-feedback-mark"' in content.text


@pytest.mark.asyncio
async def test_the_owner_answers_a_team_member_in_their_bell_and_can_show_it_on_the_page(client, feedback_db, route_env, notify):
    doc = make(feedback_db, html=PAGE)
    revision = artifacts.revision(doc)
    item = page_feedback.create(feedback_db, doc, revision, message="Where does $20k come from?", anchor_id=None,
                                asker={"kind": "user", "user_id": "QA1", "name": "Pat Admin"})
    cookies, headers = _auth()
    listed = (await client.get(f'/api/pages/{doc["uuid"]}/questions')).json()
    assert listed[0]["asker"]["name"] == "Pat Admin" and listed[0]["status"] == "open"
    assert (await client.get(f'/api/pages/{doc["uuid"]}')).json()["open_questions"] == 1
    response = await client.post(f'/api/pages/{doc["uuid"]}/questions/{item["uuid"]}/answer', cookies=cookies, headers=headers,
                                 json={"text": "Revised quote from the vendor, Nov 1.", "show_on_page": True})
    assert response.status_code == 200 and response.json()["status"] == "answered"
    recipient, kind, _title = notify.create.await_args.args
    assert (recipient, kind) == ("QA1", "page_question_answered")
    notify.send.assert_not_awaited()
    notes = (await client.get(f'/api/pages/{doc["uuid"]}')).json()["notes"]
    assert notes[0]["answer"] == "Revised quote from the vendor, Nov 1."


@pytest.mark.asyncio
async def test_owners_use_request_changes_not_questions(client, feedback_db, route_env, notify):
    doc = make(feedback_db, html=PAGE)
    cookies, headers = _auth()
    response = await client.post(f'/api/pages/{doc["uuid"]}/questions', cookies=cookies, headers=headers, json={"message": "Hi"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_public_questions_are_off_until_the_owner_allows_them(client, feedback_db, route_env, notify):
    doc = artifacts.publish(feedback_db, make(feedback_db, html=PAGE), make(feedback_db, html=PAGE)["latest_revision"])
    token = doc["public_token"]
    info = (await client.get(f"/api/pages/public/{token}")).json()
    assert info["questions_enabled"] is False
    assert info["shared_by"] == "Shared by Jane Doe, University of Idaho Office of Sponsored Programs"
    body = {"message": "Is the equipment figure final?", "email": "pi@wsu.edu"}
    # CSRF stays on for the public form: every response, the public page's
    # included, sets the token cookie and the page's API client sends it back.
    cookies, headers = _auth()

    async def ask(payload):
        return await client.post(f"/api/pages/public/{token}/questions", json=payload, cookies=cookies, headers=headers)

    assert (await ask(body)).status_code == 404

    settings = await client.patch(f'/api/pages/{doc["uuid"]}/question-settings', cookies=cookies, headers=headers,
                                  json={"public_questions": True})
    assert settings.json()["public_questions"] is True
    assert (await client.get(f"/api/pages/public/{token}")).json()["questions_enabled"] is True
    assert (await ask({**body, "email": "not-an-email"})).status_code == 422
    assert (await ask(body)).status_code == 200
    assert notify.create.await_args.args[1] == "page_question"
    assert "pi@wsu.edu" in notify.create.await_args.kwargs["body"]
    # A filled honeypot looks accepted and stores nothing.
    assert (await ask({**body, "website": "spam"})).json() == {"ok": True}
    assert len(feedback_db.page_feedback.docs) == 1

    question = feedback_db.page_feedback.docs[0]
    response = await client.post(f'/api/pages/{doc["uuid"]}/questions/{question["uuid"]}/answer', cookies=cookies,
                                 headers=headers, json={"text": "Yes, final as of Nov 1."})
    assert response.status_code == 200
    to, subject, html = notify.send.await_args.args
    assert to == "pi@wsu.edu" and subject == "Answer to your question about Review"
    assert f"/a/{token}" in html and "Yes, final as of Nov 1." in html


def test_public_question_text_is_escaped_in_the_answer_email():
    from app.services.email_service import page_question_answered_email

    _subject, html = page_question_answered_email("Budget", "<script>x</script>", "<b>ok</b>", None)
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html
