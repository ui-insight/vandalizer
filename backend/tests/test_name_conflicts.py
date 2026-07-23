"""Tests for app.services.name_conflicts — scoped name-uniqueness checks.

Mocks Beanie model .find().count() to test query construction and the
raise / auto-suffix behavior without MongoDB.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import name_conflicts as nc


def _find_returning(count: int) -> MagicMock:
    find = MagicMock()
    find.return_value.count = AsyncMock(return_value=count)
    return find


# ---------------------------------------------------------------------------
# Scope query construction
# ---------------------------------------------------------------------------


class TestScopeQueries:
    def test_library_scope_with_team_includes_own_and_team_items(self):
        q = nc._library_scope("user1", "team1")
        assert q == {"$or": [
            {"user_id": "user1", "team_id": {"$in": ["team1", None]}},
            {"team_id": "team1"},
        ]}

    def test_library_scope_without_team_is_personal_only(self):
        assert nc._library_scope("user1", None) == {"user_id": "user1"}

    def test_kb_scope_excludes_implicit_and_includes_team_shared(self):
        q = nc._kb_scope("user1", "team1")
        assert {"$or": [
            {"user_id": "user1", "team_owned": {"$ne": True}},
            {"shared_with_team": True, "team_id": "team1"},
        ]} in q["$and"]
        assert {"implicit": {"$ne": True}} in q["$and"]

    def test_exact_name_escapes_regex_metachars(self):
        q = nc._exact_name("Budget (v2) $pecial")
        assert q["$options"] == "i"
        assert q["$regex"].startswith("^") and q["$regex"].endswith("$")
        assert "\\(" in q["$regex"] and "\\$pecial" in q["$regex"]


# ---------------------------------------------------------------------------
# ensure_* raise on conflict, pass when free
# ---------------------------------------------------------------------------


class TestEnsureAvailable:
    @pytest.mark.asyncio
    async def test_workflow_conflict_raises(self):
        with patch.object(nc.Workflow, "find", _find_returning(1)):
            with pytest.raises(nc.DuplicateNameError, match="Budget Analyzer"):
                await nc.ensure_workflow_name_available("Budget Analyzer", "user1", "team1")

    @pytest.mark.asyncio
    async def test_workflow_free_passes(self):
        with patch.object(nc.Workflow, "find", _find_returning(0)):
            await nc.ensure_workflow_name_available("Budget Analyzer", "user1", "team1")

    @pytest.mark.asyncio
    async def test_workflow_exclude_id_added_to_query(self):
        find = _find_returning(0)
        with patch.object(nc.Workflow, "find", find):
            await nc.ensure_workflow_name_available(
                "X", "user1", None, exclude_id="0123456789ab0123456789ab",
            )
        query = find.call_args.args[0]
        assert any("_id" in clause for clause in query["$and"])

    @pytest.mark.asyncio
    async def test_search_set_conflict_scoped_by_set_type(self):
        find = _find_returning(1)
        with patch.object(nc.SearchSet, "find", find):
            with pytest.raises(nc.DuplicateNameError, match="Prompt"):
                await nc.ensure_search_set_title_available("My Prompt", "prompt", "user1", None)
        query = find.call_args.args[0]
        assert any(clause.get("set_type") == "prompt" for clause in query["$and"] if isinstance(clause, dict))

    @pytest.mark.asyncio
    async def test_search_set_free_passes(self):
        with patch.object(nc.SearchSet, "find", _find_returning(0)):
            await nc.ensure_search_set_title_available("My Prompt", "prompt", "user1", None)

    @pytest.mark.asyncio
    async def test_kb_conflict_raises(self):
        with patch.object(nc.KnowledgeBase, "find", _find_returning(1)):
            with pytest.raises(nc.DuplicateNameError, match="knowledge base"):
                await nc.ensure_kb_title_available("Grants KB", "user1", "team1")

    @pytest.mark.asyncio
    async def test_kb_exclude_uuid_added_to_query(self):
        find = _find_returning(0)
        with patch.object(nc.KnowledgeBase, "find", find):
            await nc.ensure_kb_title_available("Grants KB", "user1", None, exclude_uuid="kb-1")
        query = find.call_args.args[0]
        assert {"uuid": {"$ne": "kb-1"}} in query["$and"]

    @pytest.mark.asyncio
    async def test_match_is_case_insensitive_regex(self):
        find = _find_returning(0)
        with patch.object(nc.Workflow, "find", find):
            await nc.ensure_workflow_name_available("budget analyzer", "user1", None)
        query = find.call_args.args[0]
        name_clause = next(c["name"] for c in query["$and"] if isinstance(c, dict) and "name" in c)
        assert name_clause["$options"] == "i"


# ---------------------------------------------------------------------------
# next_available_name — auto-suffixing for clone / duplicate / import
# ---------------------------------------------------------------------------


class TestNextAvailableName:
    @pytest.mark.asyncio
    async def test_returns_base_when_free(self):
        taken = AsyncMock(return_value=False)
        assert await nc.next_available_name("Budget Analyzer", taken) == "Budget Analyzer"

    @pytest.mark.asyncio
    async def test_plain_name_gets_parenthesized_number(self):
        async def taken(name):
            return name == "Budget Analyzer"
        assert await nc.next_available_name("Budget Analyzer", taken) == "Budget Analyzer (2)"

    @pytest.mark.asyncio
    async def test_copy_suffix_gets_number_inside_parens(self):
        async def taken(name):
            return name in ("Budget Analyzer (Copy)", "Budget Analyzer (Copy 2)")
        assert await nc.next_available_name("Budget Analyzer (Copy)", taken) == "Budget Analyzer (Copy 3)"

    @pytest.mark.asyncio
    async def test_respects_max_length(self):
        async def taken(name):
            return name == "x" * 100
        result = await nc.next_available_name("x" * 150, taken, max_length=100)
        assert len(result) <= 100
        assert result.endswith("(2)")

    @pytest.mark.asyncio
    async def test_gives_up_and_returns_base_rather_than_failing(self):
        taken = AsyncMock(return_value=True)
        assert await nc.next_available_name("Everything Taken", taken) == "Everything Taken"
