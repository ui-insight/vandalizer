"""Tests for workflow engine pure functions — step name sanitization,
HTML text extraction, output formatting, and node contracts."""

import base64
import json

from app.services.workflow_engine import (
    DocumentNode,
    AddDocumentNode,
    DataExportNode,
    DocumentRendererNode,
    WorkflowEngine,
    _extract_text_from_html,
    _stringify_value,
    format_extraction_results,
    sanitize_step_name,
)


# ---------------------------------------------------------------------------
# sanitize_step_name — prevents MongoDB operator injection via . and $
# ---------------------------------------------------------------------------

class TestSanitizeStepName:
    def test_dots_replaced(self):
        assert sanitize_step_name("foo.bar") == "foo_bar"

    def test_dollars_replaced(self):
        assert sanitize_step_name("$where") == "where"

    def test_multiple_special_chars(self):
        assert sanitize_step_name("$foo.bar$") == "foo_bar"

    def test_whitespace_collapsed(self):
        assert sanitize_step_name("hello   world") == "hello_world"

    def test_double_underscores_collapsed(self):
        assert sanitize_step_name("step__name") == "step_name"

    def test_empty_string_returns_step(self):
        assert sanitize_step_name("") == "step"

    def test_only_special_chars_returns_step(self):
        assert sanitize_step_name("$.$") == "step"

    def test_whitespace_only_returns_step(self):
        assert sanitize_step_name("   ") == "step"

    def test_leading_trailing_underscores_stripped(self):
        assert sanitize_step_name("_name_") == "name"

    def test_normal_name_unchanged(self):
        assert sanitize_step_name("Extraction") == "Extraction"

    def test_tabs_and_newlines(self):
        assert sanitize_step_name("step\t\nname") == "step_name"


# ---------------------------------------------------------------------------
# _extract_text_from_html — strips dangerous tags, normalizes whitespace
# ---------------------------------------------------------------------------

class TestExtractTextFromHtml:
    def test_basic_text(self):
        assert _extract_text_from_html("<p>Hello world</p>") == "Hello world"

    def test_script_tags_removed(self):
        html = "<p>Text</p><script>alert('xss')</script><p>More</p>"
        result = _extract_text_from_html(html)
        assert "alert" not in result
        assert "Text" in result
        assert "More" in result

    def test_style_tags_removed(self):
        html = "<style>.foo{color:red}</style><p>Content</p>"
        result = _extract_text_from_html(html)
        assert "color" not in result
        assert "Content" in result

    def test_nav_footer_header_removed(self):
        html = "<nav>NavBar</nav><main>Main Content</main><footer>Footer</footer>"
        result = _extract_text_from_html(html)
        assert "NavBar" not in result
        assert "Footer" not in result
        assert "Main Content" in result

    def test_form_tags_removed(self):
        html = "<form><input type='text' value='secret'/></form><p>Visible</p>"
        result = _extract_text_from_html(html)
        assert "secret" not in result
        assert "Visible" in result

    def test_whitespace_normalized(self):
        html = "<p>  lots   of    spaces  </p>"
        result = _extract_text_from_html(html)
        assert "  " not in result  # no double spaces
        assert "lots of spaces" in result

    def test_excessive_newlines_collapsed(self):
        html = "<p>A</p><p></p><p></p><p></p><p>B</p>"
        result = _extract_text_from_html(html)
        assert "\n\n\n" not in result

    def test_empty_html(self):
        assert _extract_text_from_html("") == ""

    def test_aside_removed(self):
        html = "<aside>Sidebar</aside><article>Article</article>"
        result = _extract_text_from_html(html)
        assert "Sidebar" not in result
        assert "Article" in result


# ---------------------------------------------------------------------------
# format_extraction_results / _stringify_value
# ---------------------------------------------------------------------------

class TestStringifyValue:
    def test_none_returns_na(self):
        assert _stringify_value(None) == "N/A"

    def test_string_passthrough(self):
        assert _stringify_value("hello") == "hello"

    def test_int_to_string(self):
        assert _stringify_value(42) == "42"

    def test_list_joined(self):
        assert _stringify_value(["a", "b", "c"]) == "a, b, c"

    def test_list_with_none_filtered(self):
        assert _stringify_value(["a", None, "b"]) == "a, b"

    def test_dict_to_json(self):
        result = _stringify_value({"key": "val"})
        assert json.loads(result) == {"key": "val"}


