"""Fernet authenticated encryption for Telegram StringSession and API hashes."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.exceptions import SecurityConfigurationError


class SecretBox:
    """Encrypts and decrypts sensitive Telegram session strings at rest."""

    def __init__(self, key: str | None = None):
        raw_key = key or get_settings().SESSION_ENCRYPTION_KEY
        try:
            self._fernet = Fernet(raw_key.encode("utf-8"))
        except Exception as exc:
            raise SecurityConfigurationError("Invalid SESSION_ENCRYPTION_KEY format") from exc

    def encrypt(self, plaintext: str | None) -> str | None:
        if plaintext is None or plaintext == "":
            return None
        token = self._fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt(self, ciphertext: str | None) -> str | None:
        if ciphertext is None or ciphertext == "":
            return None
        try:
            raw = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return raw.decode("utf-8")
        except InvalidToken as exc:
            raise SecurityConfigurationError(
                "Failed to decrypt stored credential; check SESSION_ENCRYPTION_KEY."
            ) from exc
