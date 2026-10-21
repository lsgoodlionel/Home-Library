"""Alembic coverage for encrypted account provider credential migration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.services.credential_crypto import CredentialCipher


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ACCOUNT_KEY_PURPOSE = b"home-library:user-ai-provider-key:v1"
_STRONG_SECRET_KEY = "migration-test-strong-secret-key-value-0001"


def _alembic_config(database_url: str) -> Config:
    config = Config(str(_BACKEND_DIR / "alembic" / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _seed_revision_0002(database_url: str, provider_configs: dict[str, object]) -> None:
    config = _alembic_config(database_url)
    command.upgrade(config, "0002")
    engine = sa.create_engine(database_url)
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO users (
                    id, username, password_hash, display_name, role, status,
                    created_at, updated_at
                ) VALUES (
                    1, 'migration-user', 'hash', 'Migration User', 'member',
                    'active', :now, :now
                )
                """
            ),
            {"now": now},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO user_ai_settings (
                    id, user_id, active_provider, default_model,
                    provider_configs, created_at, updated_at
                ) VALUES (
                    1, 1, 'ollama', 'model', :provider_configs, :now, :now
                )
                """
            ),
            {"provider_configs": json.dumps(provider_configs), "now": now},
        )
    engine.dispose()


def _set_raw_provider_configs(database_url: str, raw_provider_configs: str) -> None:
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                UPDATE user_ai_settings
                SET provider_configs = :provider_configs
                WHERE id = 1
                """
            ),
            {"provider_configs": raw_provider_configs},
        )
    engine.dispose()


def test_upgrade_adds_ai_enabled_and_provider_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration-schema.sqlite3'}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", _STRONG_SECRET_KEY)
    _seed_revision_0002(database_url, {"ollama": {"api_key": ""}})

    command.upgrade(_alembic_config(database_url), "head")

    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    assert "ai_enabled" in {column["name"] for column in inspector.get_columns("user_ai_settings")}
    assert "user_ai_provider_credentials" in inspector.get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT ai_enabled FROM user_ai_settings WHERE id = 1")) == 1
    engine.dispose()


def test_upgrade_encrypts_and_removes_plaintext_provider_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration-data.sqlite3'}"
    source_key = "legacy-provider-key-marker"
    configs = {
        "ollama": {"api_key": "", "base_url": "http://localhost:11434"},
        "openai": {"api_key": source_key, "base_url": "https://api.openai.com/v1"},
    }
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", _STRONG_SECRET_KEY)
    _seed_revision_0002(database_url, configs)

    command.upgrade(_alembic_config(database_url), "head")

    engine = sa.create_engine(database_url)
    with engine.connect() as connection:
        migrated_json = connection.scalar(
            sa.text("SELECT provider_configs FROM user_ai_settings WHERE id = 1")
        )
        row = connection.execute(
            sa.text(
                """
                SELECT user_id, provider, api_key_ciphertext
                FROM user_ai_provider_credentials
                """
            )
        ).one()
    engine.dispose()

    migrated_configs = json.loads(migrated_json)
    assert "api_key" not in migrated_configs["ollama"]
    assert "api_key" not in migrated_configs["openai"]
    assert row.user_id == 1
    assert row.provider == "openai"
    assert row.api_key_ciphertext.startswith("v1:")
    assert source_key not in row.api_key_ciphertext
    assert CredentialCipher.from_secret_key(
        _STRONG_SECRET_KEY,
        purpose=_ACCOUNT_KEY_PURPOSE,
    ).decrypt(row.api_key_ciphertext) == source_key


def test_upgrade_rolls_back_plaintext_cleanup_when_encryption_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration-rollback.sqlite3'}"
    source_key = "legacy-provider-key-must-survive"
    original_configs = {"openai": {"api_key": source_key}}
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", "change-this-secret")
    _seed_revision_0002(database_url, original_configs)

    with pytest.raises(Exception):
        command.upgrade(_alembic_config(database_url), "head")

    engine = sa.create_engine(database_url)
    with engine.connect() as connection:
        stored_json = connection.scalar(
            sa.text("SELECT provider_configs FROM user_ai_settings WHERE id = 1")
        )
        revision = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
    engine.dispose()

    assert json.loads(stored_json) == original_configs
    assert source_key in stored_json
    assert revision == "0002"


