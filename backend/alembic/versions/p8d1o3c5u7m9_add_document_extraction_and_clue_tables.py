"""add document extraction and clue tables

Revision ID: p8d1o3c5u7m9
Revises: p4r1q3u5e7i1
Create Date: 2026-06-24

Stores classification/extraction output and searchable clues for the
clue-based inspection matching pipeline. Confidence fields are backend-only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p8d1o3c5u7m9"
down_revision = "p4r1q3u5e7i1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.String(), nullable=False),
        sa.Column("document_type", sa.String(), nullable=False),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("universal_fields_json", sa.JSON(), nullable=True),
        sa.Column("type_specific_fields_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_table(
        "document_clues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_extraction_id",
            sa.Integer(),
            sa.ForeignKey("document_extractions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("clue_type", sa.String(), nullable=False),
        sa.Column("clue_value", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("location_relevant", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_document_extractions_file_id",
        "document_extractions",
        ["file_id"],
    )
    op.create_index(
        "ix_document_clues_extraction",
        "document_clues",
        ["document_extraction_id"],
    )
    op.create_index(
        "ix_document_clues_value",
        "document_clues",
        ["clue_value"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_clues_value", table_name="document_clues")
    op.drop_index("ix_document_clues_extraction", table_name="document_clues")
    op.drop_index("ix_document_extractions_file_id", table_name="document_extractions")
    op.drop_table("document_clues")
    op.drop_table("document_extractions")
