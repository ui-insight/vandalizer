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


class TestAdminListAllKnowledgeBases:
    """admin_list_all_knowledge_bases is unscoped, newest-first, optionally
    title-filtered, with the limit clamped."""

    def _mock_chain(self, mock_kb_cls, returns):
        limit_result = MagicMock()
        limit_result.to_list = AsyncMock(return_value=returns)
        sort_result = MagicMock()
        sort_result.limit = MagicMock(return_value=limit_result)
        find_result = MagicMock()
        find_result.sort = MagicMock(return_value=sort_result)
        mock_kb_cls.find = MagicMock(return_value=find_result)
        return find_result, sort_result

    @patch("app.services.knowledge_service.KnowledgeBase")
    async def test_no_search_empty_query(self, mock_kb_cls):
        from app.services.knowledge_service import admin_list_all_knowledge_bases
        find_result, sort_result = self._mock_chain(mock_kb_cls, ["kb1", "kb2"])
        out = await admin_list_all_knowledge_bases()
        assert out == ["kb1", "kb2"]
        mock_kb_cls.find.assert_called_once_with({})
        find_result.sort.assert_called_once_with("-created_at")
        sort_result.limit.assert_called_once_with(1000)

    @patch("app.services.knowledge_service.KnowledgeBase")
    async def test_search_builds_regex(self, mock_kb_cls):
        from app.services.knowledge_service import admin_list_all_knowledge_bases
        self._mock_chain(mock_kb_cls, [])
        await admin_list_all_knowledge_bases(search="a.b")  # '.' is regex-special
        mock_kb_cls.find.assert_called_once_with(
            {"title": {"$regex": "a\\.b", "$options": "i"}}
        )

    @patch("app.services.knowledge_service.KnowledgeBase")
    async def test_limit_clamped(self, mock_kb_cls):
        from app.services.knowledge_service import admin_list_all_knowledge_bases
        _, sort_result = self._mock_chain(mock_kb_cls, [])
        await admin_list_all_knowledge_bases(limit=99999)
        sort_result.limit.assert_called_once_with(5000)