def test_downgrade_refuses_to_restore_provider_credentials_as_plaintext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration-downgrade.sqlite3'}"
    source_key = "downgrade-plaintext-must-not-appear"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", _STRONG_SECRET_KEY)
    _seed_revision_0002(database_url, {"openai": {"api_key": source_key}})
    config = _alembic_config(database_url)
    command.upgrade(config, "head")

    with pytest.raises(RuntimeError) as error:
        command.downgrade(config, "0002")

    engine = sa.create_engine(database_url)
    with engine.connect() as connection:
        revision = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
        provider_configs = connection.scalar(
            sa.text("SELECT provider_configs FROM user_ai_settings WHERE id = 1")
        )
        ciphertext = connection.scalar(
            sa.text(
                """
                SELECT api_key_ciphertext
                FROM user_ai_provider_credentials
                WHERE user_id = 1 AND provider = 'openai'
                """
            )
        )
    engine.dispose()

    assert revision == "0003"
    assert source_key not in provider_configs
    assert source_key not in str(error.value)
    assert ciphertext.startswith("v1:")


@pytest.mark.parametrize("raw_provider_configs", ["{", "[]", "null"])
def test_upgrade_rejects_malformed_or_non_object_provider_configs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_provider_configs: str,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration-invalid-json.sqlite3'}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", _STRONG_SECRET_KEY)
    _seed_revision_0002(database_url, {"ollama": {"api_key": ""}})
    _set_raw_provider_configs(database_url, raw_provider_configs)

    with pytest.raises(RuntimeError):
        command.upgrade(_alembic_config(database_url), "head")

    engine = sa.create_engine(database_url)
    with engine.connect() as connection:
        revision = connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
        stored_configs = connection.scalar(
            sa.text("SELECT provider_configs FROM user_ai_settings WHERE id = 1")
        )
    engine.dispose()

    assert revision == "0002"
    assert stored_configs == raw_provider_configs


def test_upgrade_write_failure_hides_ciphertext_and_original_parameters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration-write-failure.sqlite3'}"
    source_key = "migration-write-plaintext-marker"
    ciphertext_marker = "v1:migration-write-ciphertext-marker"
    raw_parameter_marker = "migration-write-original-parameter-marker"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("HOME_LIBRARY_SECRET_KEY", _STRONG_SECRET_KEY)
    _seed_revision_0002(
        database_url,
        {
            "openai": {
                "api_key": source_key,
                "base_url": f"https://{raw_parameter_marker}.example.test",
            }
        },
    )

    real_encrypt = CredentialCipher.encrypt
    real_decrypt = CredentialCipher.decrypt

    def synthetic_encrypt(cipher: CredentialCipher, plaintext: str) -> str:
        if plaintext == source_key:
            return ciphertext_marker
        return real_encrypt(cipher, plaintext)

    def synthetic_decrypt(cipher: CredentialCipher, ciphertext: str) -> str:
        if ciphertext == ciphertext_marker:
            return source_key
        return real_decrypt(cipher, ciphertext)

    real_execute = sa.engine.Connection.execute
    observed_hide_parameters: list[bool] = []

    def fail_credential_insert(
        connection: sa.engine.Connection,
        statement: object,
        parameters: object = None,
        *args: object,
        **kwargs: object,
    ) -> object:
        if "INSERT INTO user_ai_provider_credentials" in str(statement):
            observed_hide_parameters.append(connection.engine.hide_parameters)
            raise sa.exc.StatementError(
                "synthetic migration write failure",
                str(statement),
                parameters,
                RuntimeError(raw_parameter_marker),
                hide_parameters=connection.engine.hide_parameters,
            )
        return real_execute(connection, statement, parameters, *args, **kwargs)

    monkeypatch.setattr(CredentialCipher, "encrypt", synthetic_encrypt)
    monkeypatch.setattr(CredentialCipher, "decrypt", synthetic_decrypt)
    monkeypatch.setattr(sa.engine.Connection, "execute", fail_credential_insert)

    with pytest.raises(RuntimeError) as caught:
        command.upgrade(_alembic_config(database_url), "head")

    failure = caught.value
    with caplog.at_level(logging.ERROR):
        logging.getLogger("migration.sanitized").error(
            "migration failed",
            exc_info=(type(failure), failure, failure.__traceback__),
        )
    rendered = f"{failure!s}\n{failure!r}\n{caplog.text}"
    assert observed_hide_parameters == [True]
    assert source_key not in rendered
    assert ciphertext_marker not in rendered
    assert raw_parameter_marker not in rendered
    assert failure.__cause__ is None
    assert failure.__context__ is None

    engine = sa.create_engine(database_url)
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == "0002"
    engine.dispose()
