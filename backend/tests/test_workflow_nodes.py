"""Tests for every workflow node type's process() method.

Each node is tested with mocked external dependencies (LLM, HTTP, file I/O).
Tests cover happy paths, error handling, and input routing logic.
"""

import base64
import json
import zipfile
import io
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from app.services.workflow_engine import (
    ApprovalNode,
    APICallNode,
    AddDocumentNode,
    BrowserAutomationNode,
    CodeExecutionNode,
    CrawlerNode,
    DataExportNode,
    DescribeImageNode,
    DocumentNode,
    DocumentRendererNode,
    ExtractionNode,
    FormatNode,
    FormFillerNode,
    KnowledgeBaseQueryNode,
    MultiTaskNode,
    PackageBuilderNode,
    PromptNode,
    ResearchNode,
    WebsiteNode,
)


# ---------------------------------------------------------------------------
# ExtractionNode
# ---------------------------------------------------------------------------

class TestExtractionNode:
    @patch("app.services.workflow_engine.data_extraction_model")
    def test_basic_extraction_from_document(self, mock_extract):
        mock_extract.return_value = {
            "raw": [{"Name": "Alice", "Age": "30"}],
            "formatted": "- **Name**: Alice\n- **Age**: 30",
        }
        node = ExtractionNode({"searchphrases": ["Name", "Age"], "model": "gpt-4o"})
        result = node.process({"output": ["uuid1"], "step_name": "Document"})

        assert result["step_name"] == "Extraction"
        assert result["output"] == [{"Name": "Alice", "Age": "30"}]
        assert "formatted_output" in result
        mock_extract.assert_called_once()

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_extraction_uses_keys_fallback(self, mock_extract):
        mock_extract.return_value = {"raw": [{"Title": "Test"}], "formatted": "- **Title**: Test"}
        node = ExtractionNode({"keys": ["Title"], "model": "gpt-4o"})
        result = node.process({"output": ["uuid1"], "step_name": "Document"})
        args = mock_extract.call_args
        assert args[0][1] == ["Title"]

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_extraction_from_selected_document(self, mock_extract):
        mock_extract.return_value = {"raw": [{"Name": "Bob"}], "formatted": ""}
        node = ExtractionNode({
            "model": "gpt-4o",
            "keys": ["Name"],
            "input_source": "select_document",
            "selected_doc_text": "Bob is a scientist.",
        })
        result = node.process({"output": "prev", "step_name": "Prompt"})
        args, kwargs = mock_extract.call_args
        assert kwargs.get("full_text") == "Bob is a scientist." or args[2] is not None

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_extraction_from_workflow_documents(self, mock_extract):
        mock_extract.return_value = {"raw": [{"X": "1"}], "formatted": ""}
        node = ExtractionNode({
            "model": "gpt-4o",
            "keys": ["X"],
            "input_source": "workflow_documents",
            "doc_texts": ["doc text 1"],
        })
        result = node.process({"output": "prev", "step_name": "SomeStep"})
        args, kwargs = mock_extract.call_args
        assert kwargs.get("doc_texts") == ["doc text 1"] or args[2] is not None

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_extraction_from_prompt_output(self, mock_extract):
        mock_extract.return_value = {"raw": [{"Info": "val"}], "formatted": ""}
        node = ExtractionNode({"model": "gpt-4o", "keys": ["Info"]})
        result = node.process({"output": {"answer": "some answer"}, "step_name": "Prompt"})
        args, kwargs = mock_extract.call_args
        assert "some answer" in (kwargs.get("full_text", "") or "")

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_extraction_from_prompt_list_output(self, mock_extract):
        mock_extract.return_value = {"raw": [], "formatted": ""}
        node = ExtractionNode({"model": "gpt-4o", "keys": ["X"]})
        result = node.process({"output": ["line1", "line2"], "step_name": "Prompt"})
        args, kwargs = mock_extract.call_args
        assert "line1" in (kwargs.get("full_text", "") or "")

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_extraction_from_generic_step(self, mock_extract):
        mock_extract.return_value = {"raw": [{"Y": "2"}], "formatted": ""}
        node = ExtractionNode({"model": "gpt-4o", "keys": ["Y"]})
        result = node.process({"output": "plain text", "step_name": "AddWebsite"})
        args, kwargs = mock_extract.call_args
        assert kwargs.get("full_text") == "plain text"

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_extraction_reports_progress(self, mock_extract):
        mock_extract.return_value = {"raw": [], "formatted": ""}
        node = ExtractionNode({"model": "gpt-4o", "keys": ["X"]})
        progress = []
        node.progress_reporter = lambda d=None, p=None: progress.append(d)
        node.process({"output": [], "step_name": "Document"})
        assert any("Extraction" in str(p) for p in progress)


