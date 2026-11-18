"""A same-name upload reports whether its content differs from the stored file.

Support ticket: re-uploading a revised file under the same name opened the
existing document with its old content and no warning. The server keeps the
existing file either way; ``changed`` is what lets the page say so.
"""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services.file_service import upload_document


def _settings() -> Settings:
    return Settings(
        mongo_host="mongodb://localhost:27017/",
        mongo_db="test",
        redis_host="localhost",
        jwt_secret_key="test-secret-key-for-testing-only-32b",
        upload_dir="/tmp/test-uploads",
        max_upload_size_mb=1,
    )


def _user():
    user = MagicMock()
    user.user_id = "testuser"
    return user


async def _upload(new_bytes: bytes, *, stored: bytes | Exception, blob: str | None = None) -> dict:
    existing = MagicMock(uuid="OLD-UUID", path="testuser/OLD-UUID.pdf", downloadpath="testuser/OLD-UUID.pdf")
    storage = MagicMock()
    storage.read = AsyncMock(side_effect=stored) if isinstance(stored, Exception) else AsyncMock(return_value=stored)
    storage.write = AsyncMock()
    with patch("app.services.file_service.is_allowed_file", return_value=True), \
         patch("app.services.file_service.SmartDocument") as MockDoc, \
         patch("app.services.storage.get_storage", return_value=storage):
        MockDoc.find_one = AsyncMock(return_value=existing)
        result = await upload_document(
            blob=blob if blob is not None else base64.b64encode(new_bytes).decode(),
            filename="budget.pdf",
            raw_extension="pdf",
            user=_user(),
            settings=_settings(),
        )
    storage.write.assert_not_called()  # the existing file is never overwritten
    MockDoc.assert_not_called()  # and no second document is created
    return result


@pytest.mark.asyncio
async def test_revised_file_is_reported_as_changed():
    result = await _upload(b"revised budget", stored=b"original budget")
    assert result == {"complete": True, "exists": True, "uuid": "OLD-UUID", "changed": True}


@pytest.mark.asyncio
async def test_identical_file_is_reported_as_unchanged():
    result = await _upload(b"original budget", stored=b"original budget")
    assert result["exists"] is True
    assert result["changed"] is False


@pytest.mark.asyncio
async def test_unreadable_stored_file_claims_neither():
    result = await _upload(b"revised budget", stored=FileNotFoundError("gone"))
    assert result["exists"] is True
    assert result["changed"] is None


@pytest.mark.asyncio
async def test_invalid_upload_is_still_rejected_when_the_name_matches():
    with pytest.raises(ValueError, match="Invalid base64"):
        await _upload(b"", stored=b"original budget", blob="not base64!!")
