"""Refreshing a KB's web sources all at once and on a schedule.

Support ticket: a URL source is fetched once and never checked again, so a
revised government or sponsor policy page keeps answering from its old text.
Per-source Refresh existed (#726); this adds refresh-all, a per-KB automatic
interval, and makes a crashed or abandoned refresh recoverable instead of
leaving the source "processing" — and so exempt from every later refresh.
"""

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import kb_url_refresh as r

# The routes and refresh_all read the real clock, so the fixtures do too.
NOW = datetime.datetime.now(tz=datetime.timezone.utc)
DAY = datetime.timedelta(days=1)


def _src(uuid="s1", *, status="ready", checked_days_ago=10.0, queued_minutes_ago=None, **kw):
    checked = NOW - datetime.timedelta(days=checked_days_ago)
    s = SimpleNamespace(
        uuid=uuid, knowledge_base_uuid="kb-1", source_type="url", url=f"https://example.gov/{uuid}",
        status=status, created_at=checked - DAY, processed_at=None,
        last_refresh_attempted_at=checked, chunk_count=3,
        refresh_queued_at=NOW - datetime.timedelta(minutes=queued_minutes_ago) if queued_minutes_ago is not None else None,
        save=AsyncMock(),
    )
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _find(items):
    q = MagicMock()
    q.to_list = AsyncMock(return_value=items)
    return q


class TestRules:
    def test_due_by_interval(self):
        assert r.is_due(_src(checked_days_ago=8), r.INTERVALS["weekly"], NOW)
        assert not r.is_due(_src(checked_days_ago=3), r.INTERVALS["weekly"], NOW)

    def test_a_just_queued_source_is_in_flight_even_if_last_checked_long_ago(self):
        s = _src(status="pending", checked_days_ago=14, queued_minutes_ago=1)
        assert r.is_in_flight(s, NOW)
        assert not r.is_refreshable(s, NOW)

    def test_an_abandoned_refresh_is_refreshable_again(self):
        s = _src(status="processing", checked_days_ago=14, queued_minutes_ago=180)
        assert not r.is_in_flight(s, NOW)
        assert r.is_refreshable(s, NOW)

    @pytest.mark.parametrize("kw", [{"source_type": "document"}, {"url": None}, {"status": "skipped"}])
    def test_not_refreshable(self, kw):
        assert not r.is_refreshable(_src(**kw), NOW)


class TestScheduledPass:
    @pytest.mark.asyncio
    async def test_queues_only_due_sources_of_kbs_with_an_interval(self):
        kb = SimpleNamespace(uuid="kb-1", url_refresh_interval="weekly", status="ready", save=AsyncMock())
        due = _src("due", checked_days_ago=8)
        fresh = _src("fresh", checked_days_ago=2)
        busy = _src("busy", status="processing", checked_days_ago=9, queued_minutes_ago=5)
        with patch.object(r.KnowledgeBase, "find", return_value=_find([kb])) as kb_find, \
             patch.object(r.KnowledgeBaseSource, "find", return_value=_find([due, fresh, busy])), \
             patch("app.tasks.kb_validation_tasks.refresh_url_source_task.apply_async") as dispatch:
            result = await r.refresh_due_sources(NOW)
        assert kb_find.call_args.args[0] == {"url_refresh_interval": {"$in": ["daily", "weekly", "monthly"]}}
        assert result == {"knowledge_bases": 1, "queued": 1}
        dispatch.assert_called_once()
        assert dispatch.call_args.kwargs["args"][:2] == ("kb-1", "due")
        # The task carries the stamp it was queued under.
        assert dispatch.call_args.kwargs["args"][2] == due.refresh_queued_at.isoformat()
        assert due.status == "pending" and due.refresh_queued_at is not None
        # A scheduled pass leaves the KB's status to the refresh tasks.
        kb.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_one_broken_kb_does_not_stop_the_rest(self):
        bad = SimpleNamespace(uuid="kb-bad", url_refresh_interval="nonsense")
        good = SimpleNamespace(uuid="kb-1", url_refresh_interval="daily", save=AsyncMock())
        with patch.object(r.KnowledgeBase, "find", return_value=_find([bad, good])), \
             patch.object(r.KnowledgeBaseSource, "find", return_value=_find([_src(checked_days_ago=2)])), \
             patch("app.tasks.kb_validation_tasks.refresh_url_source_task.apply_async") as dispatch:
            result = await r.refresh_due_sources(NOW)
        assert result["queued"] == 1
        dispatch.assert_called_once()


