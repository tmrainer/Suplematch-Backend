"""catalog jobs and price snapshots

Revision ID: 20260623_0011
Revises: 20260622_0010
Create Date: 2026-06-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260623_0011"
down_revision = "20260622_0010"
branch_labels = None
depends_on = None


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
        "catalog_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("returncode", sa.Integer(), nullable=True),
        sa.Column("log_path", sa.Text(), nullable=True),
        sa.Column("requested_params_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("diff_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cancelled_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )

    _create_table_if_missing(
        inspector,
        "product_price_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("catalog_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pharmacy", sa.String(length=160), nullable=False),
        sa.Column("sku", sa.String(length=160), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("commercial_name", sa.Text(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("availability", sa.String(length=40), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=True),
        sa.Column("registro_sanitario", sa.String(length=80), nullable=True),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["product_id"], ["commercial_products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["catalog_job_id"], ["catalog_jobs.id"], ondelete="SET NULL"),
    )

    inspector = sa.inspect(bind)
    for table, indexes in {
        "catalog_jobs": [
            ("ix_catalog_jobs_requested_by_user_id", ["requested_by_user_id"]),
            ("ix_catalog_jobs_status", ["status"]),
            ("ix_catalog_jobs_mode", ["mode"]),
            ("ix_catalog_jobs_started_at", ["started_at"]),
            ("ix_catalog_jobs_finished_at", ["finished_at"]),
            ("ix_catalog_jobs_created_at", ["created_at"]),
        ],
        "product_price_snapshots": [
            ("ix_product_price_snapshots_product_id", ["product_id"]),
            ("ix_product_price_snapshots_catalog_job_id", ["catalog_job_id"]),
            ("ix_product_price_snapshots_pharmacy", ["pharmacy"]),
            ("ix_product_price_snapshots_sku", ["sku"]),
            ("ix_product_price_snapshots_availability", ["availability"]),
            ("ix_product_price_snapshots_registro_sanitario", ["registro_sanitario"]),
            ("ix_product_price_snapshots_seen_at", ["seen_at"]),
            ("ix_product_price_snapshots_product_seen", ["product_id", "seen_at"]),
        ],
    }.items():
        for index_name, columns in indexes:
            _create_index_if_missing(inspector, table, index_name, columns)


def downgrade() -> None:
    op.drop_table("product_price_snapshots")
    op.drop_table("catalog_jobs")
