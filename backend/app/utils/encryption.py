"""Symmetric encryption for sensitive config values stored in MongoDB."""

import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_fernet = None


def _get_fernet() -> Fernet | None:
    global _fernet
    if _fernet is not None:
        return _fernet
    from app.config import Settings

    settings = Settings()
    if not settings.config_encryption_key:
        return None
    try:
        _fernet = Fernet(settings.config_encryption_key.encode())
    except Exception:
        logger.warning("Invalid CONFIG_ENCRYPTION_KEY — secrets will not be encrypted")
        return None
    return _fernet


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string. Returns the ciphertext prefixed with 'enc:'.
    If encryption is not configured, returns the plaintext unchanged."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    if f is None:
        return plaintext
    return "enc:" + f.encrypt(plaintext.encode()).decode("ascii")


def decrypt_value(value: str) -> str:
    """Decrypt a value. If it starts with 'enc:', decrypt it.
    Otherwise return as-is (backwards compatible with unencrypted values)."""
    if not value or not value.startswith("enc:"):
        return value
    f = _get_fernet()
    if f is None:
        logger.warning("Cannot decrypt value — CONFIG_ENCRYPTION_KEY not set")
        return value
    try:
        return f.decrypt(value[4:].encode()).decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt config value — key may have changed")
        return value
