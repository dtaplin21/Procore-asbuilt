"""Ensure compare/diff HTTP routes and drawing_compare jobs are removed."""

from __future__ import annotations

import re

import pytest

COMPARE_PATH_RE = re.compile(r"/drawings/compare/")
DIFFS_PATH_RE = re.compile(r"/drawings/\{[^}]+\}/diffs")


def test_no_compare_or_diff_routes_registered() -> None:
    from main import app

    paths = sorted({getattr(route, "path", "") for route in app.routes if hasattr(route, "path")})
    for path in paths:
        assert not COMPARE_PATH_RE.search(path), f"compare route still registered: {path}"
        assert not DIFFS_PATH_RE.search(path), f"diffs route still registered: {path}"


@pytest.mark.parametrize(
    "module_path",
    [
        "services.job_worker",
        "services.drawing_render_jobs",
    ],
)
def test_drawing_compare_not_a_recognized_job_type(module_path: str) -> None:
    import importlib

    module = importlib.import_module(module_path)
    source = open(module.__file__, encoding="utf-8").read()
    assert "drawing_compare" not in source, f"{module_path} still references drawing_compare"
