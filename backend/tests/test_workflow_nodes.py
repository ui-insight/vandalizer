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
    def test_extraction_forwards_field_metadata(self, mock_extract):
        """Optional designations + enum validation resolved from a saved set
        must reach the engine when an extraction runs inside a workflow."""
        mock_extract.return_value = {"raw": [], "formatted": ""}
        field_metadata = [
            {"key": "Status", "is_optional": False, "enum_values": ["Open", "Closed"]},
            {"key": "Notes", "is_optional": True, "enum_values": []},
        ]
        node = ExtractionNode({
            "model": "gpt-4o",
            "keys": ["Status", "Notes"],
            "field_metadata": field_metadata,
        })
        node.process({"output": ["uuid1"], "step_name": "Document"})
        assert mock_extract.call_args.kwargs.get("field_metadata") == field_metadata

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_extraction_omits_field_metadata_when_absent(self, mock_extract):
        """Manual-field extractions (no saved set) pass no field_metadata."""
        mock_extract.return_value = {"raw": [], "formatted": ""}
        node = ExtractionNode({"model": "gpt-4o", "keys": ["X"]})
        node.process({"output": ["uuid1"], "step_name": "Document"})
        assert "field_metadata" not in mock_extract.call_args.kwargs

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

    @patch("app.services.workflow_engine.data_extraction_model")
    def test_extraction_multi_source_step_and_documents(self, mock_extract):
        """Combining step_input + workflow_documents extracts from each text."""
        mock_extract.return_value = {"raw": [], "formatted": ""}
        node = ExtractionNode({
            "model": "gpt-4o",
            "keys": ["X"],
            "input_sources": ["step_input", "workflow_documents"],
            "doc_texts": ["doc one", "doc two"],
        })
        node.process({"output": "step text", "step_name": "APINode"})
        kwargs = mock_extract.call_args.kwargs
        assert kwargs.get("doc_texts") == ["step text", "doc one", "doc two"]


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
    def test_missing_prompt_is_a_step_error_not_a_model_call(self, mock_llm):
        """No prompt key used to send the literal placeholder "Enter prompt" to
        the model, which answered it ("The context does not contain a prompt
        to enter.") and the run completed green with that as its output."""
        node = PromptNode({"model": "gpt-4o"})
        result = node.process({"output": "data", "step_name": "X"})
        mock_llm.assert_not_called()
        assert result["error"] == PromptNode.EMPTY_PROMPT_ERROR
        assert "no instructions" in result["output"]
        assert result["step_name"] == "Prompt"

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_empty_prompt_is_a_step_error(self, mock_llm):
        node = PromptNode({"prompt": "", "model": "gpt-4o"})
        result = node.process({"output": "data", "step_name": "X"})
        mock_llm.assert_not_called()
        assert result["error"] == PromptNode.EMPTY_PROMPT_ERROR

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_whitespace_prompt_is_a_step_error(self, mock_llm):
        node = PromptNode({"prompt": "  \n\t ", "model": "gpt-4o"})
        result = node.process({"output": "data", "step_name": "X"})
        mock_llm.assert_not_called()
        assert result["error"] == PromptNode.EMPTY_PROMPT_ERROR

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_linked_saved_prompt_with_empty_body_is_a_step_error(self, mock_llm):
        """The saved-prompt resolver leaves `prompt` untouched when the Library
        item has no body yet, so the node sees the link and no text."""
        node = PromptNode({"saved_prompt_uuid": "abc", "model": "gpt-4o"})
        result = node.process({"output": "data", "step_name": "X"})
        mock_llm.assert_not_called()
        assert result["error"] == PromptNode.EMPTY_PROMPT_ERROR

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_empty_prompt_fails_the_run_in_engine(self, mock_llm):
        """Through the engine the step error becomes WorkflowStepError, so the
        run is marked failed with the message rather than completing with the
        placeholder answer as its deliverable."""
        from app.services.workflow_engine import WorkflowEngine, WorkflowStepError

        engine = WorkflowEngine()
        node = PromptNode({"prompt": "", "model": "gpt-4o"})
        engine.add_node(node)
        with pytest.raises(WorkflowStepError) as exc_info:
            engine.execute()
        mock_llm.assert_not_called()
        assert exc_info.value.step_name == "Prompt"
        assert "no instructions" in str(exc_info.value)

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_prompt_multi_source_step_and_document(self, mock_llm):
        """input_sources combining step output + a selected document yields a labeled context."""
        mock_llm.return_value = "Response"
        node = PromptNode({
            "prompt": "Pick the best title",
            "model": "gpt-4o",
            "input_sources": ["step_input", "select_document"],
            "selected_doc_text": "The grant proposal text.",
        })
        node.process({"output": {"titles": ["Title 1", "Title 2"]}, "step_name": "APINode"})
        data = mock_llm.call_args.kwargs.get("data", "")
        assert "Previous Step Output" in data
        assert "Selected Document" in data
        assert "Title 1" in data
        assert "grant proposal text" in data

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_prompt_multi_source_skips_empty(self, mock_llm):
        """An empty source is dropped from the combined context."""
        mock_llm.return_value = "Response"
        node = PromptNode({
            "prompt": "Use what's there",
            "model": "gpt-4o",
            "input_sources": ["step_input", "select_document"],
            "selected_doc_text": "",  # empty
        })
        node.process({"output": "step output", "step_name": "Prev"})
        data = mock_llm.call_args.kwargs.get("data", "")
        # Single non-empty source -> raw payload, no section headers
        assert data == "step output"

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_prompt_input_sources_takes_precedence_over_legacy(self, mock_llm):
        """When both `input_sources` and `input_source` are set, the new field wins."""
        mock_llm.return_value = "Response"
        node = PromptNode({
            "prompt": "Test",
            "model": "gpt-4o",
            "input_source": "step_input",  # legacy
            "input_sources": ["select_document"],  # new wins
            "selected_doc_text": "doc body",
        })
        node.process({"output": "step output", "step_name": "Prev"})
        data = mock_llm.call_args.kwargs.get("data", "")
        assert data == "doc body"

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_prompt_step_input_after_document_trigger_swaps_to_workflow_docs(self, mock_llm):
        """When the previous step is the Document trigger, step_input is replaced
        with workflow_documents (the trigger emits UUIDs, not text)."""
        mock_llm.return_value = "Response"
        node = PromptNode({
            "prompt": "Summarize",
            "model": "gpt-4o",
            "input_sources": ["step_input"],
            "doc_texts": ["doc body"],
        })
        node.process({"output": ["uuid-1"], "step_name": "Document"})
        data = mock_llm.call_args.kwargs.get("data", "")
        assert "doc body" in data
        assert "uuid-1" not in data


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
        # PromptNode now always returns a string output, so FormatNode
        # receives that string directly.
        result = node.process({"output": "nice text", "step_name": "Prompt"})
        args = mock_format.call_args[0]
        assert args[2] == "nice text"

    @patch("app.services.workflow_engine.format_model")
    def test_format_from_prompt_string_output(self, mock_format):
        mock_format.return_value = ("p", "formatted")
        node = FormatNode({"prompt": "Format", "model": "gpt-4o"})
        result = node.process({"output": "plain text", "step_name": "Prompt"})
        args = mock_format.call_args[0]
        assert args[2] == "plain text"

    @patch("app.services.workflow_engine.format_model")
    def test_format_multi_source(self, mock_format):
        """input_sources combining step + selected document yields a labeled blob."""
        mock_format.return_value = ("p", "out")
        node = FormatNode({
            "prompt": "Format",
            "model": "gpt-4o",
            "input_sources": ["step_input", "select_document"],
            "selected_doc_text": "doc body",
        })
        node.process({"output": "step output", "step_name": "Prev"})
        text = mock_format.call_args[0][2]
        assert "Previous Step Output" in text
        assert "Selected Document" in text
        assert "step output" in text
        assert "doc body" in text


# ---------------------------------------------------------------------------
# WebsiteNode
# ---------------------------------------------------------------------------

class TestWebsiteNode:
    @patch("app.services.web_fetcher.fetch_url_sync")
    def test_successful_fetch(self, mock_fetch):
        from app.services.web_fetcher import WebFetchResult

        mock_fetch.return_value = WebFetchResult(
            url="https://example.com",
            title="Example",
            text="Page content",
            raw_html="<p>Page content</p>",
            used_browser=False,
            status_code=200,
        )
        node = WebsiteNode({"url": "https://example.com"})
        result = node.process({"output": "prev"})
        assert result["output"] == "Page content"
        assert result["step_name"] == "AddWebsite"

    def test_empty_url_is_a_configuration_error(self):
        """An Add Website step saved without a URL used to return "" and let
        the run finish Completed. It now reports an error so the engine fails
        the run naming the step."""
        node = WebsiteNode({"url": ""})
        result = node.process({"output": "prev"})
        assert result["output"] == ""
        assert "not configured: no URL" in result["error"]

    def test_missing_url_key_is_a_configuration_error(self):
        result = WebsiteNode({}).process({"output": "prev"})
        assert "not configured" in result["error"]

    def test_whitespace_url_is_a_configuration_error(self):
        result = WebsiteNode({"url": "   "}).process({"output": "prev"})
        assert "not configured" in result["error"]

    def test_empty_url_fails_the_run(self):
        from app.services.workflow_engine import WorkflowEngine, WorkflowStepError

        engine = WorkflowEngine()
        engine.add_node(WebsiteNode({"url": ""}))
        with pytest.raises(WorkflowStepError) as exc:
            engine.execute()
        assert exc.value.step_name == "AddWebsite"
        assert "not configured" in str(exc.value)

    @patch("app.services.web_fetcher.fetch_url_sync", side_effect=ValueError("blocked"))
    def test_blocked_url(self, mock_fetch):
        node = WebsiteNode({"url": "http://metadata.google.internal"})
        result = node.process({"output": "prev"})
        assert "Blocked URL" in result["output"]
        assert "Blocked URL" in result["error"]

    @patch("app.services.web_fetcher.fetch_url_sync")
    def test_http_error(self, mock_fetch):
        import httpx
        request = httpx.Request("GET", "https://example.com/404")
        response = httpx.Response(404, request=request)
        mock_fetch.side_effect = httpx.HTTPStatusError(
            "Not Found", request=request, response=response
        )
        node = WebsiteNode({"url": "https://example.com/404"})
        result = node.process({"output": "prev"})
        assert "Could not fetch" in result["output"]
        assert "HTTP 404" in result["output"]

    @patch("app.services.web_fetcher.fetch_url_sync")
    def test_blocked_site_error_names_automated_access(self, mock_fetch):
        import httpx
        request = httpx.Request("GET", "https://www.usda.gov/terms.pdf")
        response = httpx.Response(403, request=request)
        mock_fetch.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=request, response=response
        )
        node = WebsiteNode({"url": "https://www.usda.gov/terms.pdf"})
        result = node.process({"output": "prev"})
        assert "refused automated access" in result["output"]


