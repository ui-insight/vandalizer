"""Thin Microsoft Graph API client.

Ported from Flask app/utilities/graph_client.py.
Uses httpx for HTTP calls. Designed to work in both FastAPI and Celery workers.
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphAuthError(Exception):
    """Raised when no valid Graph token is available."""


class GraphAPIError(Exception):
    """Raised when a Graph API call returns an error response."""

    def __init__(self, status_code: int, error: dict | str, url: str = ""):
        self.status_code = status_code
        self.error = error
        self.url = url
        super().__init__(f"Graph API {status_code} at {url}: {error}")


def _get_valid_token(user_id: str) -> str | None:
    """Retrieve a valid Graph API token for the user.

    In production this would use MSAL confidential client with cached refresh tokens.
    For now, falls back to environment variable for development.
    """
    try:
        import msal

        client_id = os.environ.get("AZURE_CLIENT_ID", "")
        client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
        tenant_id = os.environ.get("AZURE_TENANT_ID", "")

        if client_id and client_secret and tenant_id:
            authority = f"https://login.microsoftonline.com/{tenant_id}"
            app = msal.ConfidentialClientApplication(
                client_id,
                authority=authority,
                client_credential=client_secret,
            )
            result = app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"],
            )
            if result and result.get("access_token"):
                return str(result["access_token"])
    except ImportError:
        pass

    return os.environ.get("GRAPH_ACCESS_TOKEN")


class GraphClient:
    """Per-user Microsoft Graph API wrapper."""

    def __init__(self, user_id: str, timeout: float = 30.0):
        self.user_id = user_id
        self.timeout = timeout

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        token = _get_valid_token(self.user_id)
        if not token:
            raise GraphAuthError(f"No valid Graph token for user {self.user_id}")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        resp = httpx.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        if resp.status_code >= 400:
            raise GraphAPIError(resp.status_code, resp.json(), url)
        return resp.json()  # type: ignore[no-any-return]

    def _post(self, path: str, json: dict | None = None) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        resp = httpx.post(url, headers=self._headers(), json=json, timeout=self.timeout)
        if resp.status_code >= 400:
            raise GraphAPIError(resp.status_code, resp.json(), url)
        return resp.json()  # type: ignore[no-any-return]

    def _patch(self, path: str, json: dict | None = None) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        resp = httpx.patch(url, headers=self._headers(), json=json, timeout=self.timeout)
        if resp.status_code >= 400:
            raise GraphAPIError(resp.status_code, resp.json(), url)
        return resp.json()  # type: ignore[no-any-return]

    def _delete(self, path: str) -> None:
        url = f"{BASE_URL}{path}"
        resp = httpx.delete(url, headers=self._headers(), timeout=self.timeout)
        if resp.status_code >= 400:
            raise GraphAPIError(resp.status_code, resp.json(), url)

    def _get_bytes(self, path: str) -> bytes:
        url = f"{BASE_URL}{path}"
        resp = httpx.get(url, headers=self._headers(), timeout=self.timeout, follow_redirects=True)
        if resp.status_code >= 400:
            raise GraphAPIError(resp.status_code, str(resp.content[:200]), url)
        return resp.content

    def _put_bytes(self, url: str, content: bytes, content_type: str = "application/octet-stream") -> dict[str, Any]:
        headers = self._headers()
        headers["Content-Type"] = content_type
        resp = httpx.put(url, headers=headers, content=content, timeout=self.timeout)
        if resp.status_code >= 400:
            raise GraphAPIError(resp.status_code, resp.json(), url)
        return resp.json()  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Mail
    # ------------------------------------------------------------------

    def list_messages(
        self,
        folder_id: str = "Inbox",
        *,
        mailbox: str | None = None,
        top: int = 25,
        select: str = "id,subject,from,receivedDateTime,hasAttachments,bodyPreview",
        filter_query: str | None = None,
    ) -> list[dict[str, Any]]:
        base = f"/users/{mailbox}" if mailbox else "/me"
        path = f"{base}/mailFolders/{folder_id}/messages"
        params: dict[str, Any] = {"$top": top, "$select": select, "$orderby": "receivedDateTime desc"}
        if filter_query:
            params["$filter"] = filter_query
        data = self._get(path, params)
        return data.get("value", [])  # type: ignore[no-any-return]

    def get_message(self, message_id: str, *, mailbox: str | None = None) -> dict[str, Any]:
        base = f"/users/{mailbox}" if mailbox else "/me"
        return self._get(f"{base}/messages/{message_id}")

    def get_message_attachments(self, message_id: str, *, mailbox: str | None = None) -> list[dict[str, Any]]:
        base = f"/users/{mailbox}" if mailbox else "/me"
        data = self._get(f"{base}/messages/{message_id}/attachments")
        return data.get("value", [])  # type: ignore[no-any-return]

    def list_mail_folders(self, *, mailbox: str | None = None) -> list[dict[str, Any]]:
        base = f"/users/{mailbox}" if mailbox else "/me"
        data = self._get(f"{base}/mailFolders", {"$top": 100})
        return data.get("value", [])  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # OneDrive / Files
    # ------------------------------------------------------------------

    def list_drive_items(self, folder_path: str = "/", *, drive_id: str | None = None) -> list[dict[str, Any]]:
        drive = f"/drives/{drive_id}" if drive_id else "/me/drive"
        if folder_path == "/":
            path = f"{drive}/root/children"
        else:
            clean = folder_path.lstrip("/")
            path = f"{drive}/root:/{clean}:/children"
        data = self._get(path)
        return data.get("value", [])  # type: ignore[no-any-return]

    def get_drive_item(self, item_id: str, *, drive_id: str | None = None) -> dict[str, Any]:
        drive = f"/drives/{drive_id}" if drive_id else "/me/drive"
        return self._get(f"{drive}/items/{item_id}")

    def download_file(self, item_id: str, *, drive_id: str | None = None) -> bytes:
        drive = f"/drives/{drive_id}" if drive_id else "/me/drive"
        return self._get_bytes(f"{drive}/items/{item_id}/content")

    def upload_file(
        self,
        folder_path: str,
        filename: str,
        content: bytes,
        *,
        drive_id: str | None = None,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        drive = f"/drives/{drive_id}" if drive_id else "/me/drive"
        clean = folder_path.strip("/")
        url = f"{BASE_URL}{drive}/root:/{clean}/{filename}:/content"
        return self._put_bytes(url, content, content_type)

    def create_folder(self, parent_path: str, name: str, *, drive_id: str | None = None) -> dict[str, Any]:
        drive = f"/drives/{drive_id}" if drive_id else "/me/drive"
        if parent_path == "/" or not parent_path:
            path = f"{drive}/root/children"
        else:
            clean = parent_path.strip("/")
            path = f"{drive}/root:/{clean}:/children"
        return self._post(path, {
            "name": name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        })

    def ensure_folder_path(self, folder_path: str, *, drive_id: str | None = None) -> None:
        parts = [p for p in folder_path.strip("/").split("/") if p]
        current_path = ""
        for part in parts:
            parent = current_path or "/"
            try:
                self.create_folder(parent, part, drive_id=drive_id)
            except GraphAPIError as e:
                if e.status_code != 409:
                    raise
            current_path = f"{current_path}/{part}" if current_path else part

    # ------------------------------------------------------------------
    # Teams
    # ------------------------------------------------------------------

    def send_channel_message(
        self,
        team_id: str,
        channel_id: str,
        *,
        content: str | None = None,
        card_json: dict | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if card_json:
            body["body"] = {"contentType": "html", "content": ""}
            body["attachments"] = [{
                "id": "adaptive-card-1",
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card_json,
            }]
        elif content:
            body["body"] = {"contentType": "html", "content": content}
        else:
            raise ValueError("Either content or card_json must be provided")

        return self._post(f"/teams/{team_id}/channels/{channel_id}/messages", body)

    # ------------------------------------------------------------------
    # Subscriptions (Graph Webhooks)
    # ------------------------------------------------------------------

    def create_subscription(
        self,
        resource: str,
        change_type: str,
        notification_url: str,
        expiration: datetime.datetime,
        *,
        client_state: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "changeType": change_type,
            "notificationUrl": notification_url,
            "resource": resource,
            "expirationDateTime": expiration.isoformat() + "Z",
        }
        if client_state:
            payload["clientState"] = client_state
        return self._post("/subscriptions", payload)

    def renew_subscription(self, subscription_id: str, expiration: datetime.datetime) -> dict[str, Any]:
        return self._patch(f"/subscriptions/{subscription_id}", {
            "expirationDateTime": expiration.isoformat() + "Z",
        })

    def delete_subscription(self, subscription_id: str) -> None:
        self._delete(f"/subscriptions/{subscription_id}")
