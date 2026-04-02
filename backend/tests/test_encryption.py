"""Tests for app.utils.encryption — symmetric encryption for config values."""

from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet


class TestGetFernet:
    def setup_method(self):
        import app.utils.encryption as mod
        mod._fernet = None

    def test_returns_none_when_no_key(self):
        import app.utils.encryption as mod
        mod._fernet = None

        mock_settings = MagicMock()
        mock_settings.config_encryption_key = ""

        with patch("app.config.Settings", return_value=mock_settings):
            result = mod._get_fernet()
        assert result is None

    def test_returns_fernet_with_valid_key(self):
        import app.utils.encryption as mod
        mod._fernet = None

        key = Fernet.generate_key().decode()
        mock_settings = MagicMock()
        mock_settings.config_encryption_key = key

        with patch("app.config.Settings", return_value=mock_settings):
            result = mod._get_fernet()
        assert result is not None
        assert isinstance(result, Fernet)

    def test_caches_fernet_instance(self):
        import app.utils.encryption as mod

        f = Fernet(Fernet.generate_key())
        mod._fernet = f

        result = mod._get_fernet()
        assert result is f

    def test_returns_none_with_invalid_key(self):
        import app.utils.encryption as mod
        mod._fernet = None

        mock_settings = MagicMock()
        mock_settings.config_encryption_key = "not-a-valid-fernet-key"

        with patch("app.config.Settings", return_value=mock_settings):
            result = mod._get_fernet()
        assert result is None


class TestEncryptValue:
    def setup_method(self):
        import app.utils.encryption as mod
        mod._fernet = None

    def test_empty_string_returns_unchanged(self):
        from app.utils.encryption import encrypt_value
        assert encrypt_value("") == ""

    def test_returns_plaintext_when_no_fernet(self):
        import app.utils.encryption as mod
        mod._fernet = None
        mock_settings = MagicMock()
        mock_settings.config_encryption_key = ""

        with patch("app.config.Settings", return_value=mock_settings):
            result = mod.encrypt_value("secret")
        assert result == "secret"

    def test_encrypts_with_enc_prefix(self):
        import app.utils.encryption as mod

        key = Fernet.generate_key().decode()
        mock_settings = MagicMock()
        mock_settings.config_encryption_key = key

        with patch("app.config.Settings", return_value=mock_settings):
            result = mod.encrypt_value("my-secret")
        assert result.startswith("enc:")
        assert result != "my-secret"


class TestDecryptValue:
    def setup_method(self):
        import app.utils.encryption as mod
        mod._fernet = None

    def test_empty_value_returns_unchanged(self):
        from app.utils.encryption import decrypt_value
        assert decrypt_value("") == ""

    def test_non_encrypted_value_returns_unchanged(self):
        from app.utils.encryption import decrypt_value
        assert decrypt_value("plain-value") == "plain-value"

    def test_returns_encrypted_value_when_no_fernet(self):
        import app.utils.encryption as mod
        mod._fernet = None
        mock_settings = MagicMock()
        mock_settings.config_encryption_key = ""

        with patch("app.config.Settings", return_value=mock_settings):
            result = mod.decrypt_value("enc:something")
        assert result == "enc:something"

    def test_roundtrip_encrypt_decrypt(self):
        import app.utils.encryption as mod
        mod._fernet = None

        key = Fernet.generate_key().decode()
        mock_settings = MagicMock()
        mock_settings.config_encryption_key = key

        with patch("app.config.Settings", return_value=mock_settings):
            encrypted = mod.encrypt_value("hello-world")
            decrypted = mod.decrypt_value(encrypted)
        assert decrypted == "hello-world"

    def test_invalid_token_returns_value(self):
        import app.utils.encryption as mod

        # Set up a valid fernet so _get_fernet() returns it
        mod._fernet = Fernet(Fernet.generate_key())

        result = mod.decrypt_value("enc:not-valid-ciphertext")
        assert result == "enc:not-valid-ciphertext"
