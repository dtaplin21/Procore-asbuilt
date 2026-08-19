"""Load the transcribed legend/abbreviation data into the DB.

Usage (from ``backend/`` so ``.env`` and imports resolve)::

    cd backend
    ./venv/bin/python scripts/seed_legend_reference.py
    ./venv/bin/python scripts/seed_legend_reference.py --project-id 2 --source-sheet C0.00

When ``--project-id`` is omitted, rows are seeded with ``project_id=NULL`` as
general/global defaults usable across projects.
"""

from __future__ import annotations

import argparse
import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy.orm import Session

from data.legend_seed_data import ABBREVIATIONS, LINE_TYPES, SOURCE_SHEET, SYMBOLS
from database import SessionLocal
from models.legend_reference import (
    DrawingLegendAbbreviation,
    DrawingLegendLineType,
    DrawingLegendSymbol,
)


def seed(
    session: Session,
    project_id: int | None = None,
    source_sheet: str = SOURCE_SHEET,
) -> None:
    for abbrev, expansion, category in ABBREVIATIONS:
        existing = (
            session.query(DrawingLegendAbbreviation)
            .filter_by(project_id=project_id, abbreviation=abbrev)
            .one_or_none()
        )
        if existing:
            setattr(existing, "expansion", expansion)
            setattr(existing, "category", category)
            setattr(existing, "source_sheet", source_sheet)
        else:
            session.add(
                DrawingLegendAbbreviation(
                    project_id=project_id,
                    abbreviation=abbrev,
                    expansion=expansion,
                    category=category,
                    source_sheet=source_sheet,
                )
            )

    for name, code, category in LINE_TYPES:
        existing = (
            session.query(DrawingLegendLineType)
            .filter_by(project_id=project_id, line_type_name=name)
            .one_or_none()
        )
        if existing:
            setattr(existing, "abbreviation_code", code)
            setattr(existing, "category", category)
            setattr(existing, "source_sheet", source_sheet)
        else:
            session.add(
                DrawingLegendLineType(
                    project_id=project_id,
                    line_type_name=name,
                    abbreviation_code=code,
                    category=category,
                    source_sheet=source_sheet,
                )
            )

    for name, code, category in SYMBOLS:
        existing = (
            session.query(DrawingLegendSymbol)
            .filter_by(project_id=project_id, symbol_name=name)
            .one_or_none()
        )
        if existing:
            setattr(existing, "abbreviation_code", code)
            setattr(existing, "category", category)
            setattr(existing, "source_sheet", source_sheet)
        else:
            session.add(
                DrawingLegendSymbol(
                    project_id=project_id,
                    symbol_name=name,
                    abbreviation_code=code,
                    category=category,
                    source_sheet=source_sheet,
                )
            )

    session.commit()
    print(
        f"Seeded {len(ABBREVIATIONS)} abbreviations, {len(LINE_TYPES)} line types, "
        f"{len(SYMBOLS)} symbols (project_id={project_id})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed legend reference tables from C0.00 data.")
    parser.add_argument("--project-id", type=int, default=None)
    parser.add_argument("--source-sheet", default=SOURCE_SHEET)
    args = parser.parse_args()

    session = SessionLocal()
    try:
        seed(session, args.project_id, args.source_sheet)
    finally:
        session.close()


if __name__ == "__main__":
    main()
