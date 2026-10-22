"""Suggesting web pages for a knowledge base from a described topic.

Feature request: building a KB from the web meant hunting down every link by
hand. The user now describes a topic and approves suggested pages. Every
suggestion must be a web-search result — the model plans the searches and
picks among numbered results, and can never introduce a URL of its own.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import kb_source_suggestions as s

KB = SimpleNamespace(uuid="kb-1", title="NSF proposals", description=None, team_id=None)
CONFIGURED = {"web_search_provider": "tavily"}


def _result(url, title="T", snippet="S"):
    return {"url": url, "title": title, "snippet": snippet}


class _FakeAgent:
    def __init__(self, output=None, exc=None):
        self.output, self.exc = output, exc
        self.prompts: list[str] = []

    async def run(self, prompt):
        self.prompts.append(prompt)
        if self.exc:
            raise self.exc
        return SimpleNamespace(output=self.output)


async def _suggest(*, searches, plan=None, picks=None, present=(), config=CONFIGURED, topic="NSF proposal requirements"):
    """Run suggest_sources with the plan agent, pick agent and searches faked."""
    agents = {s.SearchPlan: plan or _FakeAgent(s.SearchPlan(queries=[])), s.Picks: picks}

    async def agent(output_type, _prompt, _cfg):
        return agents[output_type]

    search_mock = AsyncMock(side_effect=lambda q, cfg, max_results: searches.get(q, {"results": []}))
    with patch.object(s, "_sys_config_doc", AsyncMock(return_value=config)), \
         patch.object(s, "_agent", agent), \
         patch("app.services.web_search_service.web_search", search_mock), \
         patch("app.services.knowledge_service.partition_new_urls", AsyncMock(return_value=([], list(present)))):
        out = await s.suggest_sources(KB, topic)
    return out, search_mock


class TestGrounding:
    @pytest.mark.asyncio
    async def test_suggestions_are_only_the_picked_search_results(self):
        searches = {
            "NSF proposal requirements": {"results": [_result("https://nsf.gov/pappg"), _result("https://blog.example/nsf")]},
            "NSF PAPPG chapter II": {"results": [_result("https://www.nsf.gov/pappg/"), _result("https://nsf.gov/budget")]},
        }
        plan = _FakeAgent(s.SearchPlan(queries=["NSF PAPPG chapter II"]))
        # 99 is not a candidate; 1 is repeated. Neither may become a page.
        picks = _FakeAgent(s.Picks(picks=[
            s.Pick(index=3, reason="Budget rules."), s.Pick(index=99, reason="Invented."),
            s.Pick(index=1, reason="The PAPPG."), s.Pick(index=1, reason="Again."),
        ]))
        out, search = await _suggest(searches=searches, plan=plan, picks=picks)

        assert [c.args[0] for c in search.await_args_list] == ["NSF proposal requirements", "NSF PAPPG chapter II"]
        assert [x["url"] for x in out["suggestions"]] == ["https://nsf.gov/budget", "https://nsf.gov/pappg"]
        assert out["suggestions"][0]["reason"] == "Budget rules."
        assert out["suggestions"][0]["host"] == "nsf.gov"
        # www./trailing-slash spelling of the same page was folded before picking.
        listing = picks.prompts[0]
        assert "3. T\n   https://nsf.gov/budget" in listing and "4." not in listing

    @pytest.mark.asyncio
    async def test_pages_already_in_the_kb_are_left_out_and_counted(self):
        searches = {"NSF proposal requirements": {"results": [_result("https://nsf.gov/a"), _result("https://nsf.gov/b")]}}
        picks = _FakeAgent(s.Picks(picks=[s.Pick(index=1, reason="b")]))
        out, _ = await _suggest(searches=searches, picks=picks, present=["https://nsf.gov/a"])
        assert [x["url"] for x in out["suggestions"]] == ["https://nsf.gov/b"]
        assert out["already_in_kb"] == 1
        assert "nsf.gov/a" not in picks.prompts[0]

    @pytest.mark.asyncio
    async def test_non_web_results_are_dropped(self):
        searches = {"NSF proposal requirements": {"results": [_result("javascript:alert(1)"), _result("https://nsf.gov/a")]}}
        picks = _FakeAgent(s.Picks(picks=[s.Pick(index=1, reason="a")]))
        out, _ = await _suggest(searches=searches, picks=picks)
        assert [x["url"] for x in out["suggestions"]] == ["https://nsf.gov/a"]


class TestDegrades:
    @pytest.mark.asyncio
    async def test_without_web_search_there_are_no_suggestions(self):
        out, search = await _suggest(searches={}, config={})
        assert out["available"] is False and out["suggestions"] == []
        search.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_plan_still_searches_the_topic(self):
        searches = {"NSF proposal requirements": {"results": [_result("https://nsf.gov/a")]}}
        picks = _FakeAgent(s.Picks(picks=[s.Pick(index=1, reason="a")]))
        out, search = await _suggest(searches=searches, plan=_FakeAgent(exc=RuntimeError("model down")), picks=picks)
        assert search.await_count == 1
        assert out["suggestions"][0]["url"] == "https://nsf.gov/a"

    @pytest.mark.asyncio
    async def test_failed_ranking_returns_search_order_without_reasons(self):
        searches = {"NSF proposal requirements": {"results": [_result(f"https://nsf.gov/{i}") for i in range(20)]}}
        out, _ = await _suggest(searches=searches, picks=_FakeAgent(exc=RuntimeError("model down")))
        assert len(out["suggestions"]) == s.MAX_SUGGESTIONS
        assert out["suggestions"][0] == {
            "url": "https://nsf.gov/0", "title": "T", "snippet": "S", "host": "nsf.gov", "reason": None,
        }

    @pytest.mark.asyncio
    async def test_a_trial_limit_is_not_swallowed_as_a_model_failure(self):
        from app.exceptions import TrialBudgetExceededError

        with pytest.raises(TrialBudgetExceededError):
            await _suggest(searches={}, plan=_FakeAgent(exc=TrialBudgetExceededError("over budget")))

    @pytest.mark.asyncio
    async def test_search_failure_is_reported(self):
        out, _ = await _suggest(searches={"NSF proposal requirements": {"error": "HTTP 401", "results": []}})
        assert out["suggestions"] == [] and out["error"] == "HTTP 401"


class TestRoute:
    def _client(self, result=None, exc=None):
        from fastapi.testclient import TestClient

        from app.dependencies import get_current_user
        from app.main import app

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(user_id="u1")
        self.patches = [
            patch("app.services.organization_service.get_user_org_ancestry", AsyncMock(return_value=None)),
            patch("app.routers.knowledge._require_manageable_kb", AsyncMock(return_value=KB)),
            patch.object(s, "suggest_sources", AsyncMock(return_value=result, side_effect=exc)),
        ]
        for p in self.patches:
            p.start()
        csrf = "test-csrf-token"
        client = TestClient(app, headers={"X-CSRF-Token": csrf})
        client.cookies.set("csrf_token", csrf)
        return client

    def teardown_method(self):
        from app.dependencies import get_current_user
        from app.main import app

        app.dependency_overrides.pop(get_current_user, None)
        for p in getattr(self, "patches", []):
            p.stop()

    def test_unconfigured_is_409(self):
        client = self._client({"available": False, "queries": [], "suggestions": [], "already_in_kb": 0, "error": None})
        r = client.post("/api/knowledge/kb-1/suggest-sources", json={"topic": "NSF proposals"})
        assert r.status_code == 409

    def test_too_short_topic_is_400(self):
        r = self._client().post("/api/knowledge/kb-1/suggest-sources", json={"topic": " a "})
        assert r.status_code == 400

    def test_returns_suggestions(self):
        body = {"available": True, "queries": ["q"], "already_in_kb": 0, "error": None,
                "suggestions": [{"url": "https://nsf.gov/a", "title": "A", "snippet": "", "host": "nsf.gov", "reason": "r"}]}
        r = self._client(body).post("/api/knowledge/kb-1/suggest-sources", json={"topic": "NSF proposals"})
        assert r.status_code == 200 and r.json()["suggestions"][0]["url"] == "https://nsf.gov/a"
