"""add inspection_type_tags and location_tags to drawing_regions

Revision ID: a3f9c1d8e2b4
Revises: p7p2c0m9p8a1
Create Date: 2026-06-24

Additive, nullable columns — no breaking change, no backfill required to
deploy. Existing rows get NULL/empty arrays until someone tags them
(manually, or via a backfill script — see the note at the bottom of this
file). Matches the additive-migration pattern used elsewhere in the
drawing-workspace refactor (PR7).

This is what backend/services/region_index_loader.py reads from to build
the MasterRegion list that backend/ai/pipelines/drawing_location_resolver.py
matches uploaded evidence against.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# --- Alembic identifiers -----------------------------------------------
revision = "a3f9c1d8e2b4"
down_revision = "p7p2c0m9p8a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drawing_regions",
        sa.Column(
            "inspection_type_tags",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "drawing_regions",
        sa.Column(
            "location_tags",
            postgresql.ARRAY(sa.String()),
            nullable=True,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    # GIN indexes make "does this region have tag X" lookups fast once
    # the region index loader is querying by tag rather than loading
    # every region for a drawing (see region_index_loader.py — current
    # version loads all regions for a drawing and filters in Python,
    # which is fine at expected per-drawing region counts; revisit if a
    # single drawing ever has hundreds of regions).
    op.execute(
        "CREATE INDEX ix_drawing_regions_inspection_type_tags "
        "ON drawing_regions USING GIN (inspection_type_tags)"
    )
    op.execute(
        "CREATE INDEX ix_drawing_regions_location_tags "
        "ON drawing_regions USING GIN (location_tags)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_drawing_regions_location_tags")
    op.execute("DROP INDEX IF EXISTS ix_drawing_regions_inspection_type_tags")
    op.drop_column("drawing_regions", "location_tags")
    op.drop_column("drawing_regions", "inspection_type_tags")


# ---------------------------------------------------------------------------
# Backfill note
# ---------------------------------------------------------------------------
# This migration does NOT backfill existing drawing_regions rows with
# real tag data — there's no automatic way to infer "what inspection type
# happens here" / "what is this place called" from existing geometry
# alone. Two realistic backfill paths, neither handled by this migration:
#
#   1. Manual: a reviewer goes through each project's regions once and
#      tags them via whatever admin/region-editing UI exists or gets
#      built for this.
#   2. Semi-automatic: run the existing term_extractor.py /
#      positioned_term_extractor.py against any ALREADY-CLOSED historical
#      inspection records tied to each region (if such records exist with
#      free-text notes) to suggest tags for human confirmation.
#
# Until a region has at least one tag in either column, it is simply
# invisible to Case B reference-lookup matching — that's the correct,
# safe default (no guessing), not a bug.
