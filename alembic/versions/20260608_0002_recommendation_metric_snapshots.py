"""Add recommendation product metric snapshots.

Revision ID: 20260608_0002
Revises: 20260608_0001
Create Date: 2026-06-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260608_0002"
down_revision = "20260608_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recommended_packs", sa.Column("score_products", sa.Float(), nullable=True))
    op.add_column("recommended_packs", sa.Column("score_diversity", sa.Float(), nullable=True))

    op.add_column("recommended_pack_items", sa.Column("product_score", sa.Float(), nullable=True))
    op.add_column("recommended_pack_items", sa.Column("match_score", sa.Float(), nullable=True))
    op.add_column("recommended_pack_items", sa.Column("review_score", sa.Float(), nullable=True))
    op.add_column("recommended_pack_items", sa.Column("review_count", sa.Integer(), nullable=True))
    op.add_column("recommended_pack_items", sa.Column("avg_rating", sa.Float(), nullable=True))
    op.add_column("recommended_pack_items", sa.Column("bayesian_review_score", sa.Float(), nullable=True))
    op.add_column("recommended_pack_items", sa.Column("price_score", sa.Float(), nullable=True))
    op.add_column("recommended_pack_items", sa.Column("stock_score", sa.Float(), nullable=True))
    op.add_column("recommended_pack_items", sa.Column("traceability_score", sa.Float(), nullable=True))
    op.add_column("recommended_pack_items", sa.Column("pharmacy_diversity_score", sa.Float(), nullable=True))
    op.add_column("recommended_pack_items", sa.Column("freshness_score", sa.Float(), nullable=True))
    op.add_column(
        "recommended_pack_items",
        sa.Column("selection_metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recommended_pack_items", "selection_metrics_json")
    op.drop_column("recommended_pack_items", "freshness_score")
    op.drop_column("recommended_pack_items", "pharmacy_diversity_score")
    op.drop_column("recommended_pack_items", "traceability_score")
    op.drop_column("recommended_pack_items", "stock_score")
    op.drop_column("recommended_pack_items", "price_score")
    op.drop_column("recommended_pack_items", "bayesian_review_score")
    op.drop_column("recommended_pack_items", "avg_rating")
    op.drop_column("recommended_pack_items", "review_count")
    op.drop_column("recommended_pack_items", "review_score")
    op.drop_column("recommended_pack_items", "match_score")
    op.drop_column("recommended_pack_items", "product_score")

    op.drop_column("recommended_packs", "score_diversity")
    op.drop_column("recommended_packs", "score_products")
