"""Encrypted global AI server settings and value-free configuration audit.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_ai_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_base_url", sa.String(2048), nullable=False, server_default=""),
        sa.Column("trusted_base_url", sa.String(2048), nullable=False, server_default=""),
        sa.Column("default_model", sa.String(120), nullable=False, server_default=""),
        sa.Column("connect_timeout_seconds", sa.Float(), nullable=False, server_default="20"),
        sa.Column("read_timeout_seconds", sa.Float(), nullable=False, server_default="180"),
        sa.Column("verify_tls", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("access_client_id_ciphertext", sa.Text(), nullable=True),
        sa.Column("access_client_secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_system_ai_settings_singleton"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "system_config_audits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_system_config_audits_action", "system_config_audits", ["action"])
    op.create_index("idx_system_config_audits_created_at", "system_config_audits", ["created_at"])


def downgrade() -> None:
    op.drop_table("system_config_audits")
    op.drop_table("system_ai_settings")
