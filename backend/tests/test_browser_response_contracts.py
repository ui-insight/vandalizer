"""Browser command responses must match the extension's object envelope."""

import json
from unittest.mock import Mock

import pytest

from app.services.browser_automation import BrowserAutomationService


@pytest.mark.parametrize("payload", [[], "wrong", 7, {"status": "success", "data": []}])
def test_malformed_response_is_rejected(payload):
    service = BrowserAutomationService()
    service._redis = Mock()
    service._redis.get.return_value = json.dumps(payload).encode()
    session = service.create_session("owner", "result", [])
    with pytest.raises(ValueError, match="Invalid extension response"):
        service.send_command(session, "get_page_state", {})


def test_valid_response_keeps_nested_extraction_rows():
    service = BrowserAutomationService()
    service._redis = Mock()
    data = {"structured_data": [{"text": "source row"}], "metadata": {"rows": 1}}
    service._redis.get.return_value = json.dumps({"status": "success", "data": data}).encode()
    session = service.create_session("owner", "result", [])
    assert service.send_command(session.session_id, "extract", {}) == data
    service._redis.delete.assert_called_once()


def test_missing_session_does_not_publish_command():
    service = BrowserAutomationService()
    service._redis = Mock()
    with pytest.raises(ValueError, match="Session not found"):
        service.send_command("missing", "extract", {})
    service._redis.publish.assert_not_called()
