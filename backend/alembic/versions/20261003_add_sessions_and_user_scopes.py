"""Add session records and user scoping for auth history.

Revision ID: 20261003_sessions
Revises: 20261002_auth
Create Date: 2026-10-03 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261003_sessions"
down_revision = "20261002_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("searches", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_searches_user_id"), "searches", ["user_id"], unique=False)
    op.add_column("emails", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_emails_user_id"), "emails", ["user_id"], unique=False)
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_token_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sessions_id"), "sessions", ["id"], unique=False)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_index(op.f("ix_sessions_session_token_hash"), "sessions", ["session_token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_sessions_session_token_hash"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_user_id"), table_name="sessions")
    op.drop_index(op.f("ix_sessions_id"), table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(op.f("ix_emails_user_id"), table_name="emails")
    op.drop_index(op.f("ix_searches_user_id"), table_name="searches")
    op.drop_column("emails", "user_id")
    op.drop_column("searches", "user_id")
    op.drop_column("users", "is_active")
