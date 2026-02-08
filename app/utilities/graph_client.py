#!/usr/bin/env python3
"""Thin Microsoft Graph API client.

Uses httpx for HTTP calls and the graph_token_store for authentication.
Designed to work in both Flask request context and Celery workers.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

import httpx

from app.utilities.graph_token_store import get_valid_token

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


class GraphClient:
    """Per-user Microsoft Graph API wrapper.

    Usage::

        client = GraphClient("user@example.com")
        messages = client.list_messages(folder_id="Inbox")
    """

    def __init__(self, user_id: str, timeout: float = 30.0):
        self.user_id = user_id
        self.timeout = timeout

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        token = get_valid_token(self.user_id)
        if not token:
            raise GraphAuthError(f"No valid Graph token for user {self.user_id}")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        resp = httpx.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        if resp.status_code >= 400:
            raise GraphAPIError(resp.status_code, resp.json(), url)
        return resp.json()

    def _post(self, path: str, json: dict | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        resp = httpx.post(url, headers=self._headers(), json=json, timeout=self.timeout)
        if resp.status_code >= 400:
            raise GraphAPIError(resp.status_code, resp.json(), url)
        return resp.json()

    def _patch(self, path: str, json: dict | None = None) -> dict:
        url = f"{BASE_URL}{path}"
        resp = httpx.patch(url, headers=self._headers(), json=json, timeout=self.timeout)
        if resp.status_code >= 400:
            raise GraphAPIError(resp.status_code, resp.json(), url)
        return resp.json()

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

    def _put_bytes(self, url: str, content: bytes, content_type: str = "application/octet-stream") -> dict:
        headers = self._headers()
        headers["Content-Type"] = content_type
        resp = httpx.put(url, headers=headers, content=content, timeout=self.timeout)
        if resp.status_code >= 400:
            raise GraphAPIError(resp.status_code, resp.json(), url)
        return resp.json()

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
    ) -> list[dict]:
        """List messages in a mail folder.

        Args:
            folder_id: Mail folder ID or well-known name (Inbox, Drafts, etc.)
            mailbox: Shared mailbox address. If None, uses the authenticated user's mailbox.
            top: Max messages to return.
            select: OData $select fields.
            filter_query: OData $filter expression.
        """
        base = f"/users/{mailbox}" if mailbox else "/me"
        path = f"{base}/mailFolders/{folder_id}/messages"
        params: dict[str, Any] = {"$top": top, "$select": select, "$orderby": "receivedDateTime desc"}
        if filter_query:
            params["$filter"] = filter_query
        data = self._get(path, params)
        return data.get("value", [])

    def get_message(self, message_id: str, *, mailbox: str | None = None) -> dict:
        """Get a single message by ID."""
        base = f"/users/{mailbox}" if mailbox else "/me"
        return self._get(f"{base}/messages/{message_id}")

    def get_message_attachments(self, message_id: str, *, mailbox: str | None = None) -> list[dict]:
        """Get attachments for a message."""
        base = f"/users/{mailbox}" if mailbox else "/me"
        data = self._get(f"{base}/messages/{message_id}/attachments")
        return data.get("value", [])

    def list_mail_folders(self, *, mailbox: str | None = None) -> list[dict]:
        """List mail folders for the user or shared mailbox."""
        base = f"/users/{mailbox}" if mailbox else "/me"
        data = self._get(f"{base}/mailFolders", {"$top": 100})
        return data.get("value", [])

    # ------------------------------------------------------------------
    # OneDrive / Files
    # ------------------------------------------------------------------

    def list_drive_items(
        self,
        folder_path: str = "/",
        *,
        drive_id: str | None = None,
    ) -> list[dict]:
        """List items in a OneDrive folder.

        Args:
            folder_path: Folder path relative to drive root (e.g. "/Vandalizer/Drop").
            drive_id: Specific drive ID. If None, uses the user's default drive.
        """
        drive = f"/drives/{drive_id}" if drive_id else "/me/drive"
        if folder_path == "/":
            path = f"{drive}/root/children"
        else:
            # Strip leading slash for :path: syntax
            clean = folder_path.lstrip("/")
            path = f"{drive}/root:/{clean}:/children"
        data = self._get(path)
        return data.get("value", [])

    def get_drive_item(self, item_id: str, *, drive_id: str | None = None) -> dict:
        """Get metadata for a specific drive item."""
        drive = f"/drives/{drive_id}" if drive_id else "/me/drive"
        return self._get(f"{drive}/items/{item_id}")

    def download_file(self, item_id: str, *, drive_id: str | None = None) -> bytes:
        """Download file content by item ID."""
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
    ) -> dict:
        """Upload a file (< 4MB) to a OneDrive folder.

        For larger files, use upload_large_file() with upload sessions.
        """
        drive = f"/drives/{drive_id}" if drive_id else "/me/drive"
        clean = folder_path.strip("/")
        url = f"{BASE_URL}{drive}/root:/{clean}/{filename}:/content"
        return self._put_bytes(url, content, content_type)

    def create_folder(
        self,
        parent_path: str,
        name: str,
        *,
        drive_id: str | None = None,
    ) -> dict:
        """Create a folder in OneDrive. Returns the created folder's metadata."""
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
        """Recursively create all folders in a path if they don't exist."""
        parts = [p for p in folder_path.strip("/").split("/") if p]
        current_path = ""
        for part in parts:
            parent = current_path or "/"
            try:
                self.create_folder(parent, part, drive_id=drive_id)
            except GraphAPIError as e:
                # 409 = folder already exists, which is fine
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
    ) -> dict:
        """Send a message to a Teams channel.

        Args:
            team_id: The team's ID.
            channel_id: The channel's ID.
            content: Plain HTML content for the message body.
            card_json: An Adaptive Card payload to attach.
        """
        body: dict[str, Any] = {}

        if card_json:
            body["body"] = {"contentType": "html", "content": ""}
            body["attachments"] = [
                {
                    "id": "adaptive-card-1",
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card_json,
                }
            ]
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
    ) -> dict:
        """Create a Graph change notification subscription.

        Args:
            resource: The resource to watch (e.g. "/users/{id}/mailFolders('Inbox')/messages").
            change_type: Comma-separated change types: "created", "updated", "deleted".
            notification_url: HTTPS endpoint that will receive notifications.
            expiration: When the subscription expires (max 3 days for most resources).
            client_state: Optional secret string echoed back in notifications.
        """
        payload: dict[str, Any] = {
            "changeType": change_type,
            "notificationUrl": notification_url,
            "resource": resource,
            "expirationDateTime": expiration.isoformat() + "Z",
        }
        if client_state:
            payload["clientState"] = client_state
        return self._post("/subscriptions", payload)

    def renew_subscription(self, subscription_id: str, expiration: datetime.datetime) -> dict:
        """Renew (extend) a subscription's expiration."""
        return self._patch(f"/subscriptions/{subscription_id}", {
            "expirationDateTime": expiration.isoformat() + "Z",
        })

    def delete_subscription(self, subscription_id: str) -> None:
        """Delete a subscription."""
        self._delete(f"/subscriptions/{subscription_id}")
