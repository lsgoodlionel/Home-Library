"""Alembic coverage for encrypted account provider credential migration."""

from __future__ import annotations

import json
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
