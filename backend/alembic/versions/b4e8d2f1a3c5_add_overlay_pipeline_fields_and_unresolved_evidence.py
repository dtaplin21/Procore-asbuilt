"""Add pipeline overlay fields and unresolved_evidence table.

Revision ID: b4e8d2f1a3c5
Revises: a3f9c1d8e2b4
Create Date: 2026-06-24

Additive migration for document-pipeline overlay persistence:
  - drawing_overlays: label, severity, confidence_label, inspection_date, tags_json
  - unresolved_evidence: rows for evidence map_document_to_overlays() could not place

Existing drawing_overlays.created_at remains the upload timestamp (uploaded_at in the
refactor plan docs). No backfill required.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b4e8d2f1a3c5"
down_revision = "a3f9c1d8e2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("drawing_overlays", sa.Column("label", sa.String(length=255), nullable=True))
    op.add_column("drawing_overlays", sa.Column("severity", sa.String(length=32), nullable=True))
    op.add_column(
        "drawing_overlays",
        sa.Column("confidence_label", sa.String(length=64), nullable=True),
    )
    op.add_column("drawing_overlays", sa.Column("inspection_date", sa.Date(), nullable=True))
    op.add_column(
        "drawing_overlays",
        sa.Column("tags_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_drawing_overlays_inspection_date",
        "drawing_overlays",
        ["inspection_date"],
    )

    op.create_table(
        "unresolved_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "evidence_id",
            sa.Integer(),
            sa.ForeignKey("evidence_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "inspection_run_id",
            sa.Integer(),
            sa.ForeignKey("inspection_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "master_drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("extracted_terms_json", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "resolved_by_human",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_unresolved_evidence_evidence_id", "unresolved_evidence", ["evidence_id"])
    op.create_index(
        "ix_unresolved_evidence_inspection_run_id",
        "unresolved_evidence",
        ["inspection_run_id"],
    )
    op.create_index(
        "ix_unresolved_evidence_master_drawing_id",
        "unresolved_evidence",
        ["master_drawing_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_unresolved_evidence_master_drawing_id", table_name="unresolved_evidence")
    op.drop_index("ix_unresolved_evidence_inspection_run_id", table_name="unresolved_evidence")
    op.drop_index("ix_unresolved_evidence_evidence_id", table_name="unresolved_evidence")
    op.drop_table("unresolved_evidence")

    op.drop_index("ix_drawing_overlays_inspection_date", table_name="drawing_overlays")
    op.drop_column("drawing_overlays", "tags_json")
    op.drop_column("drawing_overlays", "inspection_date")
    op.drop_column("drawing_overlays", "confidence_label")
    op.drop_column("drawing_overlays", "severity")
    op.drop_column("drawing_overlays", "label")
