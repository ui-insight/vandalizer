"""Page downloads use the visible revision's title, including Unicode names."""
from urllib.parse import unquote

import pytest

from app.routers.artifacts import content_response
from app.services import artifacts
from tests.test_artifacts import db as db, route_env as route_env


def download_name(response):
    return unquote(response.headers["content-disposition"].split("filename*=UTF-8''", 1)[1])


@pytest.mark.parametrize(("title", "expected"), [
    ("NIH R01 Budget Dashboard", "NIH R01 Budget Dashboard.html"),
    ("研究予算 — résumé", "研究予算 — résumé.html"),
    ('Budget "Final"\r\nReport', 'Budget "Final"\r\nReport.html'),
    ("Dashboard.html", "Dashboard.html"),
])
def test_page_title_is_encoded_as_a_download_filename(title, expected):
    response = content_response({"title": title, "html": "<h1>Budget</h1>"}, download=True)
    assert download_name(response) == expected
    assert response.headers["content-disposition"].startswith('attachment;')
    assert '\r' not in response.headers["content-disposition"]
    assert '\n' not in response.headers["content-disposition"]
    # Downloads receive the same standalone HTML document as the preview.
    assert b'<h1>Budget</h1>' in response.body
    assert response.body.startswith(b'<!DOCTYPE html>')


@pytest.mark.asyncio
async def test_downloads_name_the_selected_or_published_version_not_the_latest_draft(client, db, route_env):
    first = artifacts.create(db, 'testuser', 'NIH R01 Budget Dashboard', '<p>Original</p>', 'download')
    original = first['latest_revision']
    published = artifacts.publish(db, first, original)
    latest = artifacts.revise(db, published, 'Private updated budget', '<p>Draft</p>', original)

    original_url = f'/api/pages/{first["uuid"]}/revisions/{original}/content'
    private = await client.get(original_url, params={'download': 'true'})
    assert private.status_code == 200
    assert download_name(private) == 'NIH R01 Budget Dashboard.html'
    assert 'Original' in private.text

    draft = await client.get(f'/api/pages/{first["uuid"]}/revisions/{latest["latest_revision"]}/content', params={'download': 'true'})
    assert draft.status_code == 200
    assert download_name(draft) == 'Private updated budget.html'

    public = await client.get(f'/api/pages/public/{published["public_token"]}/content', params={'revision': original, 'download': 'true'})
    assert public.status_code == 200
    assert download_name(public) == 'NIH R01 Budget Dashboard.html'
    assert 'Private updated budget' not in public.headers['content-disposition']
    assert 'Original' in public.text

    preview = await client.get(original_url)
    assert preview.status_code == 200
    assert 'content-disposition' not in preview.headers
