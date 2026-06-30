"""profile age and weight

Revision ID: 20260615_0009
Revises: 20260615_0008
Create Date: 2026-06-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260615_0009"
down_revision = "20260615_0008"
branch_labels = None
depends_on = None


def _add_column_if_missing(inspector, table_name: str, column_name: str, column) -> None:
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name not in existing:
        op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_profiles" not in inspector.get_table_names():
        return

    _add_column_if_missing(inspector, "user_profiles", "age_years", sa.Column("age_years", sa.Integer(), nullable=True))
    _add_column_if_missing(inspector, "user_profiles", "weight_value", sa.Column("weight_value", sa.Float(), nullable=True))
    _add_column_if_missing(inspector, "user_profiles", "weight_unit", sa.Column("weight_unit", sa.String(length=24), nullable=True))
    _add_column_if_missing(inspector, "user_profiles", "weight_kg", sa.Column("weight_kg", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "weight_kg")
    op.drop_column("user_profiles", "weight_unit")
    op.drop_column("user_profiles", "weight_value")
    op.drop_column("user_profiles", "age_years")
