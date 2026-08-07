"""add location_match_labels eval table

Revision ID: g1l2m3a4b5e6
Revises: m5l6m7a8r9k0
Create Date: 2026-06-24

Ground-truth pins and expected outcomes for location-match evaluation.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g1l2m3a4b5e6"
down_revision = "m5l6m7a8r9k0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "location_match_labels",
        sa.Column("label_id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.Integer(),
            sa.ForeignKey("evidence_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "inspection_run_id",
            sa.Integer(),
            sa.ForeignKey("inspection_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "master_drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_fixture_path", sa.String(), nullable=True),
        sa.Column("master_bbox_json", sa.JSON(), nullable=False),
        sa.Column("expected_method", sa.String(), nullable=False),
        sa.Column("expected_match_status", sa.String(), nullable=False),
        sa.Column("rotation_deg", sa.Integer(), nullable=True),
        sa.Column(
            "has_coordinate_signal",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "has_station_signal",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "has_reference_signal",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("evidence_kind", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_location_match_labels_project_id",
        "location_match_labels",
        ["project_id"],
    )
    op.create_index(
        "ix_location_match_labels_master_drawing_id",
        "location_match_labels",
        ["master_drawing_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_location_match_labels_master_drawing_id",
        table_name="location_match_labels",
    )
    op.drop_index(
        "ix_location_match_labels_project_id",
        table_name="location_match_labels",
    )
    op.drop_table("location_match_labels")
