"""Tests for file upload size limits in app.services.file_service.upload_document.

Verifies pre-decode and post-decode size checks, plus normal upload flow.
"""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings


def _make_settings(**overrides):
    defaults = {
        "max_upload_size_mb": 1,
        "upload_dir": "/tmp/test-uploads",
        "jwt_secret_key": "test-secret",
        "environment": "development",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _make_user(user_id: str = "testuser"):
    user = MagicMock()
    user.user_id = user_id
    user.is_admin = False
    return user


class TestUploadSizeLimits:
    @pytest.mark.asyncio
    async def test_oversized_file_pre_decode(self):
        """File whose base64 estimate exceeds limit raises ValueError before decoding."""
        settings = _make_settings(max_upload_size_mb=1)

        # Create a base64 string that estimates to > 1MB
        # Pre-decode estimate: len(blob) * 3 // 4
        # For 1MB limit = 1,048,576 bytes, need blob len > 1,398,101 chars
        oversized_blob = "A" * 1_500_000  # estimates to ~1.07MB

        from app.services.file_service import upload_document

        with pytest.raises(ValueError, match="too large"):
            await upload_document(
                blob=oversized_blob,
                filename="big_file.pdf",
                raw_extension="pdf",
                user=_make_user(),
                settings=settings,
            )

    @pytest.mark.asyncio
    async def test_oversized_file_post_decode(self):
        """File exceeding limit after full base64 decode raises ValueError.

        The pre-decode heuristic (len*3//4) may or may not catch this depending
        on padding. Either way, the function must reject the file with 'too large'.
        """
        settings = _make_settings(max_upload_size_mb=1)

        # Create actual data slightly over 1MB
        file_data = b"x" * (1_048_577)  # 1MB + 1 byte
        blob = base64.b64encode(file_data).decode()

        from app.services.file_service import upload_document

        with patch("app.services.file_service.is_allowed_file", return_value=True):
            with pytest.raises(ValueError, match="too large"):
                await upload_document(
                    blob=blob,
                    filename="big_file.pdf",
                    raw_extension="pdf",
                    user=_make_user(),
                    settings=settings,
                )

    @pytest.mark.asyncio
    async def test_normal_sized_file_accepted(self):
        """A file within the size limit is processed successfully."""
        settings = _make_settings(max_upload_size_mb=1)

        # Create a small file (100 bytes)
        file_data = b"small content here"
        blob = base64.b64encode(file_data).decode()
        user = _make_user()

        mock_doc = MagicMock()
        mock_doc.id = "doc-id-1"
        mock_doc.uuid = "DOC-UUID-1"
        mock_doc.insert = AsyncMock()
        mock_doc.save = AsyncMock()
        mock_storage = MagicMock()
        mock_storage.write = AsyncMock()
        mock_storage.public_path = MagicMock(return_value="/tmp/test-uploads/testuser/DOC-UUID-1.pdf")

        with patch("app.services.file_service.is_allowed_file", return_value=True), \
             patch("app.services.file_service.is_valid_file_content", return_value=True), \
             patch("app.services.file_service.SmartDocument") as MockDoc, \
             patch("app.services.storage.get_storage", return_value=mock_storage), \
             patch("app.tasks.upload_tasks.dispatch_upload_tasks", return_value="task-123"):
            MockDoc.find_one = AsyncMock(return_value=None)  # no duplicate
            MockDoc.return_value = mock_doc

            from app.services.file_service import upload_document

            result = await upload_document(
                blob=blob,
                filename="small_file.pdf",
                raw_extension="pdf",
                user=user,
                settings=settings,
            )

        assert result["complete"] is True
        assert "uuid" in result

    @pytest.mark.asyncio
    async def test_disallowed_file_type_rejected(self):
        """A file with a disallowed extension raises ValueError."""
        settings = _make_settings(max_upload_size_mb=1)
        blob = base64.b64encode(b"data").decode()

        from app.services.file_service import upload_document

        with pytest.raises(ValueError, match="not allowed"):
            await upload_document(
                blob=blob,
                filename="script.py",
                raw_extension="py",
                user=_make_user(),
                settings=settings,
            )
