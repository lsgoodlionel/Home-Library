"""Encrypted account-scoped AI provider credential persistence."""

from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.user_ai_provider_credential import UserAIProviderCredential
from app.services.credential_crypto import (
    CredentialCipher,
    CredentialCryptoError,
    is_production_secret_key,
)


ProviderCredentialState = Literal["missing", "configured", "unusable"]
_ACCOUNT_KEY_PURPOSE = b"home-library:user-ai-provider-key:v1"


def _credential(db: Session, user_id: int, provider: str) -> UserAIProviderCredential | None:
    return db.query(UserAIProviderCredential).filter_by(
        user_id=user_id,
        provider=provider,
    ).first()


def _cipher() -> CredentialCipher:
    secret_key = Settings().secret_key
    if not is_production_secret_key(secret_key):
        raise CredentialCryptoError("账号供应商凭据不可用")
    return CredentialCipher.from_secret_key(secret_key, purpose=_ACCOUNT_KEY_PURPOSE)


def get_provider_api_key(db: Session, user_id: int, provider: str) -> str:
    credential = _credential(db, user_id, provider)
    if credential is None:
        return ""
    try:
        return _cipher().decrypt(credential.api_key_ciphertext)
    except Exception:
        raise CredentialCryptoError("账号供应商凭据不可用") from None


def set_provider_api_key(db: Session, user_id: int, provider: str, api_key: str) -> None:
    if api_key == "":
        return
    try:
        ciphertext = _cipher().encrypt(api_key)
    except Exception:
        raise CredentialCryptoError("账号供应商凭据保存失败") from None

    credential = _credential(db, user_id, provider)
    if credential is None:
        credential = UserAIProviderCredential(
            user_id=user_id,
            provider=provider,
            api_key_ciphertext=ciphertext,
        )
    else:
        credential.api_key_ciphertext = ciphertext
    db.add(credential)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise CredentialCryptoError("账号供应商凭据保存失败") from None


def clear_provider_api_key(db: Session, user_id: int, provider: str) -> None:
    credential = _credential(db, user_id, provider)
    if credential is None:
        return
    db.delete(credential)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise CredentialCryptoError("账号供应商凭据清除失败") from None


def get_provider_credential_state(
    db: Session,
    user_id: int,
    provider: str,
) -> ProviderCredentialState:
    credential = _credential(db, user_id, provider)
    if credential is None:
        return "missing"
    try:
        _cipher().decrypt(credential.api_key_ciphertext)
    except Exception:
        return "unusable"
    return "configured"
