"""PR 7.2 — deprecate compare-stack schema (post PR1–6).

Migration table (historical revisions are NOT edited; this revision applies forward DDL):

| Revision / area | Action in this migration | Notes |
|-----------------|--------------------------|-------|
| f6702109ca94 (upload_intent) | DROP column + check constraint | Canonical master is ``projects.master_drawing_id`` |
| 61eebd8aec0e (regions + alignments) | KEEP ``drawing_regions``; DROP ``drawing_alignments`` | Archive to ``drawing_alignments_legacy`` first |
| a1b2c3d4e5f6 (drawing_diffs) | Archive → ``drawing_diffs_legacy``; DROP table | Optional legacy retention per audit |
| e8f9a0b1c2d3 (alignments.project_id) | Superseded by alignments drop | — |
| h2j4k6m8n0p1 (master_drawing_id) | KEEP | Canonical master FK unchanged |
| 94abb60704c6 (inspection_runs / overlays) | KEEP; tighten overlays | Drop ``diff_id``; require ``inspection_run_id`` |
| p3p1a5c7e9g1 / p4p1i5n8r0u1 (reviews) | ADD ``overlay_id``; DROP ``alignment_id`` | Run-scoped reviews only |

Revision ID: p7p2c0m9p8a1
Revises: p4p1i5n8r0u1
Create Date: 2026-06-24

Downgrade recreates compare tables from ``*_legacy`` archives when present; does not restore
``upload_intent`` values or alignment-scoped review rows deleted during upgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "p7p2c0m9p8a1"
down_revision = "p4p1i5n8r0u1"
branch_labels = None
depends_on = None


def _table_exists(bind: sa.engine.Connection, name: str) -> bool:
    return name in inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    if not _table_exists(bind, table):
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1) Archive compare tables (legacy retention)
    # ------------------------------------------------------------------
    if _table_exists(bind, "drawing_diffs") and not _table_exists(bind, "drawing_diffs_legacy"):
        op.execute(sa.text("CREATE TABLE drawing_diffs_legacy AS TABLE drawing_diffs WITH DATA"))

    if _table_exists(bind, "drawing_alignments") and not _table_exists(
        bind, "drawing_alignments_legacy"
    ):
        op.execute(
            sa.text("CREATE TABLE drawing_alignments_legacy AS TABLE drawing_alignments WITH DATA")
        )

    # ------------------------------------------------------------------
    # 2) Overlays: drop diff-backed rows; require inspection_run_id
    # ------------------------------------------------------------------
    if _table_exists(bind, "drawing_overlays"):
        op.execute(
            sa.text(
                "DELETE FROM drawing_overlays WHERE diff_id IS NOT NULL OR inspection_run_id IS NULL"
            )
        )
        op.drop_constraint(
            "ck_drawing_overlays_exactly_one_source",
            "drawing_overlays",
            type_="check",
        )
        if _column_exists(bind, "drawing_overlays", "diff_id"):
            op.drop_index("ix_drawing_overlays_diff_id", table_name="drawing_overlays")
            op.drop_column("drawing_overlays", "diff_id")
        op.create_check_constraint(
            "ck_drawing_overlays_inspection_run_required",
            "drawing_overlays",
            "inspection_run_id IS NOT NULL",
        )

    # ------------------------------------------------------------------
    # 3) Findings: drop optional diff pointer
    # ------------------------------------------------------------------
    if _column_exists(bind, "findings", "drawing_diff_id"):
        op.drop_constraint(
            "fk_findings_drawing_diff_id_drawing_diffs",
            "findings",
            type_="foreignkey",
        )
        op.drop_index("ix_findings_drawing_diff_id", table_name="findings")
        op.drop_column("findings", "drawing_diff_id")

    # ------------------------------------------------------------------
    # 4) Drop drawing_diffs (after dependent FKs removed)
    # ------------------------------------------------------------------
    if _table_exists(bind, "drawing_diffs"):
        op.drop_table("drawing_diffs")

    # ------------------------------------------------------------------
    # 5) Inspection reviews: overlay_id; drop alignment scope
    # ------------------------------------------------------------------
    if _table_exists(bind, "drawing_inspection_reviews"):
        op.execute(
            sa.text(
                "DELETE FROM drawing_inspection_reviews "
                "WHERE inspection_run_id IS NULL"
            )
        )
        if not _column_exists(bind, "drawing_inspection_reviews", "overlay_id"):
            op.add_column(
                "drawing_inspection_reviews",
                sa.Column(
                    "overlay_id",
                    sa.Integer(),
                    sa.ForeignKey("drawing_overlays.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
            op.create_index(
                "ix_drawing_inspection_reviews_overlay_id",
                "drawing_inspection_reviews",
                ["overlay_id"],
            )
        if _column_exists(bind, "drawing_inspection_reviews", "alignment_id"):
            op.drop_constraint(
                "ck_drawing_inspection_reviews_scope",
                "drawing_inspection_reviews",
                type_="check",
            )
            op.drop_index(
                "ix_drawing_inspection_reviews_alignment_id",
                table_name="drawing_inspection_reviews",
            )
            op.drop_column("drawing_inspection_reviews", "alignment_id")
        op.create_check_constraint(
            "ck_drawing_inspection_reviews_run_required",
            "drawing_inspection_reviews",
            "inspection_run_id IS NOT NULL",
        )

    # ------------------------------------------------------------------
    # 6) Drop drawing_alignments (sub-compare table)
    # ------------------------------------------------------------------
    if _table_exists(bind, "drawing_alignments"):
        op.drop_table("drawing_alignments")

    # ------------------------------------------------------------------
    # 7) Drop upload_intent (canonical master via projects.master_drawing_id)
    # ------------------------------------------------------------------
    if _column_exists(bind, "drawings", "upload_intent"):
        op.drop_constraint("ck_drawings_upload_intent_valid", "drawings", type_="check")
        op.drop_column("drawings", "upload_intent")


def downgrade() -> None:
    bind = op.get_bind()

    if not _column_exists(bind, "drawings", "upload_intent"):
        op.add_column(
            "drawings",
            sa.Column("upload_intent", sa.String(length=16), nullable=True),
        )
        op.create_check_constraint(
            "ck_drawings_upload_intent_valid",
            "drawings",
            "upload_intent IN ('master', 'sub') OR upload_intent IS NULL",
        )

    if not _table_exists(bind, "drawing_alignments") and _table_exists(
        bind, "drawing_alignments_legacy"
    ):
        op.execute(
            sa.text(
                "CREATE TABLE drawing_alignments AS TABLE drawing_alignments_legacy WITH DATA"
            )
        )

    if _table_exists(bind, "drawing_inspection_reviews"):
        op.drop_constraint(
            "ck_drawing_inspection_reviews_run_required",
            "drawing_inspection_reviews",
            type_="check",
        )
        if not _column_exists(bind, "drawing_inspection_reviews", "alignment_id"):
            op.add_column(
                "drawing_inspection_reviews",
                sa.Column(
                    "alignment_id",
                    sa.Integer(),
                    sa.ForeignKey("drawing_alignments.id", ondelete="CASCADE"),
                    nullable=True,
                ),
            )
            op.create_index(
                "ix_drawing_inspection_reviews_alignment_id",
                "drawing_inspection_reviews",
                ["alignment_id"],
            )
        if _column_exists(bind, "drawing_inspection_reviews", "overlay_id"):
            op.drop_index(
                "ix_drawing_inspection_reviews_overlay_id",
                table_name="drawing_inspection_reviews",
            )
            op.drop_column("drawing_inspection_reviews", "overlay_id")
        op.create_check_constraint(
            "ck_drawing_inspection_reviews_scope",
            "drawing_inspection_reviews",
            "(alignment_id is not null)::int + (inspection_run_id is not null)::int = 1",
        )

    if not _table_exists(bind, "drawing_diffs") and _table_exists(bind, "drawing_diffs_legacy"):
        op.execute(sa.text("CREATE TABLE drawing_diffs AS TABLE drawing_diffs_legacy WITH DATA"))

    if not _column_exists(bind, "findings", "drawing_diff_id"):
        op.add_column(
            "findings",
            sa.Column("drawing_diff_id", sa.Integer(), nullable=True),
        )
        op.create_index(
            "ix_findings_drawing_diff_id",
            "findings",
            ["drawing_diff_id"],
        )
        if _table_exists(bind, "drawing_diffs"):
            op.create_foreign_key(
                "fk_findings_drawing_diff_id_drawing_diffs",
                "findings",
                "drawing_diffs",
                ["drawing_diff_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if _table_exists(bind, "drawing_overlays") and not _column_exists(
        bind, "drawing_overlays", "diff_id"
    ):
        op.drop_constraint(
            "ck_drawing_overlays_inspection_run_required",
            "drawing_overlays",
            type_="check",
        )
        op.add_column(
            "drawing_overlays",
            sa.Column(
                "diff_id",
                sa.Integer(),
                sa.ForeignKey("drawing_diffs.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index("ix_drawing_overlays_diff_id", "drawing_overlays", ["diff_id"])
        op.create_check_constraint(
            "ck_drawing_overlays_exactly_one_source",
            "drawing_overlays",
            "(inspection_run_id is not null)::int + (diff_id is not null)::int = 1",
        )