class TestRefreshAll:
    @pytest.mark.asyncio
    async def test_queues_everything_not_in_flight_staggered(self):
        kb = SimpleNamespace(uuid="kb-1", status="ready", save=AsyncMock())
        a, b = _src("a", checked_days_ago=0.1), _src("b")
        busy = _src("busy", status="pending", queued_minutes_ago=1)
        with patch.object(r.KnowledgeBaseSource, "find", return_value=_find([a, b, busy])), \
             patch("app.tasks.kb_validation_tasks.refresh_url_source_task.apply_async") as dispatch:
            result = await r.refresh_all(kb)
        assert result == {"queued": 2, "in_progress": 1}
        assert [c.kwargs["countdown"] for c in dispatch.call_args_list] == [0, r.STAGGER_SECONDS]
        assert kb.status == "building"
        # Stamped with when each task is due to start, not when it was queued.
        assert (b.refresh_queued_at - a.refresh_queued_at).total_seconds() == r.STAGGER_SECONDS


class TestTaskDedupe:
    @pytest.mark.asyncio
    async def test_a_superseded_task_does_nothing(self):
        from app.tasks import kb_validation_tasks as t

        src = _src(status="pending", queued_minutes_ago=0)
        older = (src.refresh_queued_at - datetime.timedelta(hours=3)).isoformat()
        with patch("app.database.init_db", AsyncMock()), \
             patch("app.models.knowledge.KnowledgeBase", **{"find_one": AsyncMock(return_value=SimpleNamespace(uuid="kb-1"))}), \
             patch("app.models.knowledge.KnowledgeBaseSource", **{"find_one": AsyncMock(return_value=src)}), \
             patch("app.services.knowledge_service.refresh_url_source", AsyncMock()) as refresh:
            out = await t._refresh_url_source_async("kb-1", "s1", older)
        assert out["reason"] == "superseded"
        refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_transient_error_is_left_to_celery_retry(self):
        from app.tasks import kb_validation_tasks as t
        from app.tasks import TRANSIENT_EXCEPTIONS

        transient = TRANSIENT_EXCEPTIONS[0]
        src = _src(status="processing")
        with patch("app.database.init_db", AsyncMock()), \
             patch("app.models.knowledge.KnowledgeBase", **{"find_one": AsyncMock(return_value=SimpleNamespace(uuid="kb-1"))}), \
             patch("app.models.knowledge.KnowledgeBaseSource", **{"find_one": AsyncMock(return_value=src)}), \
             patch("app.services.knowledge_service.refresh_url_source", AsyncMock(side_effect=transient("blip"))):
            with pytest.raises(transient):
                await t._refresh_url_source_async("kb-1", "s1")


class TestTaskRecovers:
    @pytest.mark.asyncio
    async def test_a_crashed_refresh_does_not_leave_the_source_processing(self):
        from app.tasks import kb_validation_tasks as t

        kb = SimpleNamespace(uuid="kb-1")
        src = _src(status="processing")
        with patch("app.database.init_db", AsyncMock()), \
             patch("app.models.knowledge.KnowledgeBase", **{"find_one": AsyncMock(return_value=kb)}), \
             patch("app.models.knowledge.KnowledgeBaseSource", **{"find_one": AsyncMock(return_value=src)}), \
             patch("app.services.knowledge_service.refresh_url_source", AsyncMock(side_effect=RuntimeError("db hiccup"))), \
             patch("app.services.knowledge_service.recalculate_stats", AsyncMock()) as recalc:
            out = await t._refresh_url_source_async("kb-1", "s1")
        assert out["refreshed"] is False
        assert src.status == "ready"  # it still has its chunks
        assert "db hiccup" in src.error_message
        recalc.assert_awaited_once()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

