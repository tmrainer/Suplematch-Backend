"""recommendation events, feedback context key and outcomes

Revision ID: 20261022_0013
Revises: 20260630_0012
Create Date: 2026-10-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261022_0013"
down_revision = "20260630_0012"
branch_labels = None
depends_on = None

HEALTHY_CONDITION = "SALUDABLE"
PRINCIPAL_CONDITIONS_LIMIT = 3


def _create_table_if_missing(inspector, table_name: str, *columns, **kwargs) -> None:
    if table_name not in inspector.get_table_names():
        op.create_table(table_name, *columns, **kwargs)


def _add_column_if_missing(inspector, table_name: str, column_name: str, column) -> None:
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name not in existing:
        op.add_column(table_name, column)


def _create_index_if_missing(inspector, table_name: str, index_name: str, columns: list[str]) -> None:
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def _drop_index_if_exists(inspector, table_name: str, index_name: str) -> None:
    if table_name not in inspector.get_table_names():
        return
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)


def _drop_column_if_exists(inspector, table_name: str, column_name: str) -> None:
    existing = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name in existing:
        op.drop_column(table_name, column_name)


def _context_key(pack_key, conditions) -> str | None:
    """Replica de app.domains.feedback.contexto.build_context_key (la migracion no importa app/)."""
    key = str(pack_key or "").strip()
    if not key:
        return None
    picked: list[str] = []
    seen: set[str] = set()
    for raw in conditions or []:
        text = str(raw or "").strip()
        if not text or text.upper() == HEALTHY_CONDITION or text in seen:
            continue
        seen.add(text)
        picked.append(text)
        if len(picked) >= PRINCIPAL_CONDITIONS_LIMIT:
            break
    return f"{key}|{'+'.join(sorted(picked))}"


def _backfill_feedback_context_keys(bind) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT id, pack_key, conditions_context_json FROM recommendation_feedback "
            "WHERE context_key IS NULL AND pack_key IS NOT NULL"
        )
    ).fetchall()
    for row in rows:
        conditions = row[2] if isinstance(row[2], list) else []
        key = _context_key(row[1], conditions)
        if key is None:
            continue
        bind.execute(
            sa.text("UPDATE recommendation_feedback SET context_key = :key WHERE id = :id"),
            {"key": key, "id": row[0]},
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _create_table_if_missing(
        inspector,
        "recommendation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("recommendation_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("anonymous_session_id", sa.String(length=120), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("pack_key", sa.String(length=160), nullable=True),
        sa.Column("component_id", sa.String(length=120), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("conditions_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("context_key", sa.String(length=400), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["recommendation_session_id"], ["recommendation_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["commercial_products.id"], ondelete="SET NULL"),
    )
    inspector = sa.inspect(bind)
    for index_name, columns in (
        ("ix_recommendation_events_recommendation_session_id", ["recommendation_session_id"]),
        ("ix_recommendation_events_user_id", ["user_id"]),
        ("ix_recommendation_events_anonymous_session_id", ["anonymous_session_id"]),
        ("ix_recommendation_events_event_type", ["event_type"]),
        ("ix_recommendation_events_pack_key", ["pack_key"]),
        ("ix_recommendation_events_product_id", ["product_id"]),
        ("ix_recommendation_events_context_key", ["context_key"]),
        ("ix_recommendation_events_created_at", ["created_at"]),
        ("ix_recommendation_events_session_type", ["recommendation_session_id", "event_type"]),
        ("ix_recommendation_events_context_type", ["context_key", "event_type"]),
    ):
        _create_index_if_missing(inspector, "recommendation_events", index_name, columns)

    if "recommendation_feedback" not in inspector.get_table_names():
        return

    _add_column_if_missing(
        inspector,
        "recommendation_feedback",
        "context_key",
        sa.Column("context_key", sa.String(length=400), nullable=True),
    )
    _add_column_if_missing(
        inspector,
        "recommendation_feedback",
        "outcome_json",
        sa.Column("outcome_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "recommendation_feedback", "ix_recommendation_feedback_context_key", ["context_key"])
    _backfill_feedback_context_keys(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "recommendation_feedback" in inspector.get_table_names():
        _drop_index_if_exists(inspector, "recommendation_feedback", "ix_recommendation_feedback_context_key")
        _drop_column_if_exists(inspector, "recommendation_feedback", "outcome_json")
        _drop_column_if_exists(inspector, "recommendation_feedback", "context_key")

    if "recommendation_events" in inspector.get_table_names():
        op.drop_table("recommendation_events")
