"""AES-GCM for the sensitive columns of the chart database."""

from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16


class DecryptionError(Exception):
    """The data was not encrypted with this key, or has been altered."""


class Cipher:
    """Encrypts text with a 256-bit key. `context` (e.g. "record.zh_text") is bound to the
    ciphertext, so a value cannot be moved into another column and still decrypt."""

    def __init__(self, key: bytes) -> None:
        if len(key) != KEY_BYTES:
            raise ValueError(f"key must be {KEY_BYTES} bytes, got {len(key)}")
        self._aead = AESGCM(key)

    def encrypt(self, text: str, context: str) -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        return nonce + self._aead.encrypt(nonce, text.encode(), context.encode())

    def decrypt(self, blob: bytes, context: str) -> str:
        """Raises DecryptionError for a wrong key, a wrong context, or damaged data."""
        if len(blob) < NONCE_BYTES + TAG_BYTES:
            raise DecryptionError(f"{context}: ciphertext is too short")
        try:
            plain = self._aead.decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], context.encode())
        except InvalidTag as e:
            raise DecryptionError(f"{context}: wrong key or damaged data") from e
        return plain.decode()