# ---------------------------------------------------------------------------
# DescribeImageNode
# ---------------------------------------------------------------------------

class TestDescribeImageNode:
    """The model must SEE the image. The old implementation pasted the URL
    into a text prompt; the model, asked to describe an image it could not
    see, complied — confident, invented output on a run marked Completed.
    Every failure path must be a step error, never a text-only model call.
    """

    MULTIMODAL_CFG = {"available_models": [{"name": "gpt-4o", "multimodal": True}]}

    def _node(self, sys_cfg=None, **data):
        data.setdefault("image_url", "https://example.com/img.png")
        data.setdefault("model", "gpt-4o")
        node = DescribeImageNode(data)
        node._sys_cfg = sys_cfg if sys_cfg is not None else self.MULTIMODAL_CFG
        return node

    def _http_response(self, content=b"\x89PNG...", content_type="image/png",
                       status=200, redirect_to=None, content_length=None):
        """A response as yielded by ``client.stream(...)``'s context manager."""
        resp = MagicMock()
        resp.is_redirect = redirect_to is not None
        headers = {"content-type": content_type}
        if redirect_to is not None:
            headers["location"] = redirect_to
        if content_length is not None:
            headers["content-length"] = str(content_length)
        resp.headers = headers
        resp.iter_bytes.return_value = iter([content])
        if status >= 400:
            import httpx
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "boom", request=MagicMock(), response=MagicMock(status_code=status),
            )
        return resp

    def _wire(self, mock_client, *responses):
        """Wire consecutive ``client.stream()`` calls to yield *responses*."""
        contexts = []
        for resp in responses:
            ctx = MagicMock()
            ctx.__enter__.return_value = resp
            contexts.append(ctx)
        mock_client.return_value.__enter__.return_value.stream.side_effect = contexts

    @patch("app.services.workflow_engine.create_chat_agent")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_fetches_the_image_and_sends_the_bytes_to_the_model(self, mock_client, mock_agent):
        from pydantic_ai import BinaryContent

        self._wire(mock_client, self._http_response(content=b"pngbytes"))
        mock_agent.return_value.run_sync.return_value = MagicMock(output="A landscape")

        result = self._node(prompt="Describe colors").process({"output": "prev"})

        assert result["output"] == "A landscape"
        assert result["step_name"] == "DescribeImage"
        assert "error" not in result
        (parts,) = mock_agent.return_value.run_sync.call_args[0]
        binary = [p for p in parts if isinstance(p, BinaryContent)]
        assert len(binary) == 1
        assert binary[0].data == b"pngbytes"
        assert binary[0].media_type == "image/png"
        text = [p for p in parts if isinstance(p, str)]
        assert "Describe colors" in text[0]

    @patch("app.services.workflow_engine.create_chat_agent")
    def test_text_only_model_is_a_step_error_not_a_model_call(self, mock_agent):
        """Some providers silently drop an attachment a text model can't take
        and answer from the prompt alone — the exact fabrication this node
        exists to prevent, so it must not even reach the model."""
        cfg = {"available_models": [{"name": "gpt-4o", "multimodal": False}]}
        result = self._node(sys_cfg=cfg).process({"output": "prev"})
        assert "multimodal" in result["error"]
        mock_agent.assert_not_called()

    @patch("app.services.workflow_engine.create_chat_agent")
    def test_missing_url_is_a_step_error(self, mock_agent):
        result = self._node(image_url="  ").process({"output": None})
        assert "no image URL" in result["error"]
        mock_agent.assert_not_called()

    @patch("app.services.workflow_engine.create_chat_agent")
    def test_internal_url_is_blocked_before_any_fetch(self, mock_agent):
        result = self._node(image_url="http://169.254.169.254/latest").process({"output": None})
        assert "Blocked URL" in result["error"]
        mock_agent.assert_not_called()

    @patch("app.services.workflow_engine.create_chat_agent")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_http_failure_is_a_step_error(self, mock_client, mock_agent):
        self._wire(mock_client, self._http_response(status=404))
        result = self._node().process({"output": None})
        assert "404" in result["error"]
        mock_agent.assert_not_called()

    @patch("app.services.workflow_engine.create_chat_agent")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_non_image_response_is_a_step_error(self, mock_client, mock_agent):
        self._wire(mock_client, self._http_response(content=b"<html>", content_type="text/html"))
        result = self._node(image_url="https://example.com/page").process({"output": None})
        assert "did not return an image" in result["error"]
        mock_agent.assert_not_called()

    @patch("app.services.workflow_engine.create_chat_agent")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_octet_stream_with_image_extension_falls_back_to_the_url(self, mock_client, mock_agent):
        from pydantic_ai import BinaryContent

        self._wire(mock_client, self._http_response(
            content=b"jpg", content_type="application/octet-stream",
        ))
        mock_agent.return_value.run_sync.return_value = MagicMock(output="desc")

        result = self._node(image_url="https://example.com/photo.jpg").process({"output": None})

        assert "error" not in result
        (parts,) = mock_agent.return_value.run_sync.call_args[0]
        binary = [p for p in parts if isinstance(p, BinaryContent)][0]
        assert binary.media_type == "image/jpeg"

    @patch("app.services.workflow_engine.create_chat_agent")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_oversized_image_is_refused_without_buffering_it_all(self, mock_client, mock_agent):
        """The cap is enforced as bytes arrive; a multi-GB URL must not
        balloon the worker to learn it is over the limit."""
        from app.services.workflow_engine import DESCRIBE_IMAGE_MAX_BYTES

        resp = self._http_response()
        half = b"x" * (DESCRIBE_IMAGE_MAX_BYTES // 2 + 1)
        endless = MagicMock()
        endless.__next__ = MagicMock(return_value=half)
        resp.iter_bytes.return_value = iter([half, half, half])
        self._wire(mock_client, resp)
        result = self._node().process({"output": None})
        assert "too large" in result["error"]
        mock_agent.assert_not_called()

    @patch("app.services.workflow_engine.create_chat_agent")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_declared_content_length_over_the_cap_is_refused_before_reading(self, mock_client, mock_agent):
        from app.services.workflow_engine import DESCRIBE_IMAGE_MAX_BYTES

        resp = self._http_response(content_length=DESCRIBE_IMAGE_MAX_BYTES + 1)
        self._wire(mock_client, resp)
        result = self._node().process({"output": None})
        assert "too large" in result["error"]
        resp.iter_bytes.assert_not_called()
        mock_agent.assert_not_called()

    @patch("app.services.workflow_engine.create_chat_agent")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_redirect_to_an_internal_address_is_blocked(self, mock_client, mock_agent):
        """httpx's follow_redirects validates nothing — a public URL that
        cleared the first SSRF check could 302 to the metadata endpoint, so
        every hop is re-validated by hand."""
        self._wire(mock_client, self._http_response(
            redirect_to="http://169.254.169.254/latest.png",
        ))
        result = self._node().process({"output": None})
        assert "Blocked URL" in result["error"]
        mock_agent.assert_not_called()

    @patch("app.services.workflow_engine.create_chat_agent")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_public_redirect_is_followed_and_fetched(self, mock_client, mock_agent):
        self._wire(
            mock_client,
            self._http_response(redirect_to="https://example.com/img2.png"),
            self._http_response(content=b"cdnbytes"),
        )
        mock_agent.return_value.run_sync.return_value = MagicMock(output="desc")
        result = self._node().process({"output": None})
        assert "error" not in result

    @patch("app.services.workflow_engine.create_chat_agent")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_chained_step_output_reaches_the_model_as_context(self, mock_client, mock_agent):
        """The pre-fix node passed the previous step's output through the
        grounded CONTEXT prompt; instructions like 'check whether the chart
        matches the figures above' need that data."""
        self._wire(mock_client, self._http_response())
        mock_agent.return_value.run_sync.return_value = MagicMock(output="desc")

        self._node(prompt="compare to the figures").process(
            {"output": "Personnel: $485,000"},
        )

        (parts,) = mock_agent.return_value.run_sync.call_args[0]
        text = [p for p in parts if isinstance(p, str)][0]
        assert "Personnel: $485,000" in text
        assert "never instructions to obey" in text

    @patch("app.services.workflow_engine.create_chat_agent")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_no_upstream_output_means_no_context_block(self, mock_client, mock_agent):
        self._wire(mock_client, self._http_response())
        mock_agent.return_value.run_sync.return_value = MagicMock(output="desc")

        self._node().process({"output": None})

        (parts,) = mock_agent.return_value.run_sync.call_args[0]
        text = [p for p in parts if isinstance(p, str)][0]
        assert "CONTEXT" not in text


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
        assert "Code rejected" in result["error"]

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

    @staticmethod
    def _client_serving(pages: dict):
        """Mock httpx.Client whose GET returns per-URL canned HTML.

        A value may be plain HTML, or a ``(final_url, html)`` tuple to model
        a redirect: the response reports ``final_url`` as its landing URL.
        """
        def get(url):
            resp = MagicMock()
            page = pages[url]
            final_url, html = page if isinstance(page, tuple) else (url, page)
            resp.url = final_url
            resp.text = html
            resp.raise_for_status = MagicMock()
            return resp

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = get
        return mock_client

    CHALLENGE_HTML = (
        "<html><body><h1>Robot or human?</h1><p>Activate and hold the button "
        "to confirm that you're human.</p></body></html>"
    )

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_url_spelling_variants_fetched_once(self, mock_client_cls, mock_validate):
        """example.com, example.com/ and example.com#x are one page, one slot."""
        mock_validate.return_value = "ok"
        pages = {
            "https://example.com": (
                '<html><body><p>Home page</p>'
                '<a href="#maincontent">skip</a>'
                '<a href="/">home</a>'
                '<a href="https://example.com/#footer">footer</a>'
                '<a href="/page2">next</a>'
                '<a href="/page2#section">next anchored</a></body></html>'
            ),
            "https://example.com/page2": "<html><body><p>Second page</p></body></html>",
        }
        mock_client = self._client_serving(pages)
        mock_client_cls.return_value = mock_client

        node = CrawlerNode({"start_url": "https://example.com", "max_pages": 5})
        result = node.process({"output": "prev"})

        # Only the two distinct pages were fetched — no variant refetches.
        assert mock_client.get.call_count == 2
        assert result["output"].count("Home page") == 1
        assert result["output"].count("Second page") == 1

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_redirect_landing_url_not_refetched(self, mock_client_cls, mock_validate):
        """A page reached via redirect isn't fetched again under the URL it
        landed on (uidaho.edu → www.uidaho.edu, then a www.…/#fragment link)."""
        mock_validate.return_value = "ok"
        home_html = (
            '<html><body><p>Home page</p>'
            '<a href="https://www.example.com/#content">skip</a>'
            '<a href="https://www.example.com/page2">next</a></body></html>'
        )
        pages = {
            # Start URL redirects to the www spelling.
            "https://example.com": ("https://www.example.com/", home_html),
            # If dedup fails, the fragment link refetches the homepage here.
            "https://www.example.com/#content": ("https://www.example.com/", home_html),
            "https://www.example.com/page2": "<html><body><p>Second page</p></body></html>",
        }
        mock_client = self._client_serving(pages)
        mock_client_cls.return_value = mock_client

        node = CrawlerNode({
            "start_url": "https://example.com",
            "max_pages": 5,
            "allowed_domains": "example.com, www.example.com",
        })
        result = node.process({"output": "prev"})

        assert mock_client.get.call_count == 2
        assert result["output"].count("Home page") == 1
        assert result["output"].count("Second page") == 1

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_challenge_pages_excluded_and_do_not_consume_slots(self, mock_client_cls, mock_validate):
        """Blocked pages are skipped without a Max Pages slot; crawl continues."""
        mock_validate.return_value = "ok"
        pages = {
            "https://example.com": (
                '<html><body><p>Real home page content</p>'
                '<a href="/blocked1">a</a><a href="/blocked2">b</a>'
                '<a href="/real2">c</a></body></html>'
            ),
            "https://example.com/blocked1": self.CHALLENGE_HTML,
            "https://example.com/blocked2": self.CHALLENGE_HTML,
            "https://example.com/real2": "<html><body><p>Second real page</p></body></html>",
        }
        mock_client_cls.return_value = self._client_serving(pages)

        node = CrawlerNode({"start_url": "https://example.com", "max_pages": 2})
        result = node.process({"output": "prev"})

        # Both real pages made it in — the two blocked pages didn't use slots.
        assert "Real home page content" in result["output"]
        assert "Second real page" in result["output"]
        # The junk verification text is excluded from the output body.
        assert "Robot or human" not in result["output"]
        # The user is told pages were skipped.
        assert "2 page(s) skipped — blocked by bot protection" in result["output"]

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_all_pages_blocked_reports_no_content(self, mock_client_cls, mock_validate):
        mock_validate.return_value = "ok"
        pages = {"https://example.com": self.CHALLENGE_HTML}
        mock_client_cls.return_value = self._client_serving(pages)

        node = CrawlerNode({"start_url": "https://example.com", "max_pages": 5})
        result = node.process({"output": "prev"})

        assert "Robot or human" not in result["output"]
        assert "No page content retrieved" in result["output"]
        assert "1 page(s) skipped — blocked by bot protection" in result["output"]

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_http_error_challenge_counts_as_blocked(self, mock_client_cls, mock_validate):
        """Challenges served with 403/503 are recognized from the error body."""
        import httpx as _httpx

        mock_validate.return_value = "ok"
        resp = MagicMock()
        resp.text = self.CHALLENGE_HTML
        resp.raise_for_status = MagicMock(side_effect=_httpx.HTTPStatusError(
            "403", request=MagicMock(), response=resp,
        ))
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = resp
        mock_client_cls.return_value = mock_client

        node = CrawlerNode({"start_url": "https://example.com", "max_pages": 5})
        result = node.process({"output": "prev"})

        assert "1 page(s) skipped — blocked by bot protection" in result["output"]


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

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_document_trigger_uses_doc_texts_not_uuids(self, mock_llm):
        mock_llm.side_effect = ["findings", "report"]
        node = ResearchNode({
            "question": "What's the RFA about?",
            "model": "gpt-4o",
            "doc_texts": ["The RFA seeks proposals for AI safety research."],
        })
        node.process({
            "step_name": "Document",
            "output": ["d41d8cd98f00b204e9800998ecf8427e"],
        })
        for call in mock_llm.call_args_list:
            assert call.kwargs["data"] == "The RFA seeks proposals for AI safety research."

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_research_multi_source(self, mock_llm):
        """ResearchNode honors input_sources by passing combined context to both passes."""
        mock_llm.side_effect = ["findings", "report"]
        node = ResearchNode({
            "question": "Q?",
            "model": "gpt-4o",
            "input_sources": ["step_input", "workflow_documents"],
            "doc_texts": ["doc body"],
        })
        node.process({"output": "step text", "step_name": "Prev"})
        for call in mock_llm.call_args_list:
            data = call.kwargs["data"]
            assert "Previous Step Output" in data
            assert "Workflow Documents" in data
            assert "step text" in data
            assert "doc body" in data


# ---------------------------------------------------------------------------
# APICallNode
# ---------------------------------------------------------------------------

class TestAPICallNode:
    def test_empty_url_is_a_configuration_error(self):
        node = APICallNode({"url": ""})
        result = node.process({"output": "prev"})
        assert "not configured: no URL" in result["error"]

    def test_null_url_is_a_configuration_error(self):
        result = APICallNode({"url": None}).process({"output": "prev"})
        assert "not configured: no URL" in result["error"]

    @patch("app.utils.url_validation.validate_outbound_url", side_effect=ValueError("blocked"))
    def test_blocked_url(self, mock_validate):
        node = APICallNode({"url": "http://internal"})
        result = node.process({"output": "prev"})
        assert "Blocked URL" in result["output"]
        assert "Blocked URL" in result["error"]

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_http_error_sets_error_and_request_preview(self, mock_client_cls, _mock_validate):
        import httpx

        request = httpx.Request("GET", "https://api.example.com/data")
        response = httpx.Response(500, request=request, text="server exploded")
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "boom", request=request, response=response,
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = APICallNode({"url": "https://api.example.com/data", "method": "GET"})
        result = node.process({"output": "prev"})
        assert result["error"].startswith("HTTP error: 500")
        # The full output keeps the request preview for debugging.
        assert "--- Request sent ---" in result["output"]
        assert result["request"]["url"] == "https://api.example.com/data"

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_request_error_sets_error(self, mock_client_cls, _mock_validate):
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.side_effect = httpx.ConnectError("connection refused")
        mock_client_cls.return_value = mock_client

        node = APICallNode({"url": "https://api.example.com/data", "method": "GET"})
        result = node.process({"output": "prev"})
        assert result["error"].startswith("Request error:")
        assert result["request"]["url"] == "https://api.example.com/data"

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    def test_invalid_headers_json_sets_error(self, _mock_validate):
        node = APICallNode({
            "url": "https://api.example.com/data",
            "method": "GET",
            "headers": "{not json",
        })
        result = node.process({"output": "prev"})
        assert "Invalid Headers JSON" in result["error"]

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

    @staticmethod
    def _ok_client(mock_client_cls, json_return=None):
        """Wire a MagicMock httpx.Client that returns a 200 JSON response."""
        mock_response = MagicMock()
        mock_response.json.return_value = json_return if json_return is not None else {"ok": True}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client
        return mock_client

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_body_template_wraps_upstream_output(self, mock_client_cls, _mock_validate):
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({
            "url": "https://api.example.com/create",
            "method": "POST",
            "body": '{"records": {{ inputs.output }}}',
        })
        node.process({"output": [{"id": 1}, {"id": 2}]})
        assert mock_client.request.call_args[1]["json"] == {"records": [{"id": 1}, {"id": 2}]}

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_body_template_unknown_variable_errors(self, mock_client_cls, _mock_validate):
        node = APICallNode({
            "url": "https://api.example.com/create",
            "method": "POST",
            "body": '{"x": {{ inputs.output.missing }}}',
        })
        result = node.process({"output": {"present": 1}})
        assert "could not be resolved" in result["output"]
        mock_client_cls.assert_not_called()

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_empty_body_passthrough_dict(self, mock_client_cls, _mock_validate):
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({"url": "https://api.example.com/store", "method": "POST"})
        node.process({"output": {"id": 1, "value": "x"}})
        assert mock_client.request.call_args[1]["json"] == {"id": 1, "value": "x"}

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_empty_body_passthrough_string_as_content(self, mock_client_cls, _mock_validate):
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({"url": "https://api.example.com/store", "method": "PUT"})
        node.process({"output": "raw text result"})
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["content"] == "raw text result"
        assert call_kwargs["json"] is None

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_get_with_empty_body_has_no_passthrough(self, mock_client_cls, _mock_validate):
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({"url": "https://api.example.com", "method": "GET"})
        node.process({"output": {"id": 1}})
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["json"] is None
        assert call_kwargs["content"] is None

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_configured_scalar_body_is_not_dropped(self, mock_client_cls, _mock_validate):
        # Regression: a populated body that parses to a JSON scalar (not an
        # object/array) used to fall through to a zero-byte POST, which the
        # remote rejected with a confusing 400. It must go out as raw JSON text.
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({
            "url": "https://api.example.com/submit",
            "method": "POST",
            "body": "123",
        })
        node.process({"output": "prev"})
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["content"] == "123"
        assert call_kwargs["json"] is None

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_configured_null_body_is_not_dropped(self, mock_client_cls, _mock_validate):
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({
            "url": "https://api.example.com/submit",
            "method": "POST",
            "body": "null",
        })
        node.process({"output": "prev"})
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["content"] == "null"
        assert call_kwargs["json"] is None

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_json_object_body_defaults_content_type(self, mock_client_cls, _mock_validate):
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({
            "url": "https://api.example.com/submit",
            "method": "POST",
            "body": '{"a": 1}',
        })
        node.process({"output": "prev"})
        assert mock_client.request.call_args[1]["headers"]["Content-Type"] == "application/json"

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_scalar_body_sent_as_content_defaults_content_type(self, mock_client_cls, _mock_validate):
        # The string/content send path doesn't get httpx's automatic JSON
        # content-type — we must add it ourselves so Flask's request.json works.
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({
            "url": "https://api.example.com/submit",
            "method": "POST",
            "body": "123",
        })
        node.process({"output": "prev"})
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["content"] == "123"
        assert call_kwargs["headers"]["Content-Type"] == "application/json"

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_passthrough_dict_defaults_content_type(self, mock_client_cls, _mock_validate):
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({"url": "https://api.example.com/submit", "method": "POST"})
        node.process({"output": {"id": 1}})
        assert mock_client.request.call_args[1]["headers"]["Content-Type"] == "application/json"

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_explicit_content_type_not_overridden(self, mock_client_cls, _mock_validate):
        # User picked a different content type (and a different casing) — respect it.
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({
            "url": "https://api.example.com/submit",
            "method": "POST",
            "headers": '{"content-type": "application/vnd.api+json"}',
            "body": '{"a": 1}',
        })
        node.process({"output": "prev"})
        sent = mock_client.request.call_args[1]["headers"]
        assert sent["content-type"] == "application/vnd.api+json"
        assert "Content-Type" not in sent

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_non_json_text_body_gets_no_content_type(self, mock_client_cls, _mock_validate):
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({
            "url": "https://api.example.com/submit",
            "method": "POST",
            "body": "plain text body",
        })
        node.process({"output": "prev"})
        assert "Content-Type" not in mock_client.request.call_args[1]["headers"]

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_success_includes_request_preview(self, mock_client_cls, _mock_validate):
        self._ok_client(mock_client_cls, json_return={"ok": True})
        node = APICallNode({
            "url": "https://api.example.com/submit",
            "method": "POST",
            "body": '{"a": 1}',
        })
        result = node.process({"output": "prev"})
        req = result["request"]
        assert req["method"] == "POST"
        assert req["url"] == "https://api.example.com/submit"
        assert req["body"] == '{"a": 1}'
        assert req["body_bytes"] == len('{"a": 1}'.encode())
        assert req["headers"]["Content-Type"] == "application/json"

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_request_preview_redacts_secrets(self, mock_client_cls, _mock_validate):
        self._ok_client(mock_client_cls)
        node = APICallNode({
            "url": "https://api.example.com/submit",
            "method": "POST",
            "headers": '{"Authorization": "Bearer s3cr3t", "X-Api-Key": "abc", "X-Trace": "ok"}',
            "body": '{"a": 1}',
        })
        result = node.process({"output": "prev"})
        headers = result["request"]["headers"]
        assert headers["Authorization"] == "<redacted>"
        assert headers["X-Api-Key"] == "<redacted>"
        assert headers["X-Trace"] == "ok"  # non-secret header passes through
        # And the secret must not leak anywhere in the serialized result.
        assert "s3cr3t" not in json.dumps(result)

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_http_error_embeds_request_in_output(self, mock_client_cls, _mock_validate):
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 415
        mock_response.text = "Unsupported Media Type"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "415", request=MagicMock(), response=mock_response
        )
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = APICallNode({
            "url": "https://marina.example.com/submit/foo",
            "method": "POST",
            "body": '{"records": [1, 2]}',
        })
        result = node.process({"output": "prev"})
        assert "HTTP error: 415" in result["output"]
        assert "--- Request sent ---" in result["output"]
        assert "POST https://marina.example.com/submit/foo" in result["output"]
        assert "request" in result and result["request"]["method"] == "POST"

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_url_template_interpolates_upstream_id(self, mock_client_cls, _mock_validate):
        mock_client = self._ok_client(mock_client_cls)
        node = APICallNode({
            "url": "https://api.example.com/records/{{ inputs.output.id }}",
            "method": "GET",
        })
        node.process({"output": {"id": "abc123"}})
        assert mock_client.request.call_args[0] == ("GET", "https://api.example.com/records/abc123")

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

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_malformed_headers_returns_error(self, mock_client_cls, _mock_validate):
        # Smart quotes — looks like JSON to a human but fails json.loads.
        # Previously the parse error was silently swallowed, which sent the
        # request with no auth headers and produced a confusing 403 from the
        # target server (commonly Vandalizer's own CSRF middleware when the
        # missing header was x-api-key).
        node = APICallNode({
            "url": "https://api.example.com",
            "method": "POST",
            "headers": '{“x-api-key”: “secret”}',
        })
        result = node.process({"output": "prev"})
        assert "Invalid Headers JSON" in result["output"]
        mock_client_cls.assert_not_called()

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_non_object_headers_returns_error(self, mock_client_cls, _mock_validate):
        node = APICallNode({
            "url": "https://api.example.com",
            "method": "POST",
            "headers": '"just-a-string"',
        })
        result = node.process({"output": "prev"})
        assert "Invalid Headers JSON" in result["output"]
        mock_client_cls.assert_not_called()

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

    # -----------------------------------------------------------------------
    # auth_strategy
    # -----------------------------------------------------------------------

    @patch("app.utils.url_validation.validate_outbound_url", return_value="ok")
    def test_auth_strategy_requires_credential_id(self, _mock_validate):
        node = APICallNode({
            "url": "https://api.example.com",
            "method": "GET",
            "auth_strategy": "static_header",
        })
        result = node.process({"output": "prev"})
        assert "requires credential_id" in result["output"]

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine._open_sync_db")
    def test_auth_strategy_credential_not_found(self, mock_open_db, mock_validate):
        mock_validate.return_value = "ok"
        db = MagicMock()
        db.credential.find_one.return_value = None
        mock_open_db.return_value = db

        node = APICallNode({
            "url": "https://api.example.com",
            "auth_strategy": "static_header",
            "credential_id": "507f1f77bcf86cd799439011",
        })
        result = node.process({"output": "prev"})
        assert "not found" in result["output"]

    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine._open_sync_db")
    def test_auth_strategy_type_mismatch(self, mock_open_db, mock_validate):
        mock_validate.return_value = "ok"
        db = MagicMock()
        db.credential.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "type": "static_header",
            "payload": {"header_name": "X", "header_value": "y"},
        }
        mock_open_db.return_value = db

        node = APICallNode({
            "url": "https://api.example.com",
            "auth_strategy": "oauth_client_credentials",
            "credential_id": "507f1f77bcf86cd799439011",
        })
        result = node.process({"output": "prev"})
        assert "does not match" in result["output"]

    @patch("app.services.credentials_service.decrypt_value", side_effect=lambda v: v)
    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine._open_sync_db")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_static_header_strategy_attaches_header(
        self, mock_client_cls, mock_open_db, mock_validate, _mock_decrypt
    ):
        mock_validate.return_value = "ok"
        db = MagicMock()
        db.credential.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "type": "static_header",
            "payload": {"header_name": "X-Api-Key", "header_value": "secret-value"},
        }
        mock_open_db.return_value = db

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
            "auth_strategy": "static_header",
            "credential_id": "507f1f77bcf86cd799439011",
        })
        result = node.process({"output": "prev"})

        sent_headers = mock_client.request.call_args[1]["headers"]
        assert sent_headers["X-Api-Key"] == "secret-value"
        assert result["output"] == {"ok": True}

    @patch("app.services.credentials_service.get_bearer_token", return_value="bearer-xyz")
    @patch("app.services.credentials_service.validate_outbound_url", return_value="ok")
    @patch("app.services.credentials_service.decrypt_value", side_effect=lambda v: v)
    @patch("app.utils.url_validation.validate_outbound_url")
    @patch("app.services.workflow_engine._open_sync_db")
    @patch("app.services.workflow_engine.httpx.Client")
    def test_oauth_strategy_attaches_bearer(
        self,
        mock_client_cls,
        mock_open_db,
        mock_validate,
        _mock_decrypt,
        _mock_inner_validate,
        _mock_token,
    ):
        mock_validate.return_value = "ok"
        db = MagicMock()
        db.credential.find_one.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "type": "oauth_client_credentials",
            "payload": {
                "client_id": "c",
                "token_endpoint": "https://issuer/token",
                "private_key": "-----BEGIN-----",
            },
        }
        mock_open_db.return_value = db

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.request.return_value = mock_response
        mock_client_cls.return_value = mock_client

        node = APICallNode({
            "url": "https://api.example.com/data",
            "method": "GET",
            "auth_strategy": "oauth_client_credentials",
            "credential_id": "507f1f77bcf86cd799439011",
        })
        result = node.process({"output": "prev"})

        sent_headers = mock_client.request.call_args[1]["headers"]
        assert sent_headers["Authorization"] == "Bearer bearer-xyz"
        assert result["output"] == {"ok": True}


