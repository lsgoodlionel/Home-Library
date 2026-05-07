"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("idx_users_username", "users", ["username"])
    op.create_index("idx_users_role", "users", ["role"])
    op.create_index("idx_users_status", "users", ["status"])

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("idx_categories_code", "categories", ["code"])
    op.create_index("idx_categories_parent_id", "categories", ["parent_id"])

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("room", sa.String(80), nullable=False),
        sa.Column("shelf", sa.String(80), nullable=False),
        sa.Column("layer", sa.String(80), nullable=True),
        sa.Column("position", sa.String(120), nullable=True),
        sa.Column("full_path", sa.String(400), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room", "shelf", "layer", "position", name="uq_locations_path"),
    )
    op.create_index("idx_locations_room", "locations", ["room"])
    op.create_index("idx_locations_shelf", "locations", ["shelf"])
    op.create_index("idx_locations_full_path", "locations", ["full_path"])

    op.create_table(
        "books",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("subtitle", sa.String(255), nullable=True),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("translator", sa.String(255), nullable=True),
        sa.Column("publisher", sa.String(255), nullable=True),
        sa.Column("publish_year", sa.Integer(), nullable=True),
        sa.Column("isbn", sa.String(32), nullable=True),
        sa.Column("original_isbn", sa.String(64), nullable=True),
        sa.Column("language", sa.String(32), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("binding", sa.String(64), nullable=True),
        sa.Column("series", sa.String(255), nullable=True),
        sa.Column("cover_url", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("author_intro", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("read_status", sa.String(20), nullable=False, server_default="unread"),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_books_title", "books", ["title"])
    op.create_index("idx_books_author", "books", ["author"])
    op.create_index("idx_books_isbn", "books", ["isbn"])
    op.create_index("idx_books_publisher", "books", ["publisher"])
    op.create_index("idx_books_category_id", "books", ["category_id"])
    op.create_index("idx_books_location_id", "books", ["location_id"])
    op.create_index("idx_books_status", "books", ["status"])
    op.create_index("idx_books_read_status", "books", ["read_status"])
    op.create_index("idx_books_created_at", "books", ["created_at"])

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "book_tags",
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"]),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"]),
        sa.PrimaryKeyConstraint("book_id", "tag_id"),
    )
    op.create_index("idx_book_tags_book_id", "book_tags", ["book_id"])
    op.create_index("idx_book_tags_tag_id", "book_tags", ["tag_id"])

    op.create_table(
        "borrow_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("borrower_name", sa.String(120), nullable=False),
        sa.Column("borrower_contact", sa.String(255), nullable=True),
        sa.Column("borrowed_at", sa.Date(), nullable=False),
        sa.Column("due_at", sa.Date(), nullable=True),
        sa.Column("returned_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_borrow_records_book_id", "borrow_records", ["book_id"])
    op.create_index("idx_borrow_records_status", "borrow_records", ["status"])
    op.create_index("idx_borrow_records_due_at", "borrow_records", ["due_at"])

    op.create_table(
        "reading_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.Date(), nullable=True),
        sa.Column("finished_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_reading_notes_book_id", "reading_notes", ["book_id"])
    op.create_index("idx_reading_notes_user_id", "reading_notes", ["user_id"])

    op.create_table(
        "external_book_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("query", sa.String(500), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("raw_data", sa.Text(), nullable=False),
        sa.Column("normalized_data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_external_book_results_query", "external_book_results", ["query"])
    op.create_index("idx_external_book_results_source", "external_book_results", ["source"])
    op.create_index("idx_external_book_results_source_id", "external_book_results", ["source_id"])

    op.create_table(
        "ai_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_type", sa.String(80), nullable=False),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("input_data", sa.Text(), nullable=False),
        sa.Column("output_data", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ai_tasks_task_type", "ai_tasks", ["task_type"])
    op.create_index("idx_ai_tasks_model", "ai_tasks", ["model"])
    op.create_index("idx_ai_tasks_status", "ai_tasks", ["status"])

    op.create_table(
        "user_ai_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("active_provider", sa.String(40), nullable=False, server_default="ollama"),
        sa.Column("default_model", sa.String(120), nullable=False, server_default=""),
        sa.Column("provider_configs", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_ai_settings")
    op.drop_table("ai_tasks")
    op.drop_table("external_book_results")
    op.drop_table("reading_notes")
    op.drop_table("borrow_records")
    op.drop_table("book_tags")
    op.drop_table("tags")
    op.drop_table("books")
    op.drop_table("locations")
    op.drop_table("categories")
    op.drop_table("users")
