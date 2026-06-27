"""add region_id to drawing_overlays

Revision ID: b7e2a4f91c36
Revises: b4e8d2f1a3c5
Create Date: 2026-06-26

Additive, nullable FK column — no breaking change. Links a resolved
DrawingOverlay back to the specific drawing_regions row it matched
against (via drawing_location_resolver.py's MasterRegion.region_id),
which is what lets the Objects viewer know "this backend region has at
least one inspection linked to it" (RegionViewerState.inspected_bold per
the visual-model spec) instead of only knowing the region's tags.

Nullable because:
  - Case A (alignment) overlays may resolve with no matched_region at
    all (a successful visual registration with no overlapping known
    region — see drawing_location_resolver.py's _best_overlapping_region,
    which can return None).
  - Older overlays persisted before this column existed have no value to
    backfill from (region matching at the time didn't track this).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7e2a4f91c36"
down_revision = "b4e8d2f1a3c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drawing_overlays",
        sa.Column("region_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_drawing_overlays_region_id",
        "drawing_overlays",
        ["region_id"],
    )
    op.create_foreign_key(
        "fk_drawing_overlays_region_id_drawing_regions",
        "drawing_overlays",
        "drawing_regions",
        ["region_id"],
        ["id"],
        ondelete="SET NULL",
        # ON DELETE SET NULL: deleting a region (PR2's DELETE route)
        # should not cascade-delete the inspection history that pointed
        # at it — the overlay record (and its tags_json / inspection
        # date / status) is still meaningful even if the region geometry
        # it was once linked to gets removed. It just goes back to
        # having no region link, same as an unmatched overlay.
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_drawing_overlays_region_id_drawing_regions",
        "drawing_overlays",
        type_="foreignkey",
    )
    op.drop_index("ix_drawing_overlays_region_id", table_name="drawing_overlays")
    op.drop_column("drawing_overlays", "region_id")