# ---------------------------------------------------------------------------
# PromptNode
# ---------------------------------------------------------------------------

class TestPromptNode:
    @patch("app.services.workflow_engine.llm_chat_model")
    def test_basic_prompt(self, mock_llm):
        mock_llm.return_value = "The answer is 42."
        node = PromptNode({"prompt": "What is the answer?", "model": "gpt-4o"})
        result = node.process({"output": "some data", "step_name": "Document"})

        assert result["output"] == "The answer is 42."
        assert result["step_name"] == "Prompt"
        assert result["input"] == "What is the answer?"

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_prompt_with_select_document(self, mock_llm):
        mock_llm.return_value = "Response"
        node = PromptNode({
            "prompt": "Summarize",
            "model": "gpt-4o",
            "input_source": "select_document",
            "selected_doc_text": "Full document text here.",
        })
        result = node.process({"output": "prev", "step_name": "SomeStep"})
        assert result["output"] == "Response"
        _, kwargs = mock_llm.call_args
        assert kwargs.get("data") == "Full document text here."

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_prompt_with_workflow_documents(self, mock_llm):
        mock_llm.return_value = "Response"
        node = PromptNode({
            "prompt": "Analyze",
            "model": "gpt-4o",
            "input_source": "workflow_documents",
            "doc_texts": ["text1", "text2"],
        })
        result = node.process({"output": "prev", "step_name": "SomeStep"})
        _, kwargs = mock_llm.call_args
        assert "text1" in kwargs.get("data", "")

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_prompt_from_document_step(self, mock_llm):
        mock_llm.return_value = "Response"
        node = PromptNode({"prompt": "Test", "model": "gpt-4o", "doc_texts": ["doc content"]})
        result = node.process({"output": ["uuid1"], "step_name": "Document"})
        _, kwargs = mock_llm.call_args
        assert "doc content" in kwargs.get("data", "")

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_prompt_step_input(self, mock_llm):
        mock_llm.return_value = "Result"
        node = PromptNode({"prompt": "Refine this", "model": "gpt-4o"})
        result = node.process({"output": "previous step output", "step_name": "Extraction"})
        _, kwargs = mock_llm.call_args
        assert kwargs.get("data") == "previous step output"

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_prompt_default_prompt(self, mock_llm):
        mock_llm.return_value = "output"
        node = PromptNode({"model": "gpt-4o"})
        result = node.process({"output": "data", "step_name": "X"})
        args, kwargs = mock_llm.call_args
        assert kwargs.get("prompt") == "Enter prompt" or args[1] == "Enter prompt"


# ---------------------------------------------------------------------------
# FormatNode
# ---------------------------------------------------------------------------

