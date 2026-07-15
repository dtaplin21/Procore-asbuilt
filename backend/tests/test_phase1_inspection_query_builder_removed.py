"""Phase 1 — legacy inspection_query_builder removal checks.

Verifies the old regex-only inspection query builder is not present and that
no runtime code imports it or its search-term / find_candidate_tiles helpers.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PIPELINES_DIR = BACKEND_ROOT / "ai" / "pipelines"

LEGACY_MODULE = "inspection_query_builder"
LEGACY_SYMBOLS = frozenset(
    {
        "inspection_query_builder",
        "find_candidate_tiles",
        "build_search_terms",
        "search_terms",
    }
)

SKIP_DIRS = frozenset({".venv", "__pycache__", ".pytest_cache", "alembic"})


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[-1])
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[-1])
                names.add(node.module)
            for alias in node.names:
                names.add(alias.name)
    return names


def test_inspection_query_builder_module_does_not_exist():
    legacy_path = PIPELINES_DIR / f"{LEGACY_MODULE}.py"
    assert not legacy_path.exists(), (
        f"Legacy module still exists at {legacy_path}. "
        "Delete it and route matching through the clue pipeline."
    )


def test_no_runtime_imports_of_legacy_inspection_query_builder():
    offenders: list[str] = []

    for path in _iter_python_files(BACKEND_ROOT):
        if path.name == Path(__file__).name:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue

        imported = _imported_names(tree)
        hits = sorted(imported & LEGACY_SYMBOLS)
        if hits:
            offenders.append(f"{path.relative_to(BACKEND_ROOT)}: {', '.join(hits)}")

        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if (
                f"from ai.pipelines.{LEGACY_MODULE}" in stripped
                or f"import {LEGACY_MODULE}" in stripped
                or f"pipelines.{LEGACY_MODULE}" in stripped
            ):
                offenders.append(
                    f"{path.relative_to(BACKEND_ROOT)}: imports legacy module"
                )
                break

    assert offenders == [], (
        "Legacy inspection query builder references found:\n"
        + "\n".join(offenders)
    )


def test_clue_pipeline_modules_exist_for_replacement():
    """Replacement foundation from later phases must be importable."""
    from ai.pipelines.clue_extractor import build_clues
    from ai.schemas.document_extraction_schemas import Clue, DocumentType, UniversalFields

    clues = build_clues(
        DocumentType.UNKNOWN,
        UniversalFields(location_text="COLO"),
        None,
    )
    assert len(clues) == 1
    assert isinstance(clues[0], Clue)
    assert clues[0].value == "COLO"