from tests.test_knowledge_routes import _auth, _make_user, _mock_kb  # noqa: E402


def _logged_in():
    user = _make_user()
    return (
        patch("app.dependencies.decode_token", return_value={"sub": "user1", "type": "access"}),
        patch("app.dependencies.User", **{"find_one": AsyncMock(return_value=user)}),
        patch("app.routers.knowledge.organization_service", **{"get_user_org_ancestry": AsyncMock(return_value=[])}),
    )


class TestRoutes:
    @pytest.mark.asyncio
    async def test_refresh_web_sources_queues_all(self, client):
        cookies, headers = _auth()
        kb = _mock_kb()
        a, b, c = _logged_in()
        with a, b, c, \
             patch("app.routers.knowledge.svc") as mock_svc, \
             patch("app.services.kb_url_refresh.refresh_all", AsyncMock(return_value={"queued": 4, "in_progress": 1})) as refresh_all:
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            resp = await client.post("/api/knowledge/kb-uuid-1/refresh-web-sources", cookies=cookies, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "queued": 4, "in_progress": 1}
        refresh_all.assert_awaited_once_with(kb)

    @pytest.mark.asyncio
    async def test_single_refresh_refuses_a_source_already_queued(self, client):
        cookies, headers = _auth()
        kb = _mock_kb()
        src = _src("src-1", status="pending", queued_minutes_ago=1)
        a, b, c = _logged_in()
        with a, b, c, \
             patch("app.routers.knowledge.svc") as mock_svc, \
             patch("app.models.knowledge.KnowledgeBaseSource.find_one", AsyncMock(return_value=src)), \
             patch("app.tasks.kb_validation_tasks.refresh_url_source_task.delay") as delay:
            mock_svc.get_knowledge_base = AsyncMock(return_value=kb)
            resp = await client.post("/api/knowledge/kb-uuid-1/source/src-1/refresh", cookies=cookies, headers=headers)
        assert resp.status_code == 409
        delay.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", ["weekly", "off"])
    async def test_update_passes_the_interval(self, client, value):
        cookies, headers = _auth()
        a, b, c = _logged_in()
        with a, b, c, patch("app.routers.knowledge.svc") as mock_svc:
            mock_svc.get_knowledge_base = AsyncMock(return_value=_mock_kb())
            mock_svc.update_knowledge_base = AsyncMock(return_value=_mock_kb())
            resp = await client.post(
                "/api/knowledge/kb-uuid-1/update", json={"url_refresh_interval": value},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 200
        assert mock_svc.update_knowledge_base.await_args.kwargs["url_refresh_interval"] == value

    @pytest.mark.asyncio
    async def test_update_rejects_an_unknown_interval(self, client):
        cookies, headers = _auth()
        a, b, c = _logged_in()
        with a, b, c:
            resp = await client.post(
                "/api/knowledge/kb-uuid-1/update", json={"url_refresh_interval": "hourly"},
                cookies=cookies, headers=headers,
            )
        assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("value, stored", [("monthly", "monthly"), ("off", None)])
async def test_service_stores_the_interval(value, stored):
    from app.services import knowledge_service

    kb = SimpleNamespace(uuid="kb-1", title="T", url_refresh_interval="daily", organization_ids=[], tags=[],
                         save=AsyncMock())
    with patch.object(knowledge_service, "get_knowledge_base", AsyncMock(return_value=kb)):
        await knowledge_service.update_knowledge_base("kb-1", MagicMock(), url_refresh_interval=value)
    assert kb.url_refresh_interval == stored