class TestFormatNode:
    @patch("app.services.workflow_engine.format_model")
    def test_basic_format(self, mock_format):
        mock_format.return_value = ("prompt", "formatted output")
        node = FormatNode({"prompt": "Make a table", "model": "gpt-4o"})
        result = node.process({"output": "raw data", "step_name": "Extraction"})

        assert result["output"] == "formatted output"
        assert result["step_name"] == "Formatter"

    @patch("app.services.workflow_engine.format_model")
    def test_format_select_document(self, mock_format):
        mock_format.return_value = ("p", "formatted")
        node = FormatNode({
            "prompt": "Format",
            "model": "gpt-4o",
            "input_source": "select_document",
            "selected_doc_text": "my doc",
        })
        result = node.process({"output": "prev", "step_name": "X"})
        args = mock_format.call_args[0]
        assert args[2] == "my doc"

    @patch("app.services.workflow_engine.format_model")
    def test_format_workflow_documents(self, mock_format):
        mock_format.return_value = ("p", "formatted")
        node = FormatNode({
            "prompt": "Format",
            "model": "gpt-4o",
            "input_source": "workflow_documents",
            "doc_texts": ["a", "b"],
        })
        result = node.process({"output": "prev", "step_name": "X"})
        args = mock_format.call_args[0]
        assert "=== Document 1 ===\na\n\n=== Document 2 ===\nb" == args[2]

    @patch("app.services.workflow_engine.format_model")
    def test_format_from_prompt_step(self, mock_format):
        mock_format.return_value = ("p", "formatted")
        node = FormatNode({"prompt": "Format", "model": "gpt-4o"})
        result = node.process({"output": {"formatted_answer": "nice text"}, "step_name": "Prompt"})
        args = mock_format.call_args[0]
        assert args[2] == "nice text"

    @patch("app.services.workflow_engine.format_model")
    def test_format_from_prompt_string_output(self, mock_format):
        mock_format.return_value = ("p", "formatted")
        node = FormatNode({"prompt": "Format", "model": "gpt-4o"})
        result = node.process({"output": "plain text", "step_name": "Prompt"})
        args = mock_format.call_args[0]
        assert args[2] == "plain text"


# ---------------------------------------------------------------------------
# WebsiteNode
# ---------------------------------------------------------------------------

class TestWebsiteNode:
    @patch("app.services.workflow_engine._extract_text_from_html")
    @patch("app.services.workflow_engine.httpx.Client")
    @patch("app.utils.url_validation.validate_outbound_url")
    def test_successful_fetch(self, mock_validate, mock_client_cls, mock_extract):
        mock_validate.return_value = "https://example.com"
        mock_response = MagicMock()
        mock_response.text = "<p>Page content</p>"
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client
        mock_extract.return_value = "Page content"

        node = WebsiteNode({"url": "https://example.com"})
        result = node.process({"output": "prev"})
        assert result["output"] == "Page content"
        assert result["step_name"] == "AddWebsite"

    def test_empty_url(self):
        node = WebsiteNode({"url": ""})
        result = node.process({"output": "prev"})
        assert result["output"] == ""

    @patch("app.utils.url_validation.validate_outbound_url", side_effect=ValueError("blocked"))
    def test_blocked_url(self, mock_validate):
        node = WebsiteNode({"url": "http://metadata.google.internal"})
        result = node.process({"output": "prev"})
        assert "Blocked URL" in result["output"]

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_http_error(self, mock_client_cls, mock_validate):
        import httpx
        mock_validate.return_value = "https://example.com"
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = WebsiteNode({"url": "https://example.com/404"})
        result = node.process({"output": "prev"})
        assert "HTTP error" in result["output"]


# ---------------------------------------------------------------------------
# DescribeImageNode
# ---------------------------------------------------------------------------

class TestDescribeImageNode:
    @patch("app.services.workflow_engine.llm_chat_model")
    def test_describe_image(self, mock_llm):
        mock_llm.return_value = "A beautiful landscape"
        node = DescribeImageNode({
            "image_url": "https://example.com/img.png",
            "prompt": "Describe colors",
            "model": "gpt-4o",
        })
        result = node.process({"output": "prev"})
        assert result["output"] == "A beautiful landscape"
        assert result["step_name"] == "DescribeImage"

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_default_prompt(self, mock_llm):
        mock_llm.return_value = "description"
        node = DescribeImageNode({"model": "gpt-4o"})
        result = node.process({"output": None})
        args, kwargs = mock_llm.call_args
        assert "Describe this image" in kwargs.get("prompt", "") or "Describe this image" in args[1]


# ---------------------------------------------------------------------------
# CodeExecutionNode
# ---------------------------------------------------------------------------

