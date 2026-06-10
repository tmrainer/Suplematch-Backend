"""Add ingredient safety rules.

Revision ID: 20260608_0004
Revises: 20260608_0003
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260608_0004"
down_revision = "20260608_0003"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("ingredient_safety_rules"):
        return

    op.create_table(
        "ingredient_safety_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("ingredient_pattern", sa.Text(), nullable=False),
        sa.Column("restriction_code", sa.String(length=80), nullable=True),
        sa.Column("safety_condition_code", sa.String(length=80), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False, server_default="warn"),
        sa.Column("severity", sa.String(length=40), nullable=False, server_default="medium"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(length=120), nullable=False, server_default="system_seed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_ingredient_safety_rules_name"),
    )
    op.create_index("ix_ingredient_safety_rules_name", "ingredient_safety_rules", ["name"])
    op.create_index("ix_ingredient_safety_rules_restriction_code", "ingredient_safety_rules", ["restriction_code"])
    op.create_index("ix_ingredient_safety_rules_safety_condition_code", "ingredient_safety_rules", ["safety_condition_code"])
    op.create_index("ix_ingredient_safety_rules_action", "ingredient_safety_rules", ["action"])
    op.create_index("ix_ingredient_safety_rules_severity", "ingredient_safety_rules", ["severity"])
    op.create_index("ix_ingredient_safety_rules_active", "ingredient_safety_rules", ["active"])


def downgrade() -> None:
    op.drop_index("ix_ingredient_safety_rules_active", table_name="ingredient_safety_rules")
    op.drop_index("ix_ingredient_safety_rules_severity", table_name="ingredient_safety_rules")
    op.drop_index("ix_ingredient_safety_rules_action", table_name="ingredient_safety_rules")
    op.drop_index("ix_ingredient_safety_rules_safety_condition_code", table_name="ingredient_safety_rules")
    op.drop_index("ix_ingredient_safety_rules_restriction_code", table_name="ingredient_safety_rules")
    op.drop_index("ix_ingredient_safety_rules_name", table_name="ingredient_safety_rules")
    op.drop_table("ingredient_safety_rules")
