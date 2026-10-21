"""Versioned authenticated encryption for stored credentials."""

import base64
import binascii
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


_PURPOSE = b"home-library:ai-server-credentials:v1"
_PREFIX = "v1:"
_NONCE_BYTES = 12
_DEFAULT_KEYS = frozenset({"change-this-secret", "dev-secret-change-me-in-production"})

# Fingerprint of the publicly documented deployment example, never a production key.
_PUBLIC_EXAMPLE_KEY_SHA256 = "79ef599b03c84b902bc2c21405ad47203ca5606291b87fc383219ccc0c9d77f6"


class CredentialCryptoError(ValueError):
    """A sanitized credential failure safe to handle at service boundaries."""


def is_production_secret_key(secret_key: str) -> bool:
    normalized_key = secret_key.strip()
    return (
        bool(normalized_key)
        and normalized_key not in _DEFAULT_KEYS
        and hashlib.sha256(normalized_key.encode("utf-8")).hexdigest() != _PUBLIC_EXAMPLE_KEY_SHA256
        and len(normalized_key.encode("utf-8")) >= 32
    )


class CredentialCipher:
    def __init__(self, key: bytes, purpose: bytes = _PURPOSE):
        self._aead = AESGCM(key)
        self._purpose = purpose

    @classmethod
    def from_secret_key(
        cls,
        secret_key: str,
        purpose: bytes = _PURPOSE,
    ) -> "CredentialCipher":
        key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=purpose,
        ).derive(secret_key.encode("utf-8"))
        return cls(key, purpose)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        encrypted = self._aead.encrypt(nonce, plaintext.encode("utf-8"), self._purpose)
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
                data[:_NONCE_BYTES], data[_NONCE_BYTES:], self._purpose,
            ).decode("utf-8")
        except (ValueError, InvalidTag, binascii.Error):
            raise CredentialCryptoError("凭据解密失败") from None