class TestCodeExecutionNode:
    @patch("app.utils.code_sandbox.validate_sandbox_code")
    def test_basic_code_execution(self, mock_validate):
        mock_validate.return_value = None
        node = CodeExecutionNode({"code": "result = len(data)"})
        result = node.process({"output": [1, 2, 3]})
        assert result["output"] == 3
        assert result["step_name"] == "CodeNode"

    @patch("app.utils.code_sandbox.validate_sandbox_code")
    def test_code_with_json(self, mock_validate):
        mock_validate.return_value = None
        node = CodeExecutionNode({"code": "result = json.dumps(data)"})
        result = node.process({"output": {"key": "val"}})
        assert json.loads(result["output"]) == {"key": "val"}

    @patch("app.utils.code_sandbox.validate_sandbox_code")
    def test_code_with_string_ops(self, mock_validate):
        mock_validate.return_value = None
        node = CodeExecutionNode({"code": "result = str(data).upper()"})
        result = node.process({"output": "hello"})
        assert result["output"] == "HELLO"

    def test_empty_code(self):
        node = CodeExecutionNode({"code": ""})
        result = node.process({"output": "data"})
        assert result["output"] == ""

    @patch("app.utils.code_sandbox.validate_sandbox_code",
           side_effect=ValueError("Forbidden: import detected"))
    def test_rejected_code(self, mock_validate):
        node = CodeExecutionNode({"code": "import os"})
        result = node.process({"output": "data"})
        assert "Code rejected" in result["output"]

    @patch("app.utils.code_sandbox.validate_sandbox_code",
           side_effect=SyntaxError("invalid syntax"))
    def test_syntax_error(self, mock_validate):
        node = CodeExecutionNode({"code": "def ("})
        result = node.process({"output": "data"})
        assert "Code rejected" in result["output"]

    @patch("app.utils.code_sandbox.validate_sandbox_code")
    def test_runtime_error(self, mock_validate):
        mock_validate.return_value = None
        node = CodeExecutionNode({"code": "result = 1 / 0"})
        result = node.process({"output": "data"})
        assert "Code execution error" in result["output"]

    @patch("app.utils.code_sandbox.validate_sandbox_code")
    def test_timeout(self, mock_validate):
        mock_validate.return_value = None
        # Use a busy-wait loop (no import needed) to trigger timeout
        node = CodeExecutionNode({"code": "while True: pass"})
        node.CODE_TIMEOUT_SECONDS = 1  # Override for testing
        result = node.process({"output": "data"})
        assert "timed out" in result["output"]

    @patch("app.utils.code_sandbox.validate_sandbox_code")
    def test_no_result_set(self, mock_validate):
        mock_validate.return_value = None
        node = CodeExecutionNode({"code": "x = 42"})  # doesn't set result
        result = node.process({"output": "data"})
        # result var is initialized to None in local_vars, get() returns None
        assert result["output"] is None


# ---------------------------------------------------------------------------
# CrawlerNode
# ---------------------------------------------------------------------------

class TestCrawlerNode:
    def test_empty_start_url(self):
        node = CrawlerNode({"start_url": ""})
        result = node.process({"output": "prev"})
        assert result["output"] == ""

    @patch("app.utils.url_validation.validate_outbound_url", side_effect=ValueError("blocked"))
    def test_blocked_start_url(self, mock_validate):
        node = CrawlerNode({"start_url": "http://169.254.169.254"})
        result = node.process({"output": "prev"})
        assert "Blocked URL" in result["output"]

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_crawls_single_page(self, mock_client_cls, mock_validate):
        mock_validate.return_value = "https://example.com"
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Page 1</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = CrawlerNode({"start_url": "https://example.com", "max_pages": 1})
        result = node.process({"output": "prev"})
        assert "example.com" in result["output"]
        assert result["step_name"] == "CrawlerNode"

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_respects_max_pages(self, mock_client_cls, mock_validate):
        mock_validate.return_value = "ok"
        mock_response = MagicMock()
        mock_response.text = '<html><body><p>Content</p><a href="/page2">Link</a></body></html>'
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = CrawlerNode({"start_url": "https://example.com", "max_pages": 1})
        result = node.process({"output": "prev"})
        # Should only fetch 1 page despite link being present
        assert mock_client.get.call_count == 1


