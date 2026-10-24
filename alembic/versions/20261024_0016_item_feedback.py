"""recommendation item feedback (calificacion 1-5 por suplemento)

Revision ID: 20261024_0016
Revises: 20261024_0015
Create Date: 2026-10-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261024_0016"
down_revision = "20261024_0015"
branch_labels = None
depends_on = None

TABLE = "recommendation_item_feedback"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("recommendation_feedback_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("recommendation_session_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("component_id", sa.String(length=120), nullable=False),
            sa.Column("condition_code", sa.String(length=120), nullable=True),
            sa.Column("context_key", sa.String(length=260), nullable=False),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("outcome_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["recommendation_feedback_id"], ["recommendation_feedback.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["recommendation_session_id"], ["recommendation_sessions.id"], ondelete="SET NULL"),
        )
    inspector = sa.inspect(bind)
    existing = {item["name"] for item in inspector.get_indexes(TABLE)}
    for index_name, columns in [
        ("ix_recommendation_item_feedback_recommendation_feedback_id", ["recommendation_feedback_id"]),
        ("ix_recommendation_item_feedback_user_id", ["user_id"]),
        ("ix_recommendation_item_feedback_recommendation_session_id", ["recommendation_session_id"]),
        ("ix_recommendation_item_feedback_component_id", ["component_id"]),
        ("ix_recommendation_item_feedback_condition_code", ["condition_code"]),
        ("ix_recommendation_item_feedback_context_key", ["context_key"]),
        ("ix_recommendation_item_feedback_created_at", ["created_at"]),
    ]:
        if index_name not in existing:
            op.create_index(index_name, TABLE, columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE in inspector.get_table_names():
        op.drop_table(TABLE)
