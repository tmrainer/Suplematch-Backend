"""Add lab reports and biomarker results.

Revision ID: 20260608_0005
Revises: 20260608_0004
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260608_0005"
down_revision = "20260608_0004"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _has_table("lab_reports"):
        op.create_table(
            "lab_reports",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("source_type", sa.String(length=40), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=True),
            sa.Column("file_mime_type", sa.String(length=120), nullable=True),
            sa.Column("raw_text", sa.Text(), nullable=True),
            sa.Column("parsed_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("analysis_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("consent_health_data", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="processed"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_lab_reports_user_id", "lab_reports", ["user_id"])
        op.create_index("ix_lab_reports_source_type", "lab_reports", ["source_type"])
        op.create_index("ix_lab_reports_status", "lab_reports", ["status"])
        op.create_index("ix_lab_reports_created_at", "lab_reports", ["created_at"])
        op.create_index("ix_lab_reports_deleted_at", "lab_reports", ["deleted_at"])
        op.alter_column("lab_reports", "parsed_payload_json", server_default=None)
        op.alter_column("lab_reports", "analysis_json", server_default=None)
        op.alter_column("lab_reports", "consent_health_data", server_default=None)
        op.alter_column("lab_reports", "status", server_default=None)

    if not _has_table("lab_biomarker_results"):
        op.create_table(
            "lab_biomarker_results",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("lab_report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lab_reports.id", ondelete="CASCADE"), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("display_name", sa.String(length=180), nullable=False),
            sa.Column("value", sa.Float(), nullable=False),
            sa.Column("unit", sa.String(length=40), nullable=False),
            sa.Column("reference_low", sa.Float(), nullable=True),
            sa.Column("reference_high", sa.Float(), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("severity", sa.String(length=40), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("source_text", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_lab_biomarker_results_lab_report_id", "lab_biomarker_results", ["lab_report_id"])
        op.create_index("ix_lab_biomarker_results_code", "lab_biomarker_results", ["code"])
        op.create_index("ix_lab_biomarker_results_status", "lab_biomarker_results", ["status"])
        op.create_index("ix_lab_biomarker_results_severity", "lab_biomarker_results", ["severity"])


def downgrade() -> None:
    op.drop_index("ix_lab_biomarker_results_severity", table_name="lab_biomarker_results")
    op.drop_index("ix_lab_biomarker_results_status", table_name="lab_biomarker_results")
    op.drop_index("ix_lab_biomarker_results_code", table_name="lab_biomarker_results")
    op.drop_index("ix_lab_biomarker_results_lab_report_id", table_name="lab_biomarker_results")
    op.drop_table("lab_biomarker_results")
    op.drop_index("ix_lab_reports_deleted_at", table_name="lab_reports")
    op.drop_index("ix_lab_reports_created_at", table_name="lab_reports")
    op.drop_index("ix_lab_reports_status", table_name="lab_reports")
    op.drop_index("ix_lab_reports_source_type", table_name="lab_reports")
    op.drop_index("ix_lab_reports_user_id", table_name="lab_reports")
    op.drop_table("lab_reports")
