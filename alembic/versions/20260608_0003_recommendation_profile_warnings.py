"""Store profile warnings on recommendation sessions.

Revision ID: 20260608_0003
Revises: 20260608_0002
Create Date: 2026-06-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260608_0003"
down_revision = "20260608_0002"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if _has_column("recommendation_sessions", "profile_warnings_json"):
        return

    op.add_column(
        "recommendation_sessions",
        sa.Column(
            "profile_warnings_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("recommendation_sessions", "profile_warnings_json", server_default=None)


def downgrade() -> None:
    op.drop_column("recommendation_sessions", "profile_warnings_json")
