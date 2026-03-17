"""Tests for app.services.classification_service.

Tests text preparation, LLM-based classification, and applying results to documents.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.classification_service import (
    MAX_TEXT_LENGTH,
    _prepare_text_sample,
)


class TestPrepareTextSample:
    def test_short_text_unchanged(self):
        text = "This is a short document."
        result = _prepare_text_sample(text)
        assert result == text

    def test_long_text_truncated_with_marker(self):
        text = "A" * (MAX_TEXT_LENGTH + 1000)
        result = _prepare_text_sample(text)
        assert len(result) < len(text)
        assert "[...truncated...]" in result
        half = MAX_TEXT_LENGTH // 2
        assert result.startswith("A" * half)
        assert result.endswith("A" * half)


class TestClassifyDocument:
    @pytest.mark.asyncio
    async def test_no_text_returns_unrestricted_default(self):
        doc = MagicMock()
        doc.raw_text = None

        from app.services.classification_service import classify_document

        result = await classify_document(doc)
        assert result["classification"] == "unrestricted"
        assert result["confidence"] == 0.5

    @pytest.mark.asyncio
    async def test_valid_json_response_parsed(self):
        doc = MagicMock()
        doc.raw_text = "Some student transcript with grades."
        doc.title = "transcript.pdf"
        doc.extension = "pdf"

        llm_response = json.dumps({
            "classification": "ferpa",
            "confidence": 0.95,
            "reason": "Contains student education records",
        })

        mock_result = MagicMock()
        mock_result.output = llm_response

        mock_agent = MagicMock()
        mock_agent.run_sync = MagicMock(return_value=mock_result)

        mock_config = MagicMock()
        mock_config.get_extraction_config = MagicMock(return_value={"model": "gpt-4o-mini"})

        with patch("app.services.classification_service.SystemConfig") as MockSystemConfig, \
             patch("app.services.classification_service.create_chat_agent", return_value=mock_agent):
            MockSystemConfig.get_config = AsyncMock(return_value=mock_config)

            from app.services.classification_service import classify_document

            result = await classify_document(doc)

        assert result["classification"] == "ferpa"
        assert result["confidence"] == 0.95
        assert "student education records" in result["reason"]


class TestApplyClassification:
    @pytest.mark.asyncio
    async def test_sets_fields_and_saves(self):
        doc = MagicMock()
        doc.save = AsyncMock()

        from app.services.classification_service import apply_classification

        result = await apply_classification(doc, "ferpa", 0.92, classified_by="auto")

        assert doc.classification == "ferpa"
        assert doc.classification_confidence == 0.92
        assert doc.classified_by == "auto"
        assert doc.classified_at is not None
        doc.save.assert_awaited_once()
        assert result is doc
