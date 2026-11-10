"""Uploading a plain JSON field list to create an extraction.

Support ticket: JSON that chat wrote for an award-setup extraction, pasted
into a text file and uploaded from "Name the extraction", failed with "Not a
Vandalizer export file (missing vandalizer_export flag)".
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_extraction_template_upload import _auth, _make_user, client  # noqa: F401


async def _post_import(client, body: bytes, **form):  # noqa: F811
    cookies, headers = _auth()
    ss = MagicMock(uuid="ss-new")
    importer = AsyncMock(return_value=ss)
    with (
        patch("app.dependencies.decode_token", return_value={"sub": "testuser", "type": "access"}),
        patch("app.dependencies.User") as MockUser,
        patch("app.services.export_import_service.import_search_set", importer),
        patch("app.routers.extractions._ss_response", AsyncMock(return_value={
            "id": "1", "title": "t", "uuid": "ss-new", "status": "active", "set_type": "extraction"})),
    ):
        MockUser.find_one = AsyncMock(return_value=_make_user())
        resp = await client.post(
            "/api/extractions/search-sets/import",
            files={"file": ("award.json", body, "application/json")},
            data=form, cookies=cookies, headers=headers,
        )
    return resp, importer


FIELDS = [{"name": "Award Number"}]


@pytest.mark.asyncio
async def test_extraction_upload_accepts_plain_json_under_the_typed_name(client):  # noqa: F811
    resp, importer = await _post_import(
        client, json.dumps(FIELDS).encode(), kind="extraction", title="  NSF GRANTED Extraction V2  ",
    )
    assert resp.status_code == 200
    args, kwargs = importer.await_args
    assert args[0] == FIELDS
    assert kwargs["accept_plain"] is True
    assert kwargs["title"] == "NSF GRANTED Extraction V2"


@pytest.mark.asyncio
async def test_other_kinds_do_not_accept_plain_json(client):  # noqa: F811
    _resp, importer = await _post_import(client, json.dumps(FIELDS).encode(), kind="prompt")
    assert importer.await_args.kwargs["accept_plain"] is False
    _resp, importer = await _post_import(client, json.dumps(FIELDS).encode())
    assert importer.await_args.kwargs["accept_plain"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    b"```json\n" + json.dumps(FIELDS).encode() + b"\n```",
    b"\xef\xbb\xbf```\n" + json.dumps(FIELDS).encode() + b"\n```\n",  # Notepad BOM
])
async def test_json_copied_with_its_chat_code_fence_still_imports(client, body):  # noqa: F811
    resp, importer = await _post_import(client, body, kind="extraction")
    assert resp.status_code == 200
    assert importer.await_args.args[0] == FIELDS


@pytest.mark.asyncio
async def test_text_that_is_not_json_is_still_invalid(client):  # noqa: F811
    resp, importer = await _post_import(client, b"Award Number, PI Name", kind="extraction")
    assert resp.status_code == 400 and resp.json()["detail"] == "Invalid JSON file"
    importer.assert_not_awaited()
