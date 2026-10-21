"""Account-scoped AI provider credential service contracts."""

from __future__ import annotations

import logging

import pytest
from sqlalchemy.orm import Session

from app.models import User, UserAIProviderCredential
from app.services.ai_provider_credential_service import (
    clear_provider_api_key,
    get_provider_api_key,
    get_provider_credential_state,
    set_provider_api_key,
)
from app.services.credential_crypto import CredentialCryptoError


_FIRST_SECRET_KEY = "credential-service-strong-key-value-00001"
_SECOND_SECRET_KEY = "credential-service-strong-key-value-00002"


def _user(db: Session, username: str) -> User:
    user = User(
        username=username,
        password_hash="hash",
        display_name=username,
        role="member",
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _set_secret_key(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", value)


def test_empty_api_key_preserves_existing_credential(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_secret_key(monkeypatch, _FIRST_SECRET_KEY)
    user = _user(db, "preserve-user")
    set_provider_api_key(db, user.id, "openai", "provider-key-one")
    before = db.query(UserAIProviderCredential).filter_by(user_id=user.id, provider="openai").one()
    original_ciphertext = before.api_key_ciphertext

    set_provider_api_key(db, user.id, "openai", "")

    after = db.query(UserAIProviderCredential).filter_by(user_id=user.id, provider="openai").one()
    assert after.api_key_ciphertext == original_ciphertext
    assert get_provider_api_key(db, user.id, "openai") == "provider-key-one"


def test_non_empty_api_key_replaces_existing_credential(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_secret_key(monkeypatch, _FIRST_SECRET_KEY)
    user = _user(db, "replace-user")
    set_provider_api_key(db, user.id, "openai", "provider-key-one")
    original_ciphertext = db.query(UserAIProviderCredential.api_key_ciphertext).filter_by(
        user_id=user.id,
        provider="openai",
    ).scalar()

    set_provider_api_key(db, user.id, "openai", "provider-key-two")

    replacement = db.query(UserAIProviderCredential).filter_by(
        user_id=user.id,
        provider="openai",
    ).one()
    assert replacement.api_key_ciphertext != original_ciphertext
    assert "provider-key-two" not in replacement.api_key_ciphertext
    assert get_provider_api_key(db, user.id, "openai") == "provider-key-two"
    assert get_provider_credential_state(db, user.id, "openai") == "configured"


def test_clear_provider_api_key_explicitly_removes_credential(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_secret_key(monkeypatch, _FIRST_SECRET_KEY)
    user = _user(db, "clear-user")
    set_provider_api_key(db, user.id, "gemini", "provider-key")

    clear_provider_api_key(db, user.id, "gemini")

    assert get_provider_api_key(db, user.id, "gemini") == ""
    assert get_provider_credential_state(db, user.id, "gemini") == "missing"
    assert db.query(UserAIProviderCredential).filter_by(
        user_id=user.id,
        provider="gemini",
    ).first() is None


def test_wrong_application_key_reports_unusable_without_secret_leakage(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    plaintext = "provider-key-must-not-leak"
    _set_secret_key(monkeypatch, _FIRST_SECRET_KEY)
    user = _user(db, "wrong-key-user")
    set_provider_api_key(db, user.id, "deepseek", plaintext)
    ciphertext = db.query(UserAIProviderCredential.api_key_ciphertext).filter_by(
        user_id=user.id,
        provider="deepseek",
    ).scalar()

    _set_secret_key(monkeypatch, _SECOND_SECRET_KEY)
    caplog.set_level(logging.DEBUG)
    assert get_provider_credential_state(db, user.id, "deepseek") == "unusable"
    with pytest.raises(CredentialCryptoError) as error:
        get_provider_api_key(db, user.id, "deepseek")

    combined_output = f"{error.value!s}\n{error.value!r}\n{caplog.text}"
    assert plaintext not in combined_output
    assert ciphertext not in combined_output
    assert _FIRST_SECRET_KEY not in combined_output
    assert _SECOND_SECRET_KEY not in combined_output


def test_credentials_are_isolated_by_user_and_provider(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_secret_key(monkeypatch, _FIRST_SECRET_KEY)
    first_user = _user(db, "isolation-one")
    second_user = _user(db, "isolation-two")
    set_provider_api_key(db, first_user.id, "openai", "first-openai-key")
    set_provider_api_key(db, first_user.id, "gemini", "first-gemini-key")
    set_provider_api_key(db, second_user.id, "openai", "second-openai-key")

    assert get_provider_api_key(db, first_user.id, "openai") == "first-openai-key"
    assert get_provider_api_key(db, first_user.id, "gemini") == "first-gemini-key"
    assert get_provider_api_key(db, second_user.id, "openai") == "second-openai-key"
    assert get_provider_api_key(db, second_user.id, "gemini") == ""
    assert db.query(UserAIProviderCredential).count() == 3
