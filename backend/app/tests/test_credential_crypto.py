"""Credential confidentiality, integrity, and server-setting storage contracts."""

import base64
import secrets
from datetime import timedelta

import pytest

from app.services.credential_crypto import (
    CredentialCipher,
    CredentialCryptoError,
    is_production_secret_key,
)


def test_credential_cipher_round_trips_without_exposing_plaintext():
    secret_key = secrets.token_urlsafe(48)
    plaintext = secrets.token_urlsafe(32) + "测试凭据"
    ciphertext = CredentialCipher.from_secret_key(secret_key).encrypt(plaintext)

    assert ciphertext.startswith("v1:")
    assert plaintext not in ciphertext
    assert secret_key not in ciphertext
    assert CredentialCipher.from_secret_key(secret_key).decrypt(ciphertext) == plaintext


def test_credential_cipher_uses_unique_nonce_for_same_plaintext():
    cipher = CredentialCipher.from_secret_key(secrets.token_urlsafe(48))
    plaintext = secrets.token_urlsafe(32)
    first = cipher.encrypt(plaintext)
    second = cipher.encrypt(plaintext)

    assert first != second
    first_data = base64.urlsafe_b64decode(first.split(":", 1)[1])
    second_data = base64.urlsafe_b64decode(second.split(":", 1)[1])
    assert first_data[:12] != second_data[:12]
    assert cipher.decrypt(first) == cipher.decrypt(second) == plaintext


def test_credential_cipher_rejects_tampering_and_wrong_secret_key():
    secret_key = secrets.token_urlsafe(48)
    plaintext = secrets.token_urlsafe(32)
    cipher = CredentialCipher.from_secret_key(secret_key)
    ciphertext = cipher.encrypt(plaintext)
    data = bytearray(base64.urlsafe_b64decode(ciphertext.split(":", 1)[1]))
    data[-1] ^= 1
    tampered = "v1:" + base64.urlsafe_b64encode(data).decode("ascii")
    wrong_key = secrets.token_urlsafe(48)
    wrong_cipher = CredentialCipher.from_secret_key(wrong_key)

    cases = [
        (cipher, tampered),
        (wrong_cipher, ciphertext),
        (cipher, "v2:" + ciphertext.split(":", 1)[1]),
        (cipher, "v1:!invalid"),
        (cipher, "v1:"),
        (cipher, ""),
    ]
    messages = []
    for decryptor, invalid_ciphertext in cases:
        with pytest.raises(CredentialCryptoError) as error:
            decryptor.decrypt(invalid_ciphertext)
        message = str(error.value)
        assert all(value not in message for value in (
            secret_key, wrong_key, ciphertext, tampered, plaintext,
        ))
        assert error.value.__suppress_context__
        messages.append(message)
    assert len(set(messages)) == 1


def test_production_secret_key_rejects_defaults_examples_and_short_values():
    for invalid_key in (
        "", "change-this-secret", "dev-secret-change-me-in-production",
        secrets.token_hex(15), "中" * 10, " " * 32,
    ):
        assert not is_production_secret_key(invalid_key)

    assert is_production_secret_key(secrets.token_hex(16))
    assert is_production_secret_key("中" * 11)


def test_production_secret_key_rejects_whitespace_padded_defaults():
    known_defaults = ("change-this-secret", "dev-secret-change-me-in-production")
    padding = " " * 32

    assert all(
        not is_production_secret_key(padding + default + padding)
        for default in known_defaults
    )


def test_system_setting_metadata_is_registered_without_generic_audit_payload():
    from app.models import Base

    assert "system_ai_settings" in Base.metadata.tables
    assert "system_config_audits" in Base.metadata.tables
    settings = Base.metadata.tables["system_ai_settings"]
    audit = Base.metadata.tables["system_config_audits"]
    assert {
        "enabled", "default_base_url", "trusted_base_url", "default_model",
        "connect_timeout_seconds", "read_timeout_seconds", "verify_tls",
        "access_client_id_ciphertext", "access_client_secret_ciphertext",
        "config_version", "updated_by", "created_at", "updated_at",
    } <= set(settings.columns.keys())
    assert set(audit.columns.keys()) == {
        "id", "action", "changed_fields", "config_version", "created_by", "created_at",
    }
    assert {fk.target_fullname for fk in settings.foreign_keys} == {"users.id"}
    assert {fk.target_fullname for fk in audit.foreign_keys} == {"users.id"}
    assert {tuple(column.name for column in index.columns) for index in audit.indexes} >= {
        ("action",), ("created_at",),
    }


def test_system_setting_timestamp_callables_return_utc_aware_values():
    from app.models import SystemAISetting, SystemConfigAudit

    setting_columns = SystemAISetting.__table__.c
    audit_columns = SystemConfigAudit.__table__.c
    timestamps = (
        setting_columns.created_at.default.arg(None),
        setting_columns.updated_at.default.arg(None),
        setting_columns.updated_at.onupdate.arg(None),
        audit_columns.created_at.default.arg(None),
    )

    assert all(timestamp.utcoffset() == timedelta(0) for timestamp in timestamps)


def test_system_setting_database_enforces_fixed_singleton_id(db):
    from sqlalchemy.exc import IntegrityError

    from app.models import SystemAISetting

    db.add(SystemAISetting())
    db.commit()
    setting = db.get(SystemAISetting, 1)
    assert setting is not None
    assert setting.config_version == 1

    db.add(SystemAISetting(id=2))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_system_config_audit_records_only_field_names_and_version(db):
    from app.models import SystemConfigAudit

    audit = SystemConfigAudit(
        action="update", changed_fields=["enabled", "default_model"], config_version=2,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)

    assert audit.changed_fields == ["enabled", "default_model"]
    assert audit.config_version == 2
    assert audit.created_at is not None
