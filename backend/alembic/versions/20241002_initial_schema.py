"""Initial BuyerBridge schema

Revision ID: 20241002_initial
Revises: 
Create Date: 2026-10-02 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20241002_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "buyers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("email_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("contact_source", sa.String(length=255), nullable=True),
        sa.Column("relevance_score", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_buyers_id"), "buyers", ["id"], unique=False)

    op.create_table(
        "searches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_category", sa.String(length=200), nullable=False),
        sa.Column("product_description", sa.Text(), nullable=False),
        sa.Column("buyer_type", sa.String(length=200), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("country", sa.String(length=200), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_searches_id"), "searches", ["id"], unique=False)

    op.create_table(
        "emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_emails_id"), "emails", ["id"], unique=False)
    op.create_index(op.f("ix_emails_buyer_id"), "emails", ["buyer_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_emails_buyer_id"), table_name="emails")
    op.drop_index(op.f("ix_emails_id"), table_name="emails")
    op.drop_table("emails")
    op.drop_index(op.f("ix_searches_id"), table_name="searches")
    op.drop_table("searches")
    op.drop_index(op.f("ix_buyers_id"), table_name="buyers")
    op.drop_table("buyers")
