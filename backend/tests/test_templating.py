"""Tests for app.utils.templating — the {{ inputs.output }} substitution used
by workflow API nodes to reference an upstream step's output."""

import pytest

from app.utils import templating


class TestHasPlaceholder:
    def test_detects_placeholder(self):
        assert templating.has_placeholder("{{ inputs.output }}")

    def test_plain_string_has_none(self):
        assert not templating.has_placeholder("just text")

    def test_non_string_has_none(self):
        assert not templating.has_placeholder({"a": 1})
        assert not templating.has_placeholder(None)


class TestRenderJsonEncode:
    def test_whole_output_dict_is_serialized(self):
        ctx = {"output": {"id": 1, "name": "x"}}
        out = templating.render("{{ inputs.output }}", ctx, json_encode=True)
        assert out == '{"id": 1, "name": "x"}'

    def test_envelope_wrapping_stays_valid_json(self):
        ctx = {"output": [{"id": 1}, {"id": 2}]}
        out = templating.render('{"records": {{ inputs.output }}}', ctx, json_encode=True)
        assert out == '{"records": [{"id": 1}, {"id": 2}]}'

    def test_string_output_is_quoted(self):
        ctx = {"output": "hello"}
        out = templating.render('{"note": {{ inputs.output }}}', ctx, json_encode=True)
        assert out == '{"note": "hello"}'

    def test_inputs_prefix_is_optional(self):
        ctx = {"output": 42}
        assert templating.render("{{ output }}", ctx, json_encode=True) == "42"
        assert templating.render("{{ inputs.output }}", ctx, json_encode=True) == "42"

    def test_drill_into_dict_key(self):
        ctx = {"output": {"records": [1, 2, 3]}}
        out = templating.render("{{ inputs.output.records }}", ctx, json_encode=True)
        assert out == "[1, 2, 3]"

    def test_drill_into_list_index(self):
        ctx = {"output": {"items": ["a", "b"]}}
        out = templating.render("{{ inputs.output.items.1 }}", ctx, json_encode=True)
        assert out == '"b"'


class TestRenderRawString:
    def test_scalar_is_unquoted_for_url(self):
        ctx = {"output": {"id": "abc123"}}
        out = templating.render(
            "https://api.example.com/records/{{ inputs.output.id }}",
            ctx,
            json_encode=False,
        )
        assert out == "https://api.example.com/records/abc123"

    def test_number_renders_without_quotes(self):
        ctx = {"output": {"id": 7}}
        out = templating.render("/x/{{ inputs.output.id }}", ctx, json_encode=False)
        assert out == "/x/7"

    def test_token_into_header_string(self):
        ctx = {"output": {"token": "xyz"}}
        out = templating.render(
            '{"Authorization": "Bearer {{ inputs.output.token }}"}',
            ctx,
            json_encode=False,
        )
        assert out == '{"Authorization": "Bearer xyz"}'

    def test_none_renders_empty(self):
        ctx = {"output": {"missing": None}}
        out = templating.render("[{{ inputs.output.missing }}]", ctx, json_encode=False)
        assert out == "[]"


class TestPassthroughAndNoOp:
    def test_text_without_placeholder_unchanged(self):
        ctx = {"output": "x"}
        assert templating.render("plain", ctx, json_encode=True) == "plain"

    def test_non_string_returned_unchanged(self):
        assert templating.render(None, {}, json_encode=True) is None
        assert templating.render(123, {}, json_encode=True) == 123


class TestErrors:
    def test_missing_top_level_output_is_helpful(self):
        # First node in a chain — no upstream output key.
        with pytest.raises(templating.TemplateError) as exc:
            templating.render("{{ inputs.output }}", {}, json_encode=True)
        assert "upstream step" in str(exc.value)

    def test_typo_in_key_reports_key(self):
        ctx = {"output": {"records": []}}
        with pytest.raises(templating.TemplateError) as exc:
            templating.render("{{ inputs.output.recrds }}", ctx, json_encode=True)
        assert "recrds" in str(exc.value)

    def test_index_out_of_range(self):
        ctx = {"output": {"items": ["a"]}}
        with pytest.raises(templating.TemplateError) as exc:
            templating.render("{{ inputs.output.items.5 }}", ctx, json_encode=True)
        assert "out of range" in str(exc.value)

    def test_drilling_into_scalar(self):
        ctx = {"output": "a string"}
        with pytest.raises(templating.TemplateError) as exc:
            templating.render("{{ inputs.output.field }}", ctx, json_encode=True)
        assert "no 'field'" in str(exc.value)