class TestFormatExtractionResults:
    def test_none_returns_empty(self):
        assert format_extraction_results(None) == ""

    def test_single_dict(self):
        result = format_extraction_results({"Name": "Alice", "Age": "30"})
        assert "**Name**" in result
        assert "Alice" in result
        assert "**Age**" in result
        assert "30" in result

    def test_list_of_dicts(self):
        result = format_extraction_results([
            {"Name": "Alice"},
            {"Name": "Bob"},
        ])
        assert "Result 1" in result
        assert "Result 2" in result
        assert "Alice" in result
        assert "Bob" in result

    def test_single_item_list_no_result_header(self):
        result = format_extraction_results([{"Name": "Alice"}])
        assert "Result" not in result
        assert "Alice" in result

    def test_scalar_value(self):
        result = format_extraction_results("just a string")
        assert result == "just a string"

    def test_empty_list(self):
        result = format_extraction_results([])
        assert result == ""


# ---------------------------------------------------------------------------
# WorkflowEngine._format_final_output
# ---------------------------------------------------------------------------

class TestFormatFinalOutput:
    def setup_method(self):
        self.engine = WorkflowEngine()

    def test_none_returns_empty_string(self):
        assert self.engine._format_final_output(None) == ""

    def test_string_passthrough(self):
        assert self.engine._format_final_output("hello") == "hello"

    def test_int_converted_to_string(self):
        assert self.engine._format_final_output(42) == "42"

    def test_single_item_dict_list_unwrapped(self):
        result = self.engine._format_final_output([{"key": "val"}])
        parsed = json.loads(result)
        assert parsed == {"key": "val"}

    def test_multi_item_list_gets_headers(self):
        result = self.engine._format_final_output(["first", "second"])
        assert "### Result 1" in result
        assert "### Result 2" in result

    def test_file_download_dict_passthrough(self):
        download = {"type": "file_download", "data_b64": "abc", "filename": "out.csv"}
        result = self.engine._format_final_output(download)
        assert result == download

    def test_regular_dict_to_json(self):
        result = self.engine._format_final_output({"key": "val"})
        assert json.loads(result) == {"key": "val"}

    def test_empty_list(self):
        assert self.engine._format_final_output([]) == ""

    def test_list_item_starting_with_heading_no_extra_header(self):
        result = self.engine._format_final_output(["# Title", "other"])
        assert "### Result" not in result.split("# Title")[0]  # Title not re-wrapped


# ---------------------------------------------------------------------------
# Node contracts — DocumentNode, AddDocumentNode, DataExportNode
# ---------------------------------------------------------------------------

class TestDocumentNode:
    def test_output_contains_uuids(self):
        node = DocumentNode({"doc_uuids": ["uuid1", "uuid2"]})
        result = node.process()
        assert result["output"] == ["uuid1", "uuid2"]
        assert result["step_name"] == "Document"
        assert result["input"] is None

    def test_empty_uuids(self):
        node = DocumentNode({})
        result = node.process()
        assert result["output"] == []


class TestAddDocumentNode:
    def test_joins_doc_texts(self):
        node = AddDocumentNode({"doc_texts": ["Hello", "World"]})
        result = node.process({"output": None})
        assert result["output"] == "Hello\nWorld"
        assert result["step_name"] == "AddDocument"

    def test_empty_texts(self):
        node = AddDocumentNode({})
        result = node.process({"output": None})
        assert result["output"] == ""


class TestDataExportNode:
    def test_json_export(self):
        node = DataExportNode({"format": "json", "filename": "test"})
        result = node.process({"output": {"key": "value"}})
        output = result["output"]
        assert output["type"] == "file_download"
        assert output["file_type"] == "json"
        assert output["filename"] == "test.json"
        decoded = base64.b64decode(output["data_b64"]).decode()
        assert json.loads(decoded) == {"key": "value"}

    def test_csv_export_list_of_dicts(self):
        data = [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]
        node = DataExportNode({"format": "csv", "filename": "people"})
        result = node.process({"output": data})
        output = result["output"]
        assert output["file_type"] == "csv"
        decoded = base64.b64decode(output["data_b64"]).decode()
        assert "name" in decoded  # header row
        assert "Alice" in decoded
        assert "Bob" in decoded

    def test_csv_export_single_dict(self):
        node = DataExportNode({"format": "csv", "filename": "single"})
        result = node.process({"output": {"a": "1", "b": "2"}})
        decoded = base64.b64decode(result["output"]["data_b64"]).decode()
        assert "a" in decoded
        assert "1" in decoded


class TestDocumentRendererNode:
    def test_markdown_render(self):
        node = DocumentRendererNode({"format": "md", "filename": "report"})
        result = node.process({"output": "# Hello"})
        output = result["output"]
        assert output["type"] == "file_download"
        assert output["file_type"] == "md"
        assert output["filename"] == "report.md"
        decoded = base64.b64decode(output["data_b64"]).decode()
        assert decoded == "# Hello"

    def test_dict_input_serialized_to_json(self):
        node = DocumentRendererNode({"format": "txt", "filename": "out"})
        result = node.process({"output": {"k": "v"}})
        decoded = base64.b64decode(result["output"]["data_b64"]).decode()
        assert json.loads(decoded) == {"k": "v"}