# ---------------------------------------------------------------------------
# FormFillerNode
# ---------------------------------------------------------------------------

class TestFormFillerNode:
    """The form is rendered in Python from a JSON object of values, so the
    template's layout and the missing-value token cannot vary between runs."""

    SEAM = "app.services.workflow_engine._run_form_filler_model"

    @patch(SEAM)
    def test_basic_fill_renders_template_from_values(self, mock_model):
        mock_model.return_value = '{"name": "Alice", "order_id": "123"}'
        node = FormFillerNode({
            "template": "Dear {{name}}, your order #{{order_id}} is ready.",
            "model": "gpt-4o",
        })
        result = node.process({"output": {"name": "Alice", "order_id": "123"}})
        assert result["output"] == "Dear Alice, your order #123 is ready."
        assert result["step_name"] == "FormFiller"
        assert "warning" not in result
        # The model is asked for values only — it never sees the template.
        instructions, prompt = mock_model.call_args.args[1], mock_model.call_args.args[2]
        assert "JSON object" in instructions
        assert '["name", "order_id"]' in prompt
        assert "Dear" not in prompt

    @patch(SEAM)
    def test_missing_values_use_one_token_and_are_listed_on_the_warning(self, mock_model):
        mock_model.return_value = '{"rate": "47%", "cap": null, "basis": ""}'
        node = FormFillerNode({
            "template": "Rate: {{rate}}\nCap: {{cap}}\nBasis: {{basis}}\n\nNotes:",
            "model": "gpt-4o",
        })
        result = node.process({"output": "Indirect rate 47% of MTDC"})
        assert result["output"] == "Rate: 47%\nCap: [Not provided: cap]\nBasis: [Not provided: basis]\n\nNotes:"
        assert result["warning"].startswith("2 fields not found in the input")
        assert "cap, basis" in result["warning"]

    @patch(SEAM)
    def test_missing_token_is_configurable_per_step(self, mock_model):
        mock_model.return_value = '{"a": null}'
        node = FormFillerNode({"template": "A={{a}}", "model": "m", "missing_value": "N/A"})
        result = node.process({"output": "x"})
        assert result["output"] == "A=N/A"
        assert "N/A" in result["warning"]

    @patch(SEAM)
    def test_layout_is_preserved_whatever_the_model_returns(self, mock_model):
        # Extra keys, markdown fences and a repeated placeholder: the template
        # still comes back byte-for-byte except at the placeholders.
        mock_model.return_value = '```json\n{"pi": "Dr. Ada", "extra": "ignored"}\n```'
        template = "# Award\n\nPI: {{ pi }}\n- signed by {{pi}}\n| col | {{pi}} |"
        node = FormFillerNode({"template": template, "model": "m"})
        result = node.process({"output": "PI Dr. Ada"})
        assert result["output"] == "# Award\n\nPI: Dr. Ada\n- signed by Dr. Ada\n| col | Dr. Ada |"

    @patch(SEAM)
    def test_non_json_reply_is_retried_once_then_fails_loudly(self, mock_model):
        mock_model.side_effect = ["Here are the missing fields: rate", "Sorry, still no JSON"]
        node = FormFillerNode({"template": "{{rate}}", "model": "m"})
        with pytest.raises(ValueError, match="did not return placeholder values as JSON"):
            node.process({"output": "x"})
        assert mock_model.call_count == 2
        assert "not a JSON object" in mock_model.call_args.args[2]

    @patch(SEAM)
    def test_template_without_placeholders_fills_freehand_and_warns(self, mock_model):
        mock_model.return_value = "Name: ____ Alice"
        node = FormFillerNode({"template": "Name: ____", "model": "m"})
        result = node.process({"output": "Alice"})
        assert result["output"] == "Name: ____ Alice"
        assert "no {{placeholder}} markers" in result["warning"]
        instructions, prompt = mock_model.call_args.args[1], mock_model.call_args.args[2]
        assert "[Not provided]" in instructions
        assert "TEMPLATE:\nName: ____" in prompt

    @patch(SEAM)
    def test_reports_progress(self, mock_model):
        mock_model.return_value = "filled"
        node = FormFillerNode({"template": "test", "model": "gpt-4o"})
        progress = []
        node.progress_reporter = lambda d=None, p=None: progress.append(d)
        node.process({"output": {}})
        assert any("Filling" in str(p) for p in progress)

    @patch(SEAM)
    def test_document_trigger_uses_doc_texts_not_uuids(self, mock_model):
        mock_model.return_value = '{"title": "AI Safety Initiative"}'
        node = FormFillerNode({
            "template": "Project: {{title}}",
            "model": "gpt-4o",
            "doc_texts": ["Project title: AI Safety Initiative."],
        })
        node.process({
            "step_name": "Document",
            "output": ["d41d8cd98f00b204e9800998ecf8427e"],
        })
        prompt = mock_model.call_args.args[2]
        assert "Project title: AI Safety Initiative." in prompt
        assert "d41d8cd98f00b204e9800998ecf8427e" not in prompt

    @patch(SEAM)
    def test_form_filler_multi_source(self, mock_model):
        """FormFillerNode combines step_input and selected document into labeled context."""
        mock_model.return_value = '{"x": "1"}'
        node = FormFillerNode({
            "template": "{{x}}",
            "model": "gpt-4o",
            "input_sources": ["step_input", "select_document"],
            "selected_doc_text": "doc body",
        })
        node.process({"output": "step output", "step_name": "Prev"})
        prompt = mock_model.call_args.args[2]
        assert "Previous Step Output" in prompt
        assert "Selected Document" in prompt
        assert "step output" in prompt
        assert "doc body" in prompt


    @patch(SEAM)
    def test_prose_non_answers_are_treated_as_missing(self, mock_model):
        """Support ticket: the model answered "Not provided in context" as a
        *value*; it went into the form as if filled in, with no warning, and
        the run completed green."""
        mock_model.return_value = (
            '{"rate": "47%", "cap": "Not provided in context", '
            '"basis": "The document does not mention a basis.", '
            '"pi": "[Not provided]", "dept": "N/A"}'
        )
        node = FormFillerNode({
            "template": "Rate: {{rate}}\nCap: {{cap}}\nBasis: {{basis}}\nPI: {{pi}}\nDept: {{dept}}",
            "model": "gpt-4o",
        })
        result = node.process({"output": "Indirect rate 47% of MTDC"})
        assert result["output"] == (
            "Rate: 47%\nCap: [Not provided: cap]\nBasis: [Not provided: basis]\n"
            "PI: [Not provided: pi]\nDept: [Not provided: dept]"
        )
        assert "Not provided in context" not in result["output"]
        assert result["warning"].startswith("4 fields not found in the input")
        assert "cap, basis, pi, dept" in result["warning"]
        assert "[Not provided: <field>]" in result["warning"]

    @patch(SEAM)
    def test_real_values_that_start_like_a_sentinel_survive(self, mock_model):
        mock_model.return_value = (
            '{"a": "None of the above", "b": "Unknown Author", "c": "Not-for-profit", '
            '"d": "No data was collected after 2020, per the PI"}'
        )
        node = FormFillerNode({"template": "{{a}}|{{b}}|{{c}}|{{d}}", "model": "m"})
        # Every value is present in the input, so the post-fill check has
        # nothing to flag either — the only question is the sentinel prefix.
        result = node.process({"output": (
            "Answer: None of the above. Author: Unknown Author. Status: Not-for-profit. "
            "Note: No data was collected after 2020, per the PI."
        )})
        assert result["output"] == "None of the above|Unknown Author|Not-for-profit|No data was collected after 2020, per the PI"
        assert "warning" not in result

    @patch(SEAM)
    def test_custom_missing_value_is_used_verbatim_for_prose_non_answers_too(self, mock_model):
        mock_model.return_value = '{"a": "unknown", "b": null}'
        node = FormFillerNode({"template": "A={{a}} B={{b}}", "model": "m", "missing_value": "___"})
        result = node.process({"output": "x"})
        assert result["output"] == "A=___ B=___"
        assert "marked ___ in the form" in result["warning"]

    @patch(SEAM)
    def test_freeform_fill_counts_the_blanks_it_could_not_fill(self, mock_model):
        mock_model.return_value = (
            "Name: Alice\nDate: [Not provided]\nSponsor: Not provided in context\nAmount: $5"
        )
        node = FormFillerNode({"template": "Name: ___\nDate: ___\nSponsor: ___\nAmount: ___", "model": "m"})
        result = node.process({"output": "Alice, $5"})
        assert result["warning"].startswith("2 blanks could not be filled from the input")
        assert "no {{placeholder}} markers" in result["warning"]

    @patch(SEAM)
    def test_freeform_fill_with_every_blank_filled_only_warns_about_markers(self, mock_model):
        mock_model.return_value = "Name: Alice\nAmount: $5"
        node = FormFillerNode({"template": "Name: ___\nAmount: ___", "model": "m"})
        result = node.process({"output": "Alice, $5"})
        assert result["warning"].startswith("This template has no {{placeholder}} markers")


