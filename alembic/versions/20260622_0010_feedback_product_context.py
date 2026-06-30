"""feedback product context

Revision ID: 20260622_0010
Revises: 20260615_0009
Create Date: 2026-06-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260622_0010"
down_revision = "20260615_0009"
branch_labels = None
depends_on = None


def _add_column_if_missing(inspector, table_name: str, column_name: str, column) -> None:
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name not in existing:
        op.add_column(table_name, column)


def _create_index_if_missing(inspector, table_name: str, index_name: str, columns: list[str]) -> None:
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "recommendation_feedback" not in inspector.get_table_names():
        return

    _add_column_if_missing(
        inspector,
        "recommendation_feedback",
        "selected_product_ids_json",
        sa.Column("selected_product_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
    )
    _add_column_if_missing(
        inspector,
        "recommendation_feedback",
        "chosen_product_id",
        sa.Column("chosen_product_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    _add_column_if_missing(
        inspector,
        "recommendation_feedback",
        "product_context_json",
        sa.Column("product_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )

    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("recommendation_feedback")}
    if "fk_recommendation_feedback_chosen_product" not in existing_fks:
        op.create_foreign_key(
            "fk_recommendation_feedback_chosen_product",
            "recommendation_feedback",
            "commercial_products",
            ["chosen_product_id"],
            ["id"],
            ondelete="SET NULL",
        )
    _create_index_if_missing(
        inspector,
        "recommendation_feedback",
        "ix_recommendation_feedback_chosen_product_id",
        ["chosen_product_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_recommendation_feedback_chosen_product_id", table_name="recommendation_feedback")
    op.drop_constraint("fk_recommendation_feedback_chosen_product", "recommendation_feedback", type_="foreignkey")
    op.drop_column("recommendation_feedback", "product_context_json")
    op.drop_column("recommendation_feedback", "chosen_product_id")
    op.drop_column("recommendation_feedback", "selected_product_ids_json")
