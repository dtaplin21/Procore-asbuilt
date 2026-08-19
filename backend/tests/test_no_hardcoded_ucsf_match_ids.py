"""Guard: match pipeline code must not hard-code UCSF evidence/drawing IDs or N/E."""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

SCAN_PATHS = (
    BACKEND_ROOT / "ai/pipelines/location_match_orchestrator.py",
    BACKEND_ROOT / "ai/pipelines/drawing_location_resolver.py",
    BACKEND_ROOT / "ai/pipelines/survey_point_matcher.py",
    BACKEND_ROOT / "services/match_candidate_scope.py",
    BACKEND_ROOT / "services/location_match_eval.py",
)

FORBIDDEN_LITERALS = (
    "2131764.84",
    "6051541.82",
    "evidence_id=357",
    "master_drawing_id=661",
    "drawing_id=661",
    "run_id=435",
    "inspection_run_id=435",
)


def test_match_pipeline_has_no_hardcoded_ucsf_ids() -> None:
    violations: list[str] = []
    for path in SCAN_PATHS:
        assert path.is_file(), f"Missing scan target: {path}"
        text = path.read_text(encoding="utf-8")
        for literal in FORBIDDEN_LITERALS:
            if literal in text:
                violations.append(f"{path.relative_to(BACKEND_ROOT)}: {literal!r}")

    assert not violations, (
        "Hard-coded UCSF match literals found in pipeline code:\n"
        + "\n".join(f"  - {item}" for item in violations)
    )