class TestFormFillerHelpers:
    def test_placeholders_are_deduplicated_in_order(self):
        from app.services.workflow_engine import template_placeholders
        assert template_placeholders("{{b}} {{ a }} {{b}} {{c}}") == ["b", "a", "c"]

    def test_render_substitutes_and_reports_missing(self):
        from app.services.workflow_engine import render_filled_template
        text, missing = render_filled_template("{{a}}-{{b}}-{{a}}", {"a": "1"})
        assert text == "1-[Not provided: b]-1"
        assert missing == ["b"]

    def test_render_keeps_values_verbatim(self):
        from app.services.workflow_engine import render_filled_template
        text, _ = render_filled_template("{{v}}", {"v": "47 % of modified total direct costs"})
        assert text == "47 % of modified total direct costs"



# ---------------------------------------------------------------------------
# PackageBuilderNode
# ---------------------------------------------------------------------------


    @pytest.mark.parametrize("value", [
        None, "", "   ", "N/A", "n/a", "N.A.", "none", "Null", "unknown", "—", "--", "TBD",
        "Not provided", "Not provided.", "Not provided in context", "Not provided in the context.",
        "not specified in the document", "Not available", "Not found in the input",
        "[Not provided]", "[Not provided: cap]", "(not stated)", "No information available",
        "The context does not contain this information.", "The document doesn't mention it",
        "Information does not specify a rate", "Not applicable", "Missing", "Not in the document",
    ])
    def test_form_value_is_missing_for_nullish_values(self, value):
        from app.services.workflow_engine import form_value_is_missing
        assert form_value_is_missing(value) is True

    @pytest.mark.parametrize("value", [
        "47%", "0", "None of the above", "Unknown Author", "Not-for-profit",
        "Nonesuch Ltd", "Not less than 10%", "No data was collected after 2020, per the PI",
        "Blankenship", "Missing Persons Act", "N/A-123", "TBD Holdings LLC",
    ])
    def test_form_value_is_missing_leaves_real_values_alone(self, value):
        from app.services.workflow_engine import form_value_is_missing
        assert form_value_is_missing(value) is False

    def test_form_missing_marker_names_the_field_unless_overridden(self):
        from app.services.workflow_engine import form_missing_marker
        assert form_missing_marker("applicant_name") == "[Not provided: applicant_name]"
        assert form_missing_marker("applicant_name", "N/A") == "N/A"

    def test_count_unfilled_freeform(self):
        from app.services.workflow_engine import count_unfilled_freeform
        assert count_unfilled_freeform("") == 0
        assert count_unfilled_freeform("A: x\nB: y") == 0
        assert count_unfilled_freeform("A: [Not provided]\nB: not specified in the document\nC: ___") == 2
        assert count_unfilled_freeform("A: ___\nB: [Not provided]", "___") == 2


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

    def test_empty_kb_uuid_is_a_step_error(self):
        """Configuration errors halt the run (like Add Website): a warning
        let the run finish Completed with a step that queried nothing."""
        node = KnowledgeBaseQueryNode({"kb_uuid": "", "query": "test"})
        result = node.process({"output": "prev"})
        assert result["output"] == ""
        assert "no knowledge base selected" in result["error"]

    def test_empty_query_is_a_step_error(self):
        node = KnowledgeBaseQueryNode({"kb_uuid": "kb-123", "query": ""})
        result = node.process({"output": "prev"})
        assert result["output"] == ""
        assert "query is empty" in result["error"]

    @patch("app.services.document_manager.DocumentManager")
    def test_no_results(self, mock_dm_cls):
        """An empty result set surfaces a warning and an explicit output
        message instead of silently feeding "" to the next step."""
        mock_dm = MagicMock()
        mock_dm.query_kb.return_value = []
        mock_dm_cls.return_value = mock_dm

        node = KnowledgeBaseQueryNode({"kb_uuid": "kb-123", "query": "obscure"})
        result = node.process({"output": "prev"})
        assert "no matching passages" in result["output"]
        assert "obscure" in result["warning"]

    @patch("app.services.document_manager.DocumentManager")
    def test_passages_output_has_framing_header(self, mock_dm_cls):
        """Downstream LLM steps are told the chunks are partial retrieval
        excerpts, mirroring the framing the chat RAG path uses."""
        mock_dm = MagicMock()
        mock_dm.query_kb.return_value = [
            {"content": "Chunk text", "metadata": {"source_name": "doc.pdf"}},
        ]
        mock_dm_cls.return_value = mock_dm

        node = KnowledgeBaseQueryNode({"kb_uuid": "kb-1", "query": "anything"})
        result = node.process({"output": "prev"})
        assert "partial excerpts" in result["output"]
        assert "Chunk text" in result["output"]

    @patch("app.services.document_manager.DocumentManager")
    def test_templated_query_uses_previous_output(self, mock_dm_cls):
        mock_dm = MagicMock()
        mock_dm.query_kb.return_value = []
        mock_dm_cls.return_value = mock_dm

        node = KnowledgeBaseQueryNode({
            "kb_uuid": "kb-1",
            "query": "policies for {{ inputs.output }}",
        })
        node.process({"output": "NSF", "step_name": "Extraction"})

        mock_dm.query_kb.assert_called_once_with("kb-1", "policies for NSF", k=8)

    def test_template_error_is_a_step_error(self):
        """A broken template is a configuration error; its message must fail
        the run, not become the step's output."""
        node = KnowledgeBaseQueryNode({
            "kb_uuid": "kb-1",
            "query": "{{ inputs.output.missing_key }}",
        })
        result = node.process({"output": {"other": 1}, "step_name": "Prompt"})
        assert result["error"]
        assert result["output"] == ""

    @patch("app.services.document_manager.DocumentManager")
    def test_min_similarity_filters_low_relevance_chunks(self, mock_dm_cls):
        mock_dm = MagicMock()
        mock_dm.query_kb.return_value = [
            {"content": "Relevant", "metadata": {"source_name": "a.pdf"}, "similarity": 0.8},
            {"content": "Junk", "metadata": {"source_name": "b.pdf"}, "similarity": 0.05},
        ]
        mock_dm_cls.return_value = mock_dm

        node = KnowledgeBaseQueryNode({
            "kb_uuid": "kb-1", "query": "q", "min_similarity": "0.3",
        })
        result = node.process({"output": "prev"})
        assert "Relevant" in result["output"]
        assert "Junk" not in result["output"]
        assert len(result["retrieved_sources"]) == 1

    @patch("app.services.document_manager.DocumentManager")
    def test_min_similarity_filtering_everything_warns(self, mock_dm_cls):
        mock_dm = MagicMock()
        mock_dm.query_kb.return_value = [
            {"content": "Junk", "metadata": {"source_name": "b.pdf"}, "similarity": 0.05},
        ]
        mock_dm_cls.return_value = mock_dm

        node = KnowledgeBaseQueryNode({
            "kb_uuid": "kb-1", "query": "q", "min_similarity": 0.5,
        })
        result = node.process({"output": "prev"})
        assert "no matching passages" in result["warning"]

    @patch("app.services.document_manager.DocumentManager")
    def test_query_error_hard_fails_the_step(self, mock_dm_cls):
        """Reversal of the earlier soft-fail (#805): the warning let the run
        finish Completed while the failure text flowed downstream as the next
        step's INPUT — a workflow summarizing "Knowledge base lookup failed:
        chroma down" as if it were retrieved content."""
        mock_dm = MagicMock()
        mock_dm.query_kb.side_effect = RuntimeError("chroma down")
        mock_dm_cls.return_value = mock_dm

        node = KnowledgeBaseQueryNode({"kb_uuid": "kb-1", "query": "q"})
        result = node.process({"output": "prev"})
        assert "chroma down" in result["error"]
        assert result["output"] == ""

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.DocumentManager")
    def test_answer_mode_synthesizes_grounded_answer(self, mock_dm_cls, mock_llm):
        mock_dm = MagicMock()
        mock_dm.query_kb.return_value = [
            {"content": "Cost share is 50%", "metadata": {"source_name": "PAPPG.pdf", "page": 234}},
        ]
        mock_dm_cls.return_value = mock_dm
        mock_llm.return_value = "Cost share is 50% [PAPPG.pdf · p. 234]"

        node = KnowledgeBaseQueryNode({
            "kb_uuid": "kb-1",
            "query": "What is the cost share?",
            "mode": "answer",
            "model": "gpt-4o",
        })
        result = node.process({"output": "prev"})

        assert result["output"] == "Cost share is 50% [PAPPG.pdf · p. 234]"
        # Citations still flow even when the output is a synthesized answer.
        assert result["retrieved_sources"][0]["document_title"] == "PAPPG.pdf"
        call = mock_llm.call_args
        assert call.kwargs["model"] == "gpt-4o"
        assert "QUESTION:\nWhat is the cost share?" in call.kwargs["prompt"]
        assert "Cost share is 50%" in call.kwargs["data"]

    @patch("app.services.workflow_engine.llm_chat_model")
    @patch("app.services.document_manager.DocumentManager")
    def test_passages_mode_makes_no_llm_call(self, mock_dm_cls, mock_llm):
        mock_dm = MagicMock()
        mock_dm.query_kb.return_value = [
            {"content": "Chunk", "metadata": {"source_name": "a.pdf"}},
        ]
        mock_dm_cls.return_value = mock_dm

        node = KnowledgeBaseQueryNode({"kb_uuid": "kb-1", "query": "q"})
        node.process({"output": "prev"})
        mock_llm.assert_not_called()

    @patch("app.services.document_manager.DocumentManager")
    def test_emits_retrieved_sources_with_page_and_score(self, mock_dm_cls):
        """The KB node returns a structured citation list for the workflow
        result to persist, in addition to the joined prompt text."""
        mock_dm = MagicMock()
        mock_dm.query_kb.return_value = [
            {
                "content": "Section II.D — cost share",
                "metadata": {"source_id": "src-1", "source_name": "PAPPG.pdf", "page": 234},
                "chunk_id": "src-1_chunk_47",
                "score": 0.12,
            },
            {
                "content": "Q1 budget row",
                "metadata": {"source_id": "src-2", "source_name": "Budget.xlsx", "sheet": "Year 1"},
                "chunk_id": "src-2_chunk_3",
                "score": 0.19,
            },
        ]
        mock_dm_cls.return_value = mock_dm

        node = KnowledgeBaseQueryNode({"kb_uuid": "kb-1", "query": "cost share"})
        result = node.process({"output": "prev"})

        # Prompt-side: cited label appears in the joined output text.
        assert "p. 234" in result["output"]
        assert "Year 1" in result["output"]

        # Citation-side: each result becomes a retrieved_sources entry.
        sources = result["retrieved_sources"]
        assert len(sources) == 2
        assert sources[0]["document_title"] == "PAPPG.pdf"
        assert sources[0]["page"] == 234
        assert sources[0]["sheet"] is None
        assert sources[0]["chunk_id"] == "src-1_chunk_47"
        assert sources[0]["score"] == 0.12
        assert sources[1]["sheet"] == "Year 1"
        assert sources[1]["page"] is None


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


