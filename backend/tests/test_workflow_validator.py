"""Tests for workflow_validator — the two surviving sync helpers.

This file previously tested the Flask-port PlanGenerator / CheckRunner /
Scorer classes, which were superseded by the unified validation flow in
workflow_service (generate_validation_plan, _evaluate_checks_against_output,
_build_result) and deleted. Only ``_extract_json`` and ``_resolve_model_name``
remain in the module; this file now covers exactly those.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.workflow_validator import _extract_json, _resolve_model_name


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json_object(self):
        result = _extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_plain_json_array(self):
        result = _extract_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_json_in_markdown_fences(self):
        text = '```json\n{"checks": []}\n```'
        result = _extract_json(text)
        assert result == {"checks": []}

    def test_json_with_leading_text(self):
        text = 'Here is the result: {"status": "PASS"}'
        result = _extract_json(text)
        assert result == {"status": "PASS"}

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="Could not extract JSON"):
            _extract_json("no json here at all")

    def test_json_with_whitespace(self):
        text = '   \n  {"a": 1}  \n  '
        result = _extract_json(text)
        assert result == {"a": 1}

    def test_markdown_fences_without_language(self):
        text = '```\n[1, 2]\n```'
        result = _extract_json(text)
        assert result == [1, 2]


# ---------------------------------------------------------------------------
# _resolve_model_name
# ---------------------------------------------------------------------------


def _make_db(user_config=None, sys_config=None):
    db = MagicMock()
    db.user_model_config.find_one.return_value = user_config
    db.system_config.find_one.return_value = sys_config
    return db


class TestResolveModelName:
    @patch("app.services.workflow_validator._get_db")
    def test_user_config_wins(self, mock_db):
        mock_db.return_value = _make_db(
            user_config={"user_id": "u1", "name": "user-model"},
            sys_config={"available_models": [{"name": "sys-model"}]},
        )
        assert _resolve_model_name("u1") == "user-model"

    @patch("app.services.workflow_validator._get_db")
    def test_falls_back_to_system_default(self, mock_db):
        mock_db.return_value = _make_db(
            user_config=None,
            sys_config={"available_models": [{"name": "sys-model"}]},
        )
        assert _resolve_model_name("u1") == "sys-model"

    @patch("app.services.workflow_validator._get_db")
    def test_no_user_id_skips_user_lookup(self, mock_db):
        db = _make_db(sys_config={"available_models": [{"name": "sys-model"}]})
        mock_db.return_value = db
        assert _resolve_model_name(None) == "sys-model"
        db.user_model_config.find_one.assert_not_called()

    @patch("app.services.workflow_validator._get_db")
    def test_empty_config_returns_empty_string(self, mock_db):
        mock_db.return_value = _make_db(user_config=None, sys_config=None)
        assert _resolve_model_name("u1") == ""

    @patch("app.services.workflow_validator._get_db")
    def test_non_dict_models_returns_empty_string(self, mock_db):
        mock_db.return_value = _make_db(sys_config={"available_models": ["bare-string"]})
        assert _resolve_model_name(None) == ""
