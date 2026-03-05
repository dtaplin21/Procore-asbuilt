"""add inspection_runs inspection_results drawing_overlays

Revision ID: 94abb60704c6
Revises: e7f8a9b0c1d2
Create Date: 2026-03-05 11:56:55.804851

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '94abb60704c6'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------
    # inspection_runs
    # -------------------------
    op.create_table(
        "inspection_runs",
        sa.Column("id", sa.Integer(), primary_key=True),

        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "master_drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_id",
            sa.Integer(),
            sa.ForeignKey("evidence_records.id", ondelete="SET NULL"),
            nullable=True,
        ),

        sa.Column("inspection_type", sa.String(), nullable=True),

        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.CheckConstraint(
            "status in ('queued','processing','complete','failed')",
            name="ck_inspection_runs_status",
        ),

        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),

        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_inspection_runs_project_id", "inspection_runs", ["project_id"])
    op.create_index("ix_inspection_runs_master_drawing_id", "inspection_runs", ["master_drawing_id"])
    op.create_index("ix_inspection_runs_evidence_id", "inspection_runs", ["evidence_id"])
    op.create_index("ix_inspection_runs_status", "inspection_runs", ["status"])
    op.create_index("ix_inspection_runs_project_id_created_at", "inspection_runs", ["project_id", "created_at"])

    # -------------------------
    # inspection_results
    # -------------------------
    op.create_table(
        "inspection_results",
        sa.Column("id", sa.Integer(), primary_key=True),

        sa.Column(
            "inspection_run_id",
            sa.Integer(),
            sa.ForeignKey("inspection_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),

        sa.Column("outcome", sa.String(), nullable=False, server_default="unknown"),
        sa.CheckConstraint(
            "outcome in ('pass','fail','mixed','unknown')",
            name="ck_inspection_results_outcome",
        ),

        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_inspection_results_inspection_run_id", "inspection_results", ["inspection_run_id"])
    op.create_index("ix_inspection_results_outcome", "inspection_results", ["outcome"])
    op.create_index(
        "ix_inspection_results_inspection_run_id_created_at",
        "inspection_results",
        ["inspection_run_id", "created_at"],
    )

    # -------------------------
    # drawing_overlays
    # -------------------------
    op.create_table(
        "drawing_overlays",
        sa.Column("id", sa.Integer(), primary_key=True),

        sa.Column(
            "master_drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),

        sa.Column(
            "inspection_run_id",
            sa.Integer(),
            sa.ForeignKey("inspection_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),

        # You confirmed drawing_diffs exists (migration a1b2c3d4e5f6), so this FK is valid:
        sa.Column(
            "diff_id",
            sa.Integer(),
            sa.ForeignKey("drawing_diffs.id", ondelete="SET NULL"),
            nullable=True,
        ),

        sa.Column("geometry", sa.JSON(), nullable=False),

        sa.Column("status", sa.String(), nullable=False, server_default="unknown"),
        sa.CheckConstraint(
            "status in ('pass','fail','unknown')",
            name="ck_drawing_overlays_status",
        ),

        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_drawing_overlays_master_drawing_id", "drawing_overlays", ["master_drawing_id"])
    op.create_index("ix_drawing_overlays_inspection_run_id", "drawing_overlays", ["inspection_run_id"])
    op.create_index("ix_drawing_overlays_diff_id", "drawing_overlays", ["diff_id"])
    op.create_index("ix_drawing_overlays_status", "drawing_overlays", ["status"])
    op.create_index(
        "ix_drawing_overlays_master_drawing_id_created_at",
        "drawing_overlays",
        ["master_drawing_id", "created_at"],
    )

    # OPTIONAL DB-level enforcement of your rule:
    # exactly one of inspection_run_id or diff_id must be set.
    # If you truly want "free overlays", do NOT add this.
    op.create_check_constraint(
        "ck_drawing_overlays_exactly_one_source",
        "drawing_overlays",
        "(inspection_run_id is not null)::int + (diff_id is not null)::int = 1"
    )



def downgrade() -> None:
     # drawing_overlays (drop constraint + indexes first)
    op.drop_constraint("ck_drawing_overlays_exactly_one_source", "drawing_overlays", type_="check")
    op.drop_index("ix_drawing_overlays_master_drawing_id_created_at", table_name="drawing_overlays")
    op.drop_index("ix_drawing_overlays_status", table_name="drawing_overlays")
    op.drop_index("ix_drawing_overlays_diff_id", table_name="drawing_overlays")
    op.drop_index("ix_drawing_overlays_inspection_run_id", table_name="drawing_overlays")
    op.drop_index("ix_drawing_overlays_master_drawing_id", table_name="drawing_overlays")
    op.drop_table("drawing_overlays")

    # inspection_results
    op.drop_index("ix_inspection_results_inspection_run_id_created_at", table_name="inspection_results")
    op.drop_index("ix_inspection_results_outcome", table_name="inspection_results")
    op.drop_index("ix_inspection_results_inspection_run_id", table_name="inspection_results")
    op.drop_table("inspection_results")

    # inspection_runs
    op.drop_index("ix_inspection_runs_project_id_created_at", table_name="inspection_runs")
    op.drop_index("ix_inspection_runs_status", table_name="inspection_runs")
    op.drop_index("ix_inspection_runs_evidence_id", table_name="inspection_runs")
    op.drop_index("ix_inspection_runs_master_drawing_id", table_name="inspection_runs")
    op.drop_index("ix_inspection_runs_project_id", table_name="inspection_runs")
    op.drop_table("inspection_runs")