# ---------------------------------------------------------------------------
# ResearchNode
# ---------------------------------------------------------------------------

class TestResearchNode:
    @patch("app.services.workflow_engine.llm_chat_model")
    def test_two_pass_research(self, mock_llm):
        mock_llm.side_effect = [
            "Finding 1: X is important\nFinding 2: Y matters",
            "# Research Report\n## Summary\nX and Y are key findings.",
        ]
        node = ResearchNode({"question": "What matters?", "model": "gpt-4o"})
        result = node.process({"output": "raw data here"})

        assert result["step_name"] == "ResearchNode"
        assert "Research Report" in result["output"]
        assert mock_llm.call_count == 2

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_research_reports_progress(self, mock_llm):
        mock_llm.side_effect = ["findings", "report"]
        node = ResearchNode({"question": "test", "model": "gpt-4o"})
        progress = []
        node.progress_reporter = lambda d=None, p=None: progress.append(d)
        node.process({"output": "data"})
        assert any("Pass 1" in str(p) for p in progress)
        assert any("Pass 2" in str(p) for p in progress)


# ---------------------------------------------------------------------------
# APICallNode
# ---------------------------------------------------------------------------

class TestAPICallNode:
    def test_empty_url(self):
        node = APICallNode({"url": ""})
        result = node.process({"output": "prev"})
        assert result["output"] == ""

    @patch("app.utils.url_validation.validate_outbound_url", side_effect=ValueError("blocked"))
    def test_blocked_url(self, mock_validate):
        node = APICallNode({"url": "http://internal"})
        result = node.process({"output": "prev"})
        assert "Blocked URL" in result["output"]

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_get_json_response(self, mock_client_cls, mock_validate):
        mock_validate.return_value = "ok"
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "value"}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = APICallNode({"url": "https://api.example.com/data", "method": "GET"})
        result = node.process({"output": "prev"})
        assert result["output"] == {"data": "value"}
        assert result["step_name"] == "APINode"

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_post_with_json_body(self, mock_client_cls, mock_validate):
        mock_validate.return_value = "ok"
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = APICallNode({
            "url": "https://api.example.com/create",
            "method": "POST",
            "body": '{"key": "value"}',
        })
        result = node.process({"output": "prev"})
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["json"] == {"key": "value"}

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_post_with_text_body(self, mock_client_cls, mock_validate):
        mock_validate.return_value = "ok"
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = APICallNode({
            "url": "https://api.example.com/create",
            "method": "POST",
            "body": "plain text body",
        })
        result = node.process({"output": "prev"})
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["content"] == "plain text body"

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_get_ignores_body(self, mock_client_cls, mock_validate):
        mock_validate.return_value = "ok"
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = APICallNode({
            "url": "https://api.example.com",
            "method": "GET",
            "body": '{"ignored": true}',
        })
        result = node.process({"output": "prev"})
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["json"] is None
        assert call_kwargs["content"] is None

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_custom_headers(self, mock_client_cls, mock_validate):
        mock_validate.return_value = "ok"
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = APICallNode({
            "url": "https://api.example.com",
            "method": "GET",
            "headers": '{"Authorization": "Bearer token"}',
        })
        result = node.process({"output": "prev"})
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer token"

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_non_json_response(self, mock_client_cls, mock_validate):
        mock_validate.return_value = "ok"
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("not json")
        mock_response.text = "plain text response"
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = APICallNode({"url": "https://api.example.com", "method": "GET"})
        result = node.process({"output": "prev"})
        assert result["output"] == "plain text response"

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_http_error(self, mock_client_cls, mock_validate):
        import httpx
        mock_validate.return_value = "ok"
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server Error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = APICallNode({"url": "https://api.example.com", "method": "GET"})
        result = node.process({"output": "prev"})
        assert "HTTP error" in result["output"]


# ---------------------------------------------------------------------------
# FormFillerNode
# ---------------------------------------------------------------------------

