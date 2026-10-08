"""Unit tests for KB source provenance (source_reference) and the admin
KB inventory listing — both added for the 'show source' / version-review ticket."""

from unittest.mock import AsyncMock, MagicMock, patch


class TestSetSourceReference:
    """set_source_reference sets/clears the provenance field without touching
    custom_name or rewriting ChromaDB (it's metadata, not a citation label)."""

    @patch("app.services.knowledge_service.KnowledgeBaseSource")
    async def test_sets_reference(self, mock_src_cls):
        from app.services.knowledge_service import set_source_reference
        kb = MagicMock(uuid="kb1")
        source = MagicMock()
        source.save = AsyncMock()
        mock_src_cls.find_one = AsyncMock(return_value=source)

        out = await set_source_reference(kb, "s1", "  https://www.uidaho.edu/apm/45  ")
        assert out is source
        assert source.source_reference == "https://www.uidaho.edu/apm/45"  # trimmed
        source.save.assert_awaited_once()

    @patch("app.services.knowledge_service.KnowledgeBaseSource")
    async def test_empty_clears_reference(self, mock_src_cls):
        from app.services.knowledge_service import set_source_reference
        source = MagicMock()
        source.save = AsyncMock()
        mock_src_cls.find_one = AsyncMock(return_value=source)

        await set_source_reference(MagicMock(uuid="kb1"), "s1", "   ")
        assert source.source_reference is None

    @patch("app.services.knowledge_service.KnowledgeBaseSource")
    async def test_missing_source_returns_none(self, mock_src_cls):
        from app.services.knowledge_service import set_source_reference
        mock_src_cls.find_one = AsyncMock(return_value=None)
        out = await set_source_reference(MagicMock(uuid="kb1"), "nope", "x")
        assert out is None

    @patch("app.services.knowledge_service.KnowledgeBaseSource")
    async def test_caps_long_reference(self, mock_src_cls):
        from app.services.knowledge_service import set_source_reference
        source = MagicMock()
        source.save = AsyncMock()
        mock_src_cls.find_one = AsyncMock(return_value=source)
        await set_source_reference(MagicMock(uuid="kb1"), "s1", "x" * 5000)
        assert len(source.source_reference) == 2000


class TestAdminSearchKnowledgeBases:
    @patch("app.services.knowledge_service.KnowledgeBase")
    async def test_inventory_count_and_page_share_one_filtered_pipeline(self, model):
        from app.services.knowledge_service import admin_search_knowledge_bases
        model.aggregate.return_value.to_list = AsyncMock(return_value=[{"records": [{"uuid": "kb-501"}], "count": [{"total": 503}]}])
        model.model_validate.side_effect = lambda row: row
        rows, total = await admin_search_knowledge_bases(status="ready", sort="updated", offset=500, limit=100)
        assert rows == [{"uuid": "kb-501"}] and total == 503
        pipeline = model.aggregate.call_args.args[0]
        assert pipeline[0] == {"$match": {"status": "ready"}}
        assert pipeline[-1]["$facet"]["records"] == [{"$sort": {"updated_at": -1, "_id": 1}}, {"$skip": 500}, {"$limit": 100}]
        assert not any("$lookup" in stage for stage in pipeline)

    @patch("app.services.knowledge_service.Team")
    @patch("app.services.knowledge_service.User")
    @patch("app.services.knowledge_service.KnowledgeBase")
    async def test_search_is_literal_and_covers_owner_team_title_and_tags(self, model, users, teams):
        from app.services.knowledge_service import admin_search_knowledge_bases
        model.aggregate.return_value.to_list = AsyncMock(return_value=[{"records": [], "count": []}])
        users.get_collection_name.return_value = "user"
        teams.get_collection_name.return_value = "team"
        assert await admin_search_knowledge_bases(search=" a.b ", sort="title") == ([], 0)
        pipeline = model.aggregate.call_args.args[0]
        match = next(stage["$match"] for stage in pipeline if "$match" in stage)
        assert match["$or"] == [{field: {"$regex": r"a\.b", "$options": "i"}} for field in ["title", "tags", "inventory_owner.email", "inventory_team.name"]]
        assert pipeline[-1]["$facet"]["records"][0] == {"$sort": {"title": 1, "_id": 1}}
        assert model.aggregate.call_args.kwargs["collation"]["strength"] == 2

    @patch("app.services.knowledge_service.KnowledgeBase")
    async def test_limit_clamped_and_blank_search_needs_no_joins(self, model):
        from app.services.knowledge_service import admin_search_knowledge_bases
        model.aggregate.return_value.to_list = AsyncMock(return_value=[])
        assert await admin_search_knowledge_bases(search="  ", limit=99999, offset=-5) == ([], 0)
        assert model.aggregate.call_args.args[0] == [{"$facet": {"records": [{"$sort": {"created_at": -1, "_id": 1}}, {"$skip": 0}, {"$limit": 5000}], "count": [{"$count": "total"}]}}]