# ---------------------------------------------------------------------------
# FormFillerNode — fill check, sources, and fillable PDF templates
# ---------------------------------------------------------------------------

class TestFormFillerFillReport:
    """After filling, every value is checked against the inputs and attributed
    to a document and page; unfilled or unsupported values become warnings."""

    SEAM = "app.services.workflow_engine._run_form_filler_model"
    DOC = "Indirect cost rate: 47.5% of MTDC.\n\fPI: Dr. Ada Lovelace"
    MARKERS = [{"char_offset": 0, "kind": "page", "value": 1},
               {"char_offset": DOC.index("\f"), "kind": "page", "value": 2}]

    @patch(SEAM)
    def test_report_attributes_values_to_document_and_page(self, mock_model):
        mock_model.return_value = '{"rate": "47.5%", "pi": "Dr. Ada Lovelace", "eur": "EUR 4,000", "cap": null}'
        node = FormFillerNode({
            "template": "Rate {{rate}} PI {{pi}} EUR {{eur}} Cap {{cap}}",
            "model": "m",
            "doc_texts": [self.DOC],
            "doc_metas": [{"uuid": "D1", "title": "Award.pdf", "text_markers": self.MARKERS}],
        })
        result = node.process({"step_name": "Document", "output": ["D1"]})

        by = {e["name"]: e for e in result["fill_report"]}
        assert by["rate"]["status"] == "supported"
        assert (by["rate"]["document_title"], by["rate"]["page"]) == ("Award.pdf", 1)
        assert (by["pi"]["document_uuid"], by["pi"]["page"]) == ("D1", 2)
        assert by["eur"]["status"] == "unsupported"
        assert by["cap"]["status"] == "missing"
        assert result["output"] == "Rate 47.5% PI Dr. Ada Lovelace EUR EUR 4,000 Cap [Not provided: cap]"
        assert "1 field not found in the input and marked [Not provided: <field>] in the form — fill in or remove before using it: cap" in result["warning"]
        assert "eur ('EUR 4,000')" in result["warning"]
        assert "may be invented or reformatted" in result["warning"]

    @patch(SEAM)
    def test_clean_fill_has_report_but_no_warning(self, mock_model):
        mock_model.return_value = '{"rate": "47.5%"}'
        node = FormFillerNode({"template": "{{rate}}", "model": "m"})
        result = node.process({"output": "The rate is 47.5% of MTDC", "step_name": "Prev"})
        assert "warning" not in result
        [entry] = result["fill_report"]
        assert entry["status"] == "supported"
        assert entry["document_title"] == "Previous Step Output"

    @patch(SEAM)
    def test_sentinel_from_model_is_rendered_as_missing_token(self, mock_model):
        mock_model.return_value = '{"a": "Not provided", "b": "n/a"}'
        node = FormFillerNode({"template": "{{a}}|{{b}}", "model": "m"})
        result = node.process({"output": "x", "step_name": "Prev"})
        assert result["output"] == "[Not provided: a]|[Not provided: b]"
        assert result["warning"].startswith("2 fields not found")

    @patch(SEAM)
    def test_selected_document_meta_is_used_for_attribution(self, mock_model):
        mock_model.return_value = '{"pi": "Dr. Ada Lovelace"}'
        node = FormFillerNode({
            "template": "{{pi}}", "model": "m",
            "input_sources": ["select_document"],
            "selected_doc_text": self.DOC,
            "selected_doc_meta": {"uuid": "S1", "title": "Selected.pdf", "text_markers": self.MARKERS},
        })
        result = node.process({"output": "ignored", "step_name": "Prev"})
        [entry] = result["fill_report"]
        assert (entry["document_uuid"], entry["document_title"], entry["page"]) == ("S1", "Selected.pdf", 2)


