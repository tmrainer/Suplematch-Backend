"""catalog rs review queue

Revision ID: 20261022_0014
Revises: 20261022_0013
Create Date: 2026-10-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261022_0014"
down_revision = "20261022_0013"
branch_labels = None
depends_on = None

TABLE = "catalog_rs_reviews"


def _create_table_if_missing(inspector, table_name: str, *columns, **kwargs) -> None:
    if table_name not in inspector.get_table_names():
        op.create_table(table_name, *columns, **kwargs)


def _create_index_if_missing(inspector, table_name: str, index_name: str, columns: list[str]) -> None:
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _create_table_if_missing(
        inspector,
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pharmacy", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=160), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("commercial_name", sa.Text(), nullable=True),
        sa.Column("registro_sanitario_key", sa.String(length=80), nullable=False),
        sa.Column("digemid_producto", sa.Text(), nullable=True),
        sa.Column("digemid_composicion", sa.Text(), nullable=True),
        sa.Column("registro_sanitario_source", sa.String(length=80), nullable=True),
        sa.Column("match_reason", sa.Text(), nullable=True),
        sa.Column("sample_reason", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("pharmacy", "sku", "registro_sanitario_key", name="uq_catalog_rs_reviews_pharmacy_sku_rs"),
    )

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ("ix_catalog_rs_reviews_pharmacy", ["pharmacy"]),
        ("ix_catalog_rs_reviews_sku", ["sku"]),
        ("ix_catalog_rs_reviews_registro_sanitario_key", ["registro_sanitario_key"]),
        ("ix_catalog_rs_reviews_registro_sanitario_source", ["registro_sanitario_source"]),
        ("ix_catalog_rs_reviews_sample_reason", ["sample_reason"]),
        ("ix_catalog_rs_reviews_status", ["status"]),
        ("ix_catalog_rs_reviews_reviewer_user_id", ["reviewer_user_id"]),
        ("ix_catalog_rs_reviews_status_sample", ["status", "sample_reason"]),
    ]:
        _create_index_if_missing(inspector, TABLE, index_name, columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE in inspector.get_table_names():
        op.drop_table(TABLE)
