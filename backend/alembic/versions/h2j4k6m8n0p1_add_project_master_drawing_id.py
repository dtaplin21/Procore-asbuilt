"""add project master_drawing_id and partial unique one master per project

Revision ID: h2j4k6m8n0p1
Revises: f6702109ca94
Create Date: 2026-05-05

Phase B backfill (per project), after duplicate-master dedupe:

1. ``master_drawing_id`` ← lowest id among ``upload_intent = 'master'``, else lowest drawing id
   in the project; projects with no drawings stay NULL.

2. Set winning row explicitly: ``UPDATE drawings SET upload_intent = 'master' WHERE id = :master_id``
   (batch: all non-NULL ``projects.master_drawing_id``).

3. Demote any other ``upload_intent = 'master'`` not equal to the FK.

If multiple rows had ``upload_intent = 'master'`` for a project, logs ``project_id`` for support
before dedupe (smallest ``drawings.id`` is kept).

``downgrade()`` only drops the partial unique index, FK, and ``master_drawing_id`` column; it does
not restore prior ``upload_intent`` or FK values (not reversible).
"""

from __future__ import annotations

import sys

import sqlalchemy as sa
from alembic import op

revision = "h2j4k6m8n0p1"
down_revision = "f6702109ca94"
branch_labels = None
depends_on = None

MASTER_INTENT_WHERE = sa.text("upload_intent = 'master'")

_LOG_DUPLICATE_MASTERS = sa.text(
    """
    SELECT project_id, COUNT(*) AS cnt
    FROM drawings
    WHERE upload_intent = 'master'
    GROUP BY project_id
    HAVING COUNT(*) > 1
    """
)

# Keeps MIN(id) per project among upload_intent = 'master'; demotes the rest to 'sub'.
_DEDUPE_MASTER_INTENT = sa.text(
    """
    UPDATE drawings
    SET upload_intent = 'sub'
    WHERE upload_intent = 'master'
      AND id NOT IN (
          SELECT MIN(id)
          FROM drawings
          WHERE upload_intent = 'master'
          GROUP BY project_id
      )
    """
)

# Prefer explicit master (lowest id); else lowest drawing id in project; else leave NULL.
_BACKFILL_PROJECT_MASTER = sa.text(
    """
    UPDATE projects
    SET master_drawing_id = COALESCE(
        (
            SELECT MIN(d.id)
            FROM drawings d
            WHERE d.project_id = projects.id
              AND d.upload_intent = 'master'
        ),
        (
            SELECT MIN(d.id)
            FROM drawings d
            WHERE d.project_id = projects.id
        )
    )
    WHERE EXISTS (
        SELECT 1
        FROM drawings d
        WHERE d.project_id = projects.id
    )
    """
)

# Per project: UPDATE drawings SET upload_intent = 'master' WHERE id = :master_id
# (batch over all projects with a chosen master_drawing_id).
_SET_WINNING_ROW_MASTER_INTENT = sa.text(
    """
    UPDATE drawings
    SET upload_intent = 'master'
    WHERE id IN (
        SELECT master_drawing_id
        FROM projects
        WHERE master_drawing_id IS NOT NULL
    )
    """
)

# Any other drawing still marked master is not the canonical id — demote.
_DEMOTE_NON_CANONICAL_MASTER_INTENT = sa.text(
    """
    UPDATE drawings
    SET upload_intent = 'sub'
    WHERE upload_intent = 'master'
      AND id NOT IN (
          SELECT master_drawing_id
          FROM projects
          WHERE master_drawing_id IS NOT NULL
      )
    """
)


def _log_duplicate_master_conflicts(connection: sa.Connection) -> None:
    """If two+ rows had upload_intent='master' for a project, print project_id for support."""
    rows = connection.execute(_LOG_DUPLICATE_MASTERS).fetchall()
    for row in rows:
        project_id, cnt = row[0], row[1]
        print(
            f"[alembic {revision}] duplicate masters: project_id={project_id!r} "
            f"had {cnt} rows with upload_intent='master'; "
            f"dedupe keeps MIN(drawings.id) as master — review if unexpected",
            file=sys.stderr,
        )


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("master_drawing_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_master_drawing_id_drawings",
        "projects",
        "drawings",
        ["master_drawing_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_projects_master_drawing_id",
        "projects",
        ["master_drawing_id"],
        unique=False,
    )

    bind = op.get_bind()
    assert bind is not None
    _log_duplicate_master_conflicts(bind)

    op.execute(_DEDUPE_MASTER_INTENT)
    op.execute(_BACKFILL_PROJECT_MASTER)
    op.execute(_SET_WINNING_ROW_MASTER_INTENT)
    op.execute(_DEMOTE_NON_CANONICAL_MASTER_INTENT)

    dialect = bind.dialect.name
    if dialect == "postgresql":
        op.create_index(
            "uq_drawings_one_master_per_project",
            "drawings",
            ["project_id"],
            unique=True,
            postgresql_where=MASTER_INTENT_WHERE,
        )
    elif dialect == "sqlite":
        op.create_index(
            "uq_drawings_one_master_per_project",
            "drawings",
            ["project_id"],
            unique=True,
            sqlite_where=MASTER_INTENT_WHERE,
        )


def downgrade() -> None:
    """Drop index, FK, and column only — do not assume data reversibility."""
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    if dialect in ("postgresql", "sqlite"):
        op.drop_index(
            "uq_drawings_one_master_per_project",
            table_name="drawings",
        )

    op.drop_index("ix_projects_master_drawing_id", table_name="projects")
    op.drop_constraint(
        "fk_projects_master_drawing_id_drawings",
        "projects",
        type_="foreignkey",
    )
    op.drop_column("projects", "master_drawing_id")