def _fillable_pdf_b64() -> str:
    import base64

    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((20, 25), "Principal Investigator")
    w = fitz.Widget(); w.field_name = "pi_name"; w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(150, 10, 400, 30); page.add_widget(w)
    w = fitz.Widget(); w.field_name = "human_subjects"; w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.rect = fitz.Rect(150, 40, 170, 60); page.add_widget(w)
    w = fitz.Widget(); w.field_name = "rate"; w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(150, 70, 400, 90); page.add_widget(w)
    return base64.b64encode(doc.tobytes()).decode("ascii")


class TestFormFillerPdfTemplate:
    SEAM = "app.services.workflow_engine._run_form_filler_model"

    @patch(SEAM)
    def test_fills_the_pdf_fields_and_returns_the_file(self, mock_model):
        import base64

        import fitz

        mock_model.return_value = '{"pi_name": "Dr. Ada Lovelace", "human_subjects": true, "rate": "99%"}'
        node = FormFillerNode({
            "template_source": "pdf",
            "template_pdf_b64": _fillable_pdf_b64(),
            "template_document_title": "NSF Cover.pdf",
            "model": "m",
        })
        result = node.process({"output": "PI: Dr. Ada Lovelace. Rate 47.5%.", "step_name": "Prev"})

        out = result["output"]
        assert out["type"] == "file_download" and out["file_type"] == "pdf"
        assert out["filename"] == "NSF Cover-filled.pdf"
        filled = fitz.open(stream=base64.b64decode(out["data_b64"]), filetype="pdf")
        values = {w.field_name: w.field_value for w in filled[0].widgets()}
        assert values == {"pi_name": "Dr. Ada Lovelace", "human_subjects": "Yes", "rate": "99%"}

        # The model got the fields with their labels, never a template.
        instructions, prompt = mock_model.call_args.args[1], mock_model.call_args.args[2]
        assert "PDF forms" in instructions
        assert '"label": "Principal Investigator"' in prompt
        assert "CONTEXT:\nPI: Dr. Ada Lovelace" in prompt

        by = {e["name"]: e for e in result["fill_report"]}
        assert by["pi_name"]["status"] == "supported" and by["pi_name"]["label"] == "Principal Investigator"
        assert by["rate"]["status"] == "unsupported"
        assert result["filled_values"] == {"pi_name": "Dr. Ada Lovelace", "human_subjects": True, "rate": "99%"}
        assert "rate ('99%')" in result["warning"]

    @patch(SEAM)
    def test_missing_values_leave_fields_blank_and_warn(self, mock_model):
        mock_model.return_value = '{"pi_name": null, "human_subjects": null, "rate": "47.5%"}'
        node = FormFillerNode({"template_source": "pdf", "template_pdf_b64": _fillable_pdf_b64(), "model": "m"})
        result = node.process({"output": "Rate 47.5%", "step_name": "Prev"})
        assert "2 fields not found in the input and left blank in the form — fill in before using it: pi_name, human_subjects" in result["warning"]
        assert "[Not provided]" not in json.dumps(result["fill_report"])

    @patch(SEAM)
    def test_unwritable_value_is_reported_not_written(self, mock_model):
        mock_model.return_value = '{"pi_name": "Ada", "human_subjects": "maybe", "rate": null}'
        node = FormFillerNode({"template_source": "pdf", "template_pdf_b64": _fillable_pdf_b64(), "model": "m"})
        result = node.process({"output": "PI Ada", "step_name": "Prev"})
        by = {e["name"]: e for e in result["fill_report"]}
        assert by["human_subjects"]["status"] == "not_written"
        assert "checkbox needs true/false" in by["human_subjects"]["reason"]
        assert "1 form field could not be set: human_subjects" in result["warning"]

    @patch(SEAM)
    def test_template_load_error_fails_the_step_without_calling_the_model(self, mock_model):
        node = FormFillerNode({
            "template_source": "pdf",
            "template_load_error": "The template document 'x' is not a PDF (.docx).",
            "model": "m",
        })
        result = node.process({"output": "x", "step_name": "Prev"})
        mock_model.assert_not_called()
        assert result["error"] == "Form Filler: The template document 'x' is not a PDF (.docx)."
        assert result["output"] == ""

    @patch(SEAM)
    def test_pdf_without_form_fields_fails_the_step(self, mock_model):
        import base64

        import fitz

        doc = fitz.open(); doc.new_page().insert_text((20, 20), "flat scan")
        node = FormFillerNode({
            "template_source": "pdf",
            "template_pdf_b64": base64.b64encode(doc.tobytes()).decode(),
            "template_document_title": "scan.pdf",
            "model": "m",
        })
        result = node.process({"output": "x", "step_name": "Prev"})
        mock_model.assert_not_called()
        assert "'scan.pdf' has no fillable form fields" in result["error"]

    @patch(SEAM)
    def test_pdf_mode_without_loaded_template_fails(self, mock_model):
        node = FormFillerNode({"template_source": "pdf", "model": "m"})
        result = node.process({"output": "x", "step_name": "Prev"})
        assert "no template PDF was loaded" in result["error"]


