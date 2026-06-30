"""profile height

Revision ID: 20260630_0012
Revises: 20260623_0011
Create Date: 2026-06-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260630_0012"
down_revision = "20260623_0011"
branch_labels = None
depends_on = None


def _add_column_if_missing(inspector, table_name: str, column_name: str, column) -> None:
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name not in existing:
        op.add_column(table_name, column)


def _drop_column_if_exists(inspector, table_name: str, column_name: str) -> None:
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name in existing:
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_profiles" not in inspector.get_table_names():
        return

    _add_column_if_missing(inspector, "user_profiles", "height_value", sa.Column("height_value", sa.Float(), nullable=True))
    _add_column_if_missing(inspector, "user_profiles", "height_unit", sa.Column("height_unit", sa.String(length=24), nullable=True))
    _add_column_if_missing(inspector, "user_profiles", "height_cm", sa.Column("height_cm", sa.Float(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_profiles" not in inspector.get_table_names():
        return

    _drop_column_if_exists(inspector, "user_profiles", "height_cm")
    _drop_column_if_exists(inspector, "user_profiles", "height_unit")
    _drop_column_if_exists(inspector, "user_profiles", "height_value")
