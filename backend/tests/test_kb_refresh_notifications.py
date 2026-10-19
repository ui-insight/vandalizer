"""A scheduled web-source refresh tells the KB's managers what happened.

Support ticket: a KB on an automatic refresh interval re-indexed changed pages,
and kept answering from the old text of pages that stopped loading, with no
signal to its owner or editors. Changed and newly failing sources now notify
the owner and the team's owners/admins; unchanged pages, already-failing
sources and hand-started refreshes stay quiet.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import kb_refresh_notifications as n
from app.utils import kb_source_currency as currency


def _kb(**kw):
    base = {"uuid": "kb-1", "title": "NSF PAPPG", "user_id": "owner", "team_id": None, "shared_with_team": False}
    base.update(kw)
    return SimpleNamespace(**base)


def _source(**kw):
    base = {
        "uuid": "s1", "custom_name": None, "url_title": "Chapter II", "url": "https://nsf.gov/ch2",
        "status": "ready", "chunk_count": 4, "content": "old line\nkept line",
        "last_refresh_outcome": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


class TestSummary:
    def test_counts_lines_and_quotes_the_first_new_one(self):
        out = n.summarize_change("a\nb\nc", "a\nc\nThe cap is now $100,000.\nd", "Old", "New")
        assert "Title changed from “Old” to “New”." in out
        assert "2 lines added, 1 removed" in out
        assert "“The cap is now $100,000.”" in out

    def test_reformatted_text_says_so(self):
        assert "reordered or reformatted" in n.summarize_change("a\nb", "b\n  a")

    def test_long_first_line_is_clipped(self):
        out = n.summarize_change("", "x" * 500)
        assert "…" in out and "x" * 161 not in out


class TestRecipients:
    @pytest.mark.asyncio
    async def test_private_kb_is_owner_only(self):
        assert await n.kb_managers(_kb()) == ["owner"]

    @pytest.mark.asyncio
    async def test_team_kb_adds_team_owners_and_admins_once(self):
        from app.models.team import Team, TeamMembership

        team = SimpleNamespace(id="team-oid")
        members = MagicMock()
        members.to_list = AsyncMock(return_value=[
            SimpleNamespace(user_id="owner"), SimpleNamespace(user_id="admin-1"),
        ])
        with patch.object(Team, "find_one", AsyncMock(return_value=team)), \
             patch.object(TeamMembership, "find", return_value=members) as find:
            out = await n.kb_managers(_kb(team_id="team-uuid", shared_with_team=True))
        assert out == ["owner", "admin-1"]
        assert find.call_args.args[0] == {"team": "team-oid", "role": {"$in": ["admin", "owner"]}}


async def _emit(coro_fn, *args, managers=("owner", "admin-1"), **kw):
    create = AsyncMock()
    with patch("app.services.notification_service.create_notification", create), \
         patch.object(n, "kb_managers", AsyncMock(return_value=list(managers))):
        await coro_fn(*args, **kw)
    return create


class TestNotifications:
    @pytest.mark.asyncio
    async def test_changed_source_notifies_every_manager_coalesced_per_kb(self):
        create = await _emit(n.notify_source_changed, _kb(), _source(), "3 lines added.")
        assert [c.kwargs["user_id"] for c in create.await_args_list] == ["owner", "admin-1"]
        kw = create.await_args.kwargs
        assert kw["kind"] == "kb_source_updated"
        assert kw["title"] == "Web source updated: NSF PAPPG"
        assert "“Chapter II” changed" in kw["body"] and "3 lines added." in kw["body"]
        assert kw["coalesce_key"] == "kb_source_updated:kb-1"
        assert kw["link"] == "/?mode=knowledge"

    @pytest.mark.asyncio
    async def test_new_failure_says_previous_text_is_kept(self):
        create = await _emit(
            n.notify_source_refresh_failed, _kb(), _source(), "HTTP 404", previous_outcome=currency.OUTCOME_UNCHANGED,
        )
        kw = create.await_args.kwargs
        assert kw["kind"] == "kb_source_refresh_failed"
        assert kw["severity"] == "warning"
        assert "previous text is still being used" in kw["body"] and "HTTP 404" in kw["body"]

    @pytest.mark.asyncio
    async def test_failure_without_indexed_text_says_so(self):
        create = await _emit(
            n.notify_source_refresh_failed, _kb(), _source(status="error", chunk_count=0), "timeout",
            previous_outcome=None,
        )
        assert "no indexed text" in create.await_args.kwargs["body"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("outcome", sorted(n.FAILED_OUTCOMES))
    async def test_an_already_failing_source_does_not_ring_again(self, outcome):
        create = await _emit(n.notify_source_refresh_failed, _kb(), _source(), "HTTP 404", previous_outcome=outcome)
        create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_never_raises(self):
        with patch.object(n, "kb_managers", AsyncMock(side_effect=RuntimeError("db down"))):
            await n.notify_source_changed(_kb(), _source(), "x")


async def _run_task(source, refresh, *, scheduled):
    from app.tasks import kb_validation_tasks as t

    kb = _kb()
    changed, failed = AsyncMock(), AsyncMock()
    with patch("app.database.init_db", AsyncMock()), \
         patch("app.models.knowledge.KnowledgeBase", **{"find_one": AsyncMock(return_value=kb)}), \
         patch("app.models.knowledge.KnowledgeBaseSource", **{"find_one": AsyncMock(return_value=source)}), \
         patch("app.services.knowledge_service.refresh_url_source", AsyncMock(side_effect=refresh)), \
         patch("app.services.knowledge_service.recalculate_stats", AsyncMock()), \
         patch.object(n, "notify_source_changed", changed), \
         patch.object(n, "notify_source_refresh_failed", failed):
        await t._refresh_url_source_async("kb-1", "s1", None, scheduled)
    return changed, failed


def _outcome(outcome, *, reason=None, content=None, title=None):
    async def refresh(source, kb):
        source.last_refresh_outcome = outcome
        if content is not None:
            source.content = content
        if title is not None:
            source.url_title = title
        return reason
    return refresh


class TestTaskWiring:
    @pytest.mark.asyncio
    async def test_scheduled_change_summarizes_against_the_previous_text(self):
        changed, failed = await _run_task(
            _source(), _outcome(currency.OUTCOME_REFRESHED, content="kept line\nnew rule", title="Chapter II (rev)"),
            scheduled=True,
        )
        failed.assert_not_awaited()
        summary = changed.await_args.args[2]
        assert "1 line added, 1 removed" in summary and "“new rule”" in summary
        assert "Chapter II (rev)" in summary

    @pytest.mark.asyncio
    async def test_scheduled_failure_passes_the_outcome_from_before_the_refresh(self):
        source = _source(last_refresh_outcome=currency.OUTCOME_UNCHANGED)
        changed, failed = await _run_task(
            source, _outcome(currency.OUTCOME_RETRIEVAL_FAILED, reason="HTTP 503"), scheduled=True,
        )
        changed.assert_not_awaited()
        assert failed.await_args.args[2] == "HTTP 503"
        assert failed.await_args.kwargs["previous_outcome"] == currency.OUTCOME_UNCHANGED

    @pytest.mark.asyncio
    async def test_scheduled_unchanged_page_is_quiet(self):
        changed, failed = await _run_task(_source(), _outcome(currency.OUTCOME_UNCHANGED), scheduled=True)
        changed.assert_not_awaited()
        failed.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("outcome,reason", [
        (currency.OUTCOME_REFRESHED, None), (currency.OUTCOME_RETRIEVAL_FAILED, "HTTP 404"),
    ])
    async def test_a_hand_started_refresh_is_quiet(self, outcome, reason):
        changed, failed = await _run_task(_source(), _outcome(outcome, reason=reason, content="new"), scheduled=False)
        changed.assert_not_awaited()
        failed.assert_not_awaited()


class TestSchedulerMarksItsTasks:
    @pytest.mark.asyncio
    async def test_scheduled_pass_flags_tasks_and_refresh_all_does_not(self):
        import datetime

        from app.services import kb_url_refresh as r

        def src(uuid):
            return SimpleNamespace(
                uuid=uuid, source_type="url", url="https://x.gov", status="ready", chunk_count=1,
                created_at=None, processed_at=None, last_refresh_attempted_at=None, refresh_queued_at=None,
                save=AsyncMock(),
            )

        def found(items):
            q = MagicMock()
            q.to_list = AsyncMock(return_value=items)
            return q

        kb = SimpleNamespace(uuid="kb-1", url_refresh_interval="daily", status="ready", save=AsyncMock())
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        with patch.object(r.KnowledgeBase, "find", return_value=found([kb])), \
             patch.object(r.KnowledgeBaseSource, "find", return_value=found([src("a")])), \
             patch("app.tasks.kb_validation_tasks.refresh_url_source_task.apply_async") as dispatch:
            await r.refresh_due_sources(now)
        assert dispatch.call_args.kwargs["kwargs"] == {"scheduled": True}

        with patch.object(r.KnowledgeBaseSource, "find", return_value=found([src("b")])), \
             patch("app.tasks.kb_validation_tasks.refresh_url_source_task.apply_async") as dispatch:
            await r.refresh_all(kb)
        assert not dispatch.call_args.kwargs["kwargs"]