class TestFormFillerReportSurvivesTheStepWrapper:
    """Every node runs inside a MultiTaskNode, and the engine persists that
    wrapper's result under ``steps_output`` — which is where the run UI reads
    ``fill_report``. The wrapper used to keep only output/warning/sources, so
    the per-field table never reached the client."""

    SEAM = "app.services.workflow_engine._run_form_filler_model"

    @patch(SEAM)
    def test_fill_report_reaches_steps_output(self, mock_model):
        from app.services.workflow_engine import WorkflowEngine

        mock_model.return_value = '{"rate": "47.5%", "cap": null}'
        node = FormFillerNode({"template": "{{rate}} {{cap}}", "model": "m"})
        wrapper = MultiTaskNode("Fill")
        wrapper.add_task(node)

        wrapped = wrapper.process({"output": "The rate is 47.5% of MTDC", "step_name": "Prev"})
        assert [e["status"] for e in wrapped["fill_report"]] == ["supported", "missing"]
        assert wrapped["warning"].startswith("1 field not found")

        engine = WorkflowEngine()
        engine.add_node(wrapper)
        persisted: dict = {}
        engine.execute(
            initial_output={"output": "The rate is 47.5% of MTDC", "step_name": "Prev"},
            workflow_result_updater=persisted.update,
        )
        step_outputs = [v for k, v in persisted.items() if k.startswith("steps_output.")]
        assert step_outputs and isinstance(step_outputs[-1].get("fill_report"), list)
        assert step_outputs[-1]["fill_report"][0]["document_title"] == "Previous Step Output"

