"""survey step events (embudo de la encuesta)

Revision ID: 20261024_0015
Revises: 20261022_0014
Create Date: 2026-10-24 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261024_0015"
down_revision = "20261022_0014"
branch_labels = None
depends_on = None

TABLE = "survey_step_events"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("survey_session_id", sa.String(length=80), nullable=False),
            sa.Column("step_key", sa.String(length=80), nullable=False),
            sa.Column("event_type", sa.String(length=20), nullable=False),
            sa.Column("position", sa.Integer(), nullable=True),
            sa.Column("visible_steps", sa.Integer(), nullable=True),
            sa.Column("contract_version", sa.String(length=20), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        )
    inspector = sa.inspect(bind)
    existing = {item["name"] for item in inspector.get_indexes(TABLE)}
    for index_name, columns in [
        ("ix_survey_step_events_user_id", ["user_id"]),
        ("ix_survey_step_events_survey_session_id", ["survey_session_id"]),
        ("ix_survey_step_events_step_key", ["step_key"]),
        ("ix_survey_step_events_event_type", ["event_type"]),
        ("ix_survey_step_events_created_at", ["created_at"]),
        ("ix_survey_step_events_session_step", ["survey_session_id", "step_key"]),
    ]:
        if index_name not in existing:
            op.create_index(index_name, TABLE, columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE in inspector.get_table_names():
        op.drop_table(TABLE)
