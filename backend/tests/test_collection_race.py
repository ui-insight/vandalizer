"""Concurrent first uploads must not leave documents unsearchable because
several workers raced to create the same Chroma collection."""

from unittest.mock import MagicMock

import pytest
from chromadb.errors import UniqueConstraintError

from app.services.document_manager import DocumentManager, _is_already_exists


def _dm(client):
    dm = DocumentManager.__new__(DocumentManager)
    dm.client = client
    dm.embedding_function = object()
    return dm


def test_lost_create_race_opens_existing_collection():
    client = MagicMock()
    existing = object()
    client.get_or_create_collection.side_effect = UniqueConstraintError(
        "Collection 8d6ac802 already exists")
    client.get_collection.return_value = existing
    assert _dm(client).get_user_collection("someone@uidaho.edu") is existing
    client.get_collection.assert_called_once()


def test_kb_collection_same_protection():
    client = MagicMock()
    existing = object()
    client.get_or_create_collection.side_effect = UniqueConstraintError("already exists")
    client.get_collection.return_value = existing
    assert _dm(client).get_kb_collection("kb-1") is existing


def test_other_errors_still_raise():
    client = MagicMock()
    client.get_or_create_collection.side_effect = ConnectionError("chroma down")
    with pytest.raises(ConnectionError):
        _dm(client).get_user_collection("someone@uidaho.edu")
    client.get_collection.assert_not_called()


def test_error_recognised_from_server_message():
    assert _is_already_exists(RuntimeError('{"error":"UniqueConstraintError","message":"x"}'))
    assert not _is_already_exists(RuntimeError("timeout"))
