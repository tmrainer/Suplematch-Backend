"""Initial PostgreSQL relational schema.

Revision ID: 20260608_0001
Revises:
Create Date: 2026-06-08
"""

from __future__ import annotations

from alembic import op

from app.db.models import Base


revision = "20260608_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
