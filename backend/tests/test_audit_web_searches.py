"""Admin → Audit → Web searches: what was sent to the search provider.

Every search is recorded in web_search_usage (#web-search hardening); these
endpoints are the only way to read it without querying MongoDB.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_audit_routes import _auth, _make_user, client  # noqa: F401 (fixture)


def _row(**overrides):
    base = dict(
        id="r1", timestamp=datetime.datetime(2026, 10, 22, 15, 30, tzinfo=datetime.timezone.utc),
        feature="chat", user_id="ra-1", team_id="team-1", activity_id=None, provider="tavily",
        query="NSF equipment threshold", result_count=5, status="ok", error=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _model(rows, counts=None):
    """A WebSearchUsage stand-in recording the filter each call used."""
    model = MagicMock()
    seen: list[dict] = []

    def find(query):
        seen.append(query)
        cursor = MagicMock()
        cursor.count = AsyncMock(return_value=len(rows))
        chain = cursor.sort.return_value
        chain.skip.return_value.limit.return_value.to_list = AsyncMock(return_value=rows)
        chain.limit.return_value.to_list = AsyncMock(return_value=rows)
        return cursor

    model.find.side_effect = find
    agg = MagicMock()
    agg.to_list = AsyncMock(side_effect=list(counts or [[], []]))
    model.get_motor_collection.return_value.aggregate.return_value = agg
    model.seen = seen
    return model


async def _get(client, path, model, user):  # noqa: F811
    cookies, headers = _auth(user.user_id)
    with (
        patch("app.dependencies.decode_token", return_value={"sub": user.user_id, "type": "access"}),
        patch("app.dependencies.User") as MockUser,
        patch("app.models.web_search_usage.WebSearchUsage", model),
    ):
        MockUser.find_one = AsyncMock(return_value=user)
        return await client.get(path, cookies=cookies, headers=headers)


@pytest.mark.asyncio
async def test_lists_searches_with_counts_and_applies_filters(client):  # noqa: F811
    model = _model([_row()], counts=[[{"_id": "chat", "n": 4}, {"_id": "workflow", "n": 1}],
                                     [{"_id": "ok", "n": 4}, {"_id": "error", "n": 1}]])
    resp = await _get(client, "/api/audit/web-searches?feature=chat&status=ok&start_time=2026-10-01T00:00:00",
                      model, _make_user(is_admin=True))

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["entries"][0]["query"] == "NSF equipment threshold"
    assert body["entries"][0]["timestamp"].startswith("2026-10-22T15:30")
    assert body["by_feature"] == {"chat": 4, "workflow": 1}
    assert body["by_status"] == {"ok": 4, "error": 1}
    applied = model.seen[0]
    assert applied["feature"] == "chat" and applied["status"] == "ok"
    assert applied["timestamp"]["$gte"] == datetime.datetime(2026, 10, 1)


@pytest.mark.asyncio
async def test_staff_can_read_but_a_member_cannot(client):  # noqa: F811
    assert (await _get(client, "/api/audit/web-searches", _model([]), _make_user(is_staff=True))).status_code == 200
    assert (await _get(client, "/api/audit/web-searches", _model([]), _make_user())).status_code == 403


@pytest.mark.asyncio
async def test_a_bad_time_is_a_400(client):  # noqa: F811
    resp = await _get(client, "/api/audit/web-searches?end_time=yesterday", _model([]), _make_user(is_admin=True))
    assert resp.status_code == 400 and "end_time" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_export_writes_every_column(client):  # noqa: F811
    model = _model([_row(status="error", error="Web search provider returned HTTP 401.", result_count=0)])
    resp = await _get(client, "/api/audit/web-searches/export?status=error", model, _make_user(is_admin=True))

    assert resp.status_code == 200
    lines = resp.text.strip().splitlines()
    assert lines[0] == "timestamp,feature,user_id,team_id,activity_id,provider,query,result_count,status,error"
    assert "NSF equipment threshold,0,error,Web search provider returned HTTP 401." in lines[1]
    assert model.seen[0] == {"status": "error"}
