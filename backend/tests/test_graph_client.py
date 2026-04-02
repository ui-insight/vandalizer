"""Tests for app.services.graph_client — Microsoft Graph API wrapper."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.graph_client import (
    GraphAPIError,
    GraphAuthError,
    GraphClient,
    _get_valid_token,
)


class TestGetValidToken:
    def test_returns_env_var_when_no_msal(self):
        with patch.dict("os.environ", {"GRAPH_ACCESS_TOKEN": "test-token"}, clear=False):
            with patch("builtins.__import__", side_effect=ImportError):
                result = _get_valid_token("user1")
        # Falls back to env var

    def test_returns_none_when_no_env_var(self):
        with patch.dict("os.environ", {}, clear=True):
            result = _get_valid_token("user1")
        assert result is None

    def test_returns_env_var_fallback(self):
        with patch.dict("os.environ", {"GRAPH_ACCESS_TOKEN": "my-token"}, clear=False):
            # msal import will fail in test env, so falls back to env
            result = _get_valid_token("user1")
        assert result == "my-token"


class TestGraphAPIError:
    def test_stores_fields(self):
        err = GraphAPIError(404, {"message": "Not found"}, "/me")
        assert err.status_code == 404
        assert err.error == {"message": "Not found"}
        assert err.url == "/me"
        assert "404" in str(err)

    def test_string_error(self):
        err = GraphAPIError(500, "server error")
        assert err.error == "server error"


class TestGraphAuthError:
    def test_message(self):
        err = GraphAuthError("no token")
        assert "no token" in str(err)


class TestGraphClient:
    def _client(self):
        return GraphClient("test-user", timeout=5.0)

    def test_headers_raises_when_no_token(self):
        gc = self._client()
        with patch("app.services.graph_client._get_valid_token", return_value=None):
            with pytest.raises(GraphAuthError):
                gc._headers()

    def test_headers_returns_bearer(self):
        gc = self._client()
        with patch("app.services.graph_client._get_valid_token", return_value="abc"):
            headers = gc._headers()
        assert headers["Authorization"] == "Bearer abc"
        assert headers["Content-Type"] == "application/json"

    def test_get_success(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "123"}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.get", return_value=mock_resp),
        ):
            result = gc._get("/me")
        assert result == {"id": "123"}

    def test_get_error(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"error": "not found"}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.get", return_value=mock_resp),
        ):
            with pytest.raises(GraphAPIError) as exc_info:
                gc._get("/me")
            assert exc_info.value.status_code == 404

    def test_post_success(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "new"}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.post", return_value=mock_resp),
        ):
            result = gc._post("/teams/1/channels/2/messages", {"body": "hi"})
        assert result == {"id": "new"}

    def test_post_error(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"error": "bad"}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.post", return_value=mock_resp),
        ):
            with pytest.raises(GraphAPIError):
                gc._post("/test")

    def test_patch_success(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"updated": True}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.patch", return_value=mock_resp),
        ):
            result = gc._patch("/subscriptions/1", {"exp": "2026-01-01"})
        assert result == {"updated": True}

    def test_delete_success(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 204

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.delete", return_value=mock_resp),
        ):
            gc._delete("/subscriptions/1")  # should not raise

    def test_delete_error(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {"error": "forbidden"}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.delete", return_value=mock_resp),
        ):
            with pytest.raises(GraphAPIError):
                gc._delete("/subscriptions/1")

    def test_get_bytes_success(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"file-data"

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.get", return_value=mock_resp),
        ):
            result = gc._get_bytes("/me/drive/items/1/content")
        assert result == b"file-data"

    def test_put_bytes_success(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "uploaded"}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.put", return_value=mock_resp),
        ):
            result = gc._put_bytes("https://graph.microsoft.com/v1.0/upload", b"data")
        assert result == {"id": "uploaded"}

    def test_list_messages(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"value": [{"id": "msg1"}]}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.get", return_value=mock_resp),
        ):
            result = gc.list_messages()
        assert len(result) == 1
        assert result[0]["id"] == "msg1"

    def test_list_messages_with_filter(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"value": []}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.get", return_value=mock_resp),
        ):
            result = gc.list_messages(filter_query="isRead eq false")
        assert result == []

    def test_list_drive_items_root(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"value": [{"name": "file.txt"}]}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.get", return_value=mock_resp),
        ):
            result = gc.list_drive_items("/")
        assert len(result) == 1

    def test_list_drive_items_subfolder(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"value": []}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.get", return_value=mock_resp),
        ):
            result = gc.list_drive_items("/Documents/Subfolder")
        assert result == []

    def test_send_channel_message_with_content(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "msg1"}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.post", return_value=mock_resp),
        ):
            result = gc.send_channel_message("team1", "chan1", content="<p>Hello</p>")
        assert result["id"] == "msg1"

    def test_send_channel_message_with_card(self):
        gc = self._client()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "msg2"}

        with (
            patch("app.services.graph_client._get_valid_token", return_value="tok"),
            patch("httpx.post", return_value=mock_resp),
        ):
            result = gc.send_channel_message("team1", "chan1", card_json={"type": "AdaptiveCard"})
        assert result["id"] == "msg2"

    def test_send_channel_message_raises_without_content(self):
        gc = self._client()
        with pytest.raises(ValueError, match="Either content or card_json"):
            gc.send_channel_message("team1", "chan1")