class TestFormFillerNode:
    @patch("app.services.workflow_engine.llm_chat_model")
    def test_basic_fill(self, mock_llm):
        mock_llm.return_value = "Dear Alice, your order #123 is ready."
        node = FormFillerNode({
            "template": "Dear {{name}}, your order #{{order_id}} is ready.",
            "model": "gpt-4o",
        })
        result = node.process({"output": {"name": "Alice", "order_id": "123"}})
        assert result["output"] == "Dear Alice, your order #123 is ready."
        assert result["step_name"] == "FormFiller"

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_reports_progress(self, mock_llm):
        mock_llm.return_value = "filled"
        node = FormFillerNode({"template": "test", "model": "gpt-4o"})
        progress = []
        node.progress_reporter = lambda d=None, p=None: progress.append(d)
        node.process({"output": {}})
        assert any("Filling" in str(p) for p in progress)


# ---------------------------------------------------------------------------
# PackageBuilderNode
# ---------------------------------------------------------------------------

class TestPackageBuilderNode:
    def test_builds_zip(self):
        node = PackageBuilderNode({"package_name": "my_pkg"})
        result = node.process({"output": {"key": "value"}})
        output = result["output"]
        assert output["type"] == "file_download"
        assert output["file_type"] == "zip"
        assert output["filename"] == "my_pkg.zip"

        # Verify ZIP contents
        zip_bytes = base64.b64decode(output["data_b64"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            assert "output.json" in names
            assert "output.txt" in names
            json_content = json.loads(zf.read("output.json"))
            assert json_content == {"key": "value"}

    def test_string_input(self):
        node = PackageBuilderNode({"package_name": "pkg"})
        result = node.process({"output": "hello world"})
        zip_bytes = base64.b64decode(result["output"]["data_b64"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert zf.read("output.txt").decode() == "hello world"

    def test_default_name(self):
        node = PackageBuilderNode({})
        result = node.process({"output": "data"})
        assert result["output"]["filename"] == "package.zip"


# ---------------------------------------------------------------------------
# ApprovalNode
# ---------------------------------------------------------------------------

class TestApprovalNode:
    def test_approval_pauses(self):
        node = ApprovalNode({
            "review_instructions": "Check the data",
            "assigned_to_user_ids": ["user1", "user2"],
        })
        result = node.process({"output": {"extracted": "data"}})

        assert result["_approval_pause"] is True
        assert result["_review_instructions"] == "Check the data"
        assert result["_assigned_to_user_ids"] == ["user1", "user2"]
        assert result["_data_for_review"] == {"extracted": "data"}
        assert result["output"] == {"extracted": "data"}
        assert result["step_name"] == "Approval"

    def test_default_review_instructions(self):
        node = ApprovalNode({})
        result = node.process({"output": "data"})
        assert "review" in result["_review_instructions"].lower()

    def test_passes_through_output(self):
        node = ApprovalNode({})
        result = node.process({"output": "my data"})
        assert result["output"] == "my data"


# ---------------------------------------------------------------------------
# KnowledgeBaseQueryNode
# ---------------------------------------------------------------------------

class TestKnowledgeBaseQueryNode:
    @patch("app.services.document_manager.DocumentManager")
    def test_basic_query(self, mock_dm_cls):
        mock_dm = MagicMock()
        mock_dm.query_kb.return_value = [
            {"content": "Chunk 1 text", "metadata": {"source_name": "doc1.pdf"}},
            {"content": "Chunk 2 text", "metadata": {"source_name": "doc2.pdf"}},
        ]
        mock_dm_cls.return_value = mock_dm

        node = KnowledgeBaseQueryNode({
            "kb_uuid": "kb-123",
            "query": "What is the policy?",
            "k": 5,
        })
        result = node.process({"output": "prev"})

        assert "Chunk 1 text" in result["output"]
        assert "doc1.pdf" in result["output"]
        assert "Chunk 2 text" in result["output"]
        assert result["step_name"] == "KnowledgeBaseQuery"

    def test_empty_kb_uuid(self):
        node = KnowledgeBaseQueryNode({"kb_uuid": "", "query": "test"})
        result = node.process({"output": "prev"})
        assert result["output"] == ""

    def test_empty_query(self):
        node = KnowledgeBaseQueryNode({"kb_uuid": "kb-123", "query": ""})
        result = node.process({"output": "prev"})
        assert result["output"] == ""

    @patch("app.services.document_manager.DocumentManager")
    def test_no_results(self, mock_dm_cls):
        mock_dm = MagicMock()
        mock_dm.query_kb.return_value = []
        mock_dm_cls.return_value = mock_dm

        node = KnowledgeBaseQueryNode({"kb_uuid": "kb-123", "query": "obscure"})
        result = node.process({"output": "prev"})
        assert result["output"] == ""


# ---------------------------------------------------------------------------
# BrowserAutomationNode
# ---------------------------------------------------------------------------

class TestBrowserAutomationNode:
    @patch("app.services.browser_automation.BrowserAutomationService")
    def test_smart_instruction(self, mock_service_cls):
        mock_service = MagicMock()
        mock_session = MagicMock()
        mock_session.session_id = "sess-123"
        mock_service.create_session.return_value = mock_session
        mock_service.execute_smart_action.return_value = {"data": "scraped"}
        mock_service_cls.get_instance.return_value = mock_service

        node = BrowserAutomationNode({
            "user_id": "user1",
            "smart_instruction": "Find the price",
            "model": "gpt-4o",
        })
        result = node.process({"output": "prev"})

        assert result["output"] == {"data": "scraped"}
        assert result["session_id"] == "sess-123"
        mock_service.end_session.assert_called_once_with("sess-123")

    @patch("app.services.browser_automation.BrowserAutomationService")
    def test_action_sequence(self, mock_service_cls):
        mock_service = MagicMock()
        mock_session = MagicMock()
        mock_session.session_id = "sess-456"
        mock_service.create_session.return_value = mock_session
        mock_service.execute_action_with_stack.side_effect = [
            {"result": "click done"},
            {"result": "text extracted"},
        ]
        mock_service_cls.get_instance.return_value = mock_service

        node = BrowserAutomationNode({
            "user_id": "user1",
            "actions": [{"type": "click"}, {"type": "extract"}],
        })
        result = node.process({"output": "prev"})

        assert result["output"] == {"result": "text extracted"}
        assert mock_service.execute_action_with_stack.call_count == 2

    @patch("app.services.browser_automation.BrowserAutomationService")
    def test_error_handling(self, mock_service_cls):
        mock_service = MagicMock()
        mock_session = MagicMock()
        mock_session.session_id = "sess-err"
        mock_service.create_session.return_value = mock_session
        mock_service.start_session.side_effect = RuntimeError("Browser crashed")
        mock_service_cls.get_instance.return_value = mock_service

        node = BrowserAutomationNode({"user_id": "user1"})
        result = node.process({"output": "prev"})

        assert "error" in result["output"].lower() or "error" in result.get("error", "").lower()
        mock_service.end_session.assert_called_once()  # cleanup still runs


# ---------------------------------------------------------------------------
# Node._apply_post_process
# ---------------------------------------------------------------------------

class TestNodePostProcess:
    @patch("app.services.workflow_engine.llm_chat_model")
    def test_post_process_applied(self, mock_llm):
        mock_llm.return_value = "Post-processed output"
        node = PromptNode({
            "prompt": "test",
            "model": "gpt-4o",
            "post_process_prompt": "Reformat this as bullets",
        })
        result = {"output": "raw output"}
        processed = node._apply_post_process(result)
        assert processed["output"] == "Post-processed output"

    def test_no_post_process_when_not_configured(self):
        node = PromptNode({"prompt": "test", "model": "gpt-4o"})
        result = {"output": "raw output"}
        processed = node._apply_post_process(result)
        assert processed["output"] == "raw output"

    def test_no_post_process_when_empty_output(self):
        node = PromptNode({
            "prompt": "test",
            "model": "gpt-4o",
            "post_process_prompt": "Reformat",
        })
        result = {"output": ""}
        processed = node._apply_post_process(result)
        assert processed["output"] == ""
