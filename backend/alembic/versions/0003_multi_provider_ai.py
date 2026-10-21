"""Encrypted account AI provider credentials.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from alembic import op
import sqlalchemy as sa

from app.core.config import Settings
from app.services.credential_crypto import CredentialCipher, is_production_secret_key


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


_ACCOUNT_KEY_PURPOSE = b"home-library:user-ai-provider-key:v1"


def _cipher() -> CredentialCipher:
    secret_key = Settings().secret_key
    if not is_production_secret_key(secret_key):
        raise RuntimeError("账号供应商凭据迁移需要安全的应用密钥")
    return CredentialCipher.from_secret_key(secret_key, purpose=_ACCOUNT_KEY_PURPOSE)


def _prepare_upgrades(
    rows: list[sa.Row[Any]],
) -> list[tuple[int, int, str, list[tuple[str, str]]]]:
    parsed_rows: list[tuple[int, int, dict[str, Any], list[tuple[str, str]]]] = []
    has_legacy_key = False
    for row in rows:
        try:
            configs = json.loads(row.provider_configs)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(configs, dict):
            continue

        plaintext_keys: list[tuple[str, str]] = []
        for provider, provider_config in configs.items():
            if not isinstance(provider, str) or not isinstance(provider_config, dict):
                continue
            api_key = provider_config.get("api_key")
            if isinstance(api_key, str) and api_key != "":
                has_legacy_key = True
                plaintext_keys.append((provider, api_key))
            provider_config.pop("api_key", None)
        parsed_rows.append((row.id, row.user_id, configs, plaintext_keys))

    cipher = _cipher() if has_legacy_key else None
    prepared: list[tuple[int, int, str, list[tuple[str, str]]]] = []
    for setting_id, user_id, configs, plaintext_keys in parsed_rows:
        encrypted_keys: list[tuple[str, str]] = []
        for provider, api_key in plaintext_keys:
            assert cipher is not None
            ciphertext = cipher.encrypt(api_key)
            if cipher.decrypt(ciphertext) != api_key:
                raise RuntimeError("账号供应商凭据迁移验证失败")
            encrypted_keys.append((provider, ciphertext))
        prepared.append(
            (
                setting_id,
                user_id,
                json.dumps(configs, ensure_ascii=False, sort_keys=True),
                encrypted_keys,
            )
        )
    return prepared


def upgrade() -> None:
    connection = op.get_bind()
    rows = list(
        connection.execute(
            sa.text("SELECT id, user_id, provider_configs FROM user_ai_settings")
        ).mappings()
    )
    prepared = _prepare_upgrades(rows)

    op.add_column(
        "user_ai_settings",
        sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "user_ai_provider_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            name="uq_user_ai_provider_credentials_user_provider",
        ),
    )

    now = datetime.now(timezone.utc)
    for setting_id, user_id, provider_configs, encrypted_keys in prepared:
        for provider, ciphertext in encrypted_keys:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO user_ai_provider_credentials (
                        user_id, provider, api_key_ciphertext, created_at, updated_at
                    ) VALUES (
                        :user_id, :provider, :ciphertext, :now, :now
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "provider": provider,
                    "ciphertext": ciphertext,
                    "now": now,
                },
            )
        connection.execute(
            sa.text(
                """
                UPDATE user_ai_settings
                SET provider_configs = :provider_configs
                WHERE id = :setting_id
                """
            ),
            {"provider_configs": provider_configs, "setting_id": setting_id},
        )


def downgrade() -> None:
    connection = op.get_bind()
    credential_rows = list(
        connection.execute(
            sa.text(
                """
                SELECT user_id, provider, api_key_ciphertext
                FROM user_ai_provider_credentials
                """
            )
        ).mappings()
    )
    credentials_by_user: dict[int, list[tuple[str, str]]] = {}
    if credential_rows:
        cipher = _cipher()
        for row in credential_rows:
            api_key = cipher.decrypt(row.api_key_ciphertext)
            credentials_by_user.setdefault(row.user_id, []).append((row.provider, api_key))

    setting_rows = list(
        connection.execute(
            sa.text("SELECT id, user_id, provider_configs FROM user_ai_settings")
        ).mappings()
    )
    for row in setting_rows:
        try:
            configs = json.loads(row.provider_configs)
        except (TypeError, json.JSONDecodeError):
            configs = {}
        if not isinstance(configs, dict):
            configs = {}
        for provider, api_key in credentials_by_user.get(row.user_id, []):
            provider_config = configs.setdefault(provider, {})
            if isinstance(provider_config, dict):
                provider_config["api_key"] = api_key
        connection.execute(
            sa.text(
                """
                UPDATE user_ai_settings
                SET provider_configs = :provider_configs
                WHERE id = :setting_id
                """
            ),
            {
                "provider_configs": json.dumps(configs, ensure_ascii=False, sort_keys=True),
                "setting_id": row.id,
            },
        )

    op.drop_table("user_ai_provider_credentials")
    op.drop_column("user_ai_settings", "ai_enabled")
