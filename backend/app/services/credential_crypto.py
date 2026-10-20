"""Versioned authenticated encryption for server-level Access credentials."""

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


_PURPOSE = b"home-library:ai-server-credentials:v1"
_PREFIX = "v1:"
_NONCE_BYTES = 12
_DEFAULT_KEYS = frozenset({"change-this-secret", "dev-secret-change-me-in-production"})


class CredentialCryptoError(ValueError):
    """A sanitized credential failure safe to handle at service boundaries."""


def is_production_secret_key(secret_key: str) -> bool:
    return (
        bool(secret_key.strip())
        and secret_key not in _DEFAULT_KEYS
        and len(secret_key.encode("utf-8")) >= 32
    )


class CredentialCipher:
    def __init__(self, key: bytes):
        self._aead = AESGCM(key)

    @classmethod
    def from_secret_key(cls, secret_key: str) -> "CredentialCipher":
        key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=_PURPOSE,
        ).derive(secret_key.encode("utf-8"))
        return cls(key)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        encrypted = self._aead.encrypt(nonce, plaintext.encode("utf-8"), _PURPOSE)
        return _PREFIX + base64.urlsafe_b64encode(nonce + encrypted).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            if not ciphertext.startswith(_PREFIX):
                raise ValueError
            encoded = ciphertext[len(_PREFIX):].encode("ascii")
            data = base64.b64decode(encoded, altchars=b"-_", validate=True)
            if len(data) < _NONCE_BYTES + 16:
                raise ValueError
            return self._aead.decrypt(
                data[:_NONCE_BYTES], data[_NONCE_BYTES:], _PURPOSE,
            ).decode("utf-8")
        except (ValueError, InvalidTag, binascii.Error):
            raise CredentialCryptoError("凭据解密失败") from None