# ---------------------------------------------------------------------------
# ResearchNode (Deep Analysis) — empty input must not fabricate a report
# ---------------------------------------------------------------------------

class TestResearchNodeEmptyInput:
    """A Deep Analysis step with nothing to analyze used to run both passes in
    the chat helper's standalone mode and hand back a confident, invented
    report (figures, deadlines, regulation citations) marked Completed. With
    no data it must not call the model at all, and must say so on the step."""

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_empty_step_input_skips_model_and_warns(self, mock_llm):
        node = ResearchNode({"question": "What are the risks?", "model": "gpt-4o"})
        result = node.process({"output": "", "step_name": "Prev"})

        mock_llm.assert_not_called()
        assert result["step_name"] == "ResearchNode"
        assert "no input data to analyze" in result["warning"]
        assert "Previous Step Output" in result["warning"]
        assert "no input data to analyze" in result["output"]
        assert "Executive Summary" not in result["output"]

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_missing_output_key_skips_model_and_warns(self, mock_llm):
        node = ResearchNode({"question": "Q?", "model": "gpt-4o"})
        result = node.process({"step_name": "Prev"})
        mock_llm.assert_not_called()
        assert "warning" in result

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_whitespace_only_input_skips_model(self, mock_llm):
        node = ResearchNode({"question": "Q?", "model": "gpt-4o"})
        result = node.process({"output": "   \n\t ", "step_name": "Prev"})
        mock_llm.assert_not_called()
        assert "warning" in result

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_all_sources_empty_skips_model(self, mock_llm):
        node = ResearchNode({
            "question": "Q?",
            "model": "gpt-4o",
            "input_sources": ["step_input", "workflow_documents", "select_document"],
            "doc_texts": [],
            "selected_doc_text": "",
        })
        result = node.process({"output": None, "step_name": "Prev"})
        mock_llm.assert_not_called()
        assert "Workflow Documents" in result["warning"]

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_empty_step_input_but_document_present_still_runs(self, mock_llm):
        """Only the *combined* context being empty is a skip — a document source
        that has text is enough to analyze even if the previous step was blank."""
        mock_llm.side_effect = ["findings", "report"]
        node = ResearchNode({
            "question": "Q?",
            "model": "gpt-4o",
            "input_sources": ["step_input", "workflow_documents"],
            "doc_texts": ["award terms and conditions"],
        })
        result = node.process({"output": "", "step_name": "Prev"})
        assert mock_llm.call_count == 2
        assert result["output"] == "report"
        assert "warning" not in result

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_empty_input_surfaces_as_step_warning_in_engine(self, mock_llm):
        """End to end through the engine: the skip lands on the step entry's
        ``warning`` (what the run UI renders as the amber banner) and the run
        does not fail."""
        from app.services.workflow_engine import WorkflowEngine

        first = PromptNode({"prompt": "say nothing", "model": "gpt-4o"})
        research = ResearchNode({"question": "Q?", "model": "gpt-4o"})
        mock_llm.side_effect = [""]  # Prompt step yields nothing; research must not call
        engine = WorkflowEngine()
        engine.add_node(first)
        engine.add_node(research)
        engine.connect(first, research)

        final, steps = engine.execute()

        assert mock_llm.call_count == 1
        assert steps[-1]["name"] == "ResearchNode"
        assert "no input data to analyze" in steps[-1]["warning"]
        assert "no input data to analyze" in final


class TestResearchNodeNoRelevantFindings:
    """Pass 1 is asked to lead with NO_RELEVANT_FINDINGS when the input has
    nothing on the question. That must stop the step before pass 2 — which,
    asked for a four-section report, would fill the sections regardless."""

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_sentinel_skips_pass_two_and_warns(self, mock_llm):
        mock_llm.side_effect = [
            "NO_RELEVANT_FINDINGS\nThe data is a parking permit application and says nothing about award finances."
        ]
        node = ResearchNode({"question": "What are the budget risks?", "model": "gpt-4o"})
        result = node.process({"output": "Parking permit application ...", "step_name": "Prev"})

        assert mock_llm.call_count == 1
        assert "nothing in its input relevant to the question" in result["warning"]
        assert "parking permit" in result["warning"]
        assert "Executive Summary" not in result["output"]
        assert result["output"].startswith("(")

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_sentinel_wrapped_in_markdown_still_detected(self, mock_llm):
        mock_llm.side_effect = ["**NO_RELEVANT_FINDINGS** — nothing here."]
        node = ResearchNode({"question": "Q?", "model": "gpt-4o"})
        result = node.process({"output": "x", "step_name": "Prev"})
        assert mock_llm.call_count == 1
        assert result["warning"].endswith("nothing here.")

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_sentinel_mid_text_is_not_a_declaration(self, mock_llm):
        mock_llm.side_effect = [
            "Finding 1: budget is $2M. (Would have said NO_RELEVANT_FINDINGS otherwise.)",
            "report",
        ]
        node = ResearchNode({"question": "Q?", "model": "gpt-4o"})
        result = node.process({"output": "x", "step_name": "Prev"})
        assert mock_llm.call_count == 2
        assert result["output"] == "report"
        assert "warning" not in result

    @patch("app.services.workflow_engine.llm_chat_model")
    def test_prompts_carry_grounding_instructions(self, mock_llm):
        mock_llm.side_effect = ["findings", "report"]
        node = ResearchNode({"question": "Q?", "model": "gpt-4o"})
        node.process({"output": "x", "step_name": "Prev"})
        pass1 = mock_llm.call_args_list[0].kwargs["prompt"]
        pass2 = mock_llm.call_args_list[1].kwargs["prompt"]
        assert "NO_RELEVANT_FINDINGS" in pass1
        assert "general knowledge" in pass1
        assert "must come from the Findings below or the CONTEXT" in pass2
        assert "Findings:\nfindings" in pass2


class TestDataExportNonTabularCsv:
    """#812: a non-tabular input was written as str(input_data) and still
    labelled .csv — a prose blob Excel opens without complaint."""

    def test_prose_input_exports_as_text_with_a_warning(self):
        node = DataExportNode({"format": "csv", "filename": "report"})
        result = node.process({"output": "The award totals $485,000 for year one."})

        assert result["output"]["file_type"] == "txt"
        assert result["output"]["filename"] == "report.txt"
        assert "not tabular" in result["warning"]
        decoded = base64.b64decode(result["output"]["data_b64"]).decode()
        assert "485,000" in decoded

    def test_tabular_input_is_still_csv(self):
        node = DataExportNode({"format": "csv", "filename": "rows"})
        result = node.process({"output": [{"a": "1", "b": "2"}]})
        assert result["output"]["file_type"] == "csv"
        assert result["output"]["filename"] == "rows.csv"
        assert "warning" not in result
