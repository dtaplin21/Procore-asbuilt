"""Tests for outlier-robust similarity registration (Step 5)."""

from __future__ import annotations

import cmath
import math

from ai.pipelines.registration_solver import Anchor, register, screen_survey_rows


def _truth_transform() -> tuple[complex, complex]:
    a = 20 * cmath.exp(1j * math.radians(90))
    b = complex(6051000.0, 2131000.0)
    return a, b


def _mk(
    world_from_paper: tuple[complex, complex],
    pts: list[tuple[float, float]],
    noise: list[tuple[float, float]] | None = None,
) -> list[Anchor]:
    a, b = world_from_paper
    out: list[Anchor] = []
    for k, (x, y) in enumerate(pts):
        d = a * complex(x, -y) + b
        dx, dy = noise[k] if noise else (0.0, 0.0)
        out.append(Anchor(f"p{k}", (x, y), (d.real + dx, d.imag + dy)))
    return out


def test_clean_fit_registered_recovers_truth() -> None:
    a, b = _truth_transform()
    pts = [(5.5, 4.9), (8.8, 5.0), (12.0, 4.7), (6.0, 9.5), (14.0, 12.0)]
    r = register(_mk((a, b), pts), tol=1.0, expected_scale=20)
    assert r.status == "registered", r
    assert r.scale is not None and r.rotation_deg is not None
    assert abs(r.scale - 20) < 1e-6 and abs(r.rotation_deg - 90) < 1e-6
    e, n = r.apply(7.0, 6.0)
    d = a * complex(7.0, -6.0) + b
    assert abs(e - d.real) < 1e-6 and abs(n - d.imag) < 1e-6
    x, y = r.invert(e, n)
    assert abs(x - 7.0) < 1e-6 and abs(y - 6.0) < 1e-6


def test_gross_outlier_rejected() -> None:
    a, b = _truth_transform()
    pts = [(5.5, 4.9), (8.8, 5.0), (12.0, 4.7), (6.0, 9.5), (14.0, 12.0)]
    an = _mk((a, b), pts)
    an[2] = Anchor("p2", an[2].src, (an[2].dst[0] + 400, an[2].dst[1] - 250))
    r = register(an, tol=1.0, expected_scale=20)
    assert r.status == "registered" and r.outlier_ids == ["p2"], r
    assert len(r.inlier_ids) == 4


def test_noise_within_tol() -> None:
    a, b = _truth_transform()
    pts = [(5.5, 4.9), (8.8, 5.0), (12.0, 4.7), (6.0, 9.5), (14.0, 12.0)]
    noise = [(0.3, -0.2), (-0.4, 0.1), (0.2, 0.3), (0, -0.3), (0.1, 0.2)]
    r = register(_mk((a, b), pts, noise), tol=1.5)
    assert r.status == "registered" and r.rmse is not None and r.rmse < 0.5, r


def test_collinear_needs_review() -> None:
    a, b = _truth_transform()
    line = [(5.0, 5.0), (7.0, 5.0), (9.0, 5.0), (12.0, 5.0)]
    r = register(_mk((a, b), line), tol=1.0)
    assert r.status == "needs_review" and any("collinear" in x for x in r.reasons), r


def test_too_few_anchors() -> None:
    a, b = _truth_transform()
    pts = [(5.5, 4.9), (8.8, 5.0), (12.0, 4.7), (6.0, 9.5), (14.0, 12.0)]
    assert register(_mk((a, b), pts[:1]), tol=1.0).status == "insufficient"
    r = register(_mk((a, b), pts[:2]), tol=1.0)
    assert r.status == "needs_review" and any("no_redundancy" in x for x in r.reasons), r


def test_close_points_insufficient() -> None:
    a, b = _truth_transform()
    close = [(5.0, 5.0), (5.1, 5.0)]
    assert register(_mk((a, b), close), tol=1.0).status == "insufficient"


def test_scale_veto() -> None:
    a, b = _truth_transform()
    pts = [(5.5, 4.9), (8.8, 5.0), (12.0, 4.7), (6.0, 9.5), (14.0, 12.0)]
    a12 = 12 * cmath.exp(1j * math.radians(90))
    r = register(_mk((a12, b), pts), tol=1.0, expected_scale=20)
    assert r.status == "insufficient", r


def test_mirror_not_fully_registered() -> None:
    a, b = _truth_transform()
    pts = [(5.5, 4.9), (8.8, 5.0), (12.0, 4.7), (6.0, 9.5), (14.0, 12.0)]
    mir: list[Anchor] = []
    for k, (x, y) in enumerate(pts):
        d = a * complex(-x, -y) + b
        mir.append(Anchor(f"m{k}", (x, y), (d.real, d.imag)))
    r = register(mir, tol=1.0)
    assert r.status != "registered" or len(r.inlier_ids) < len(pts), r


def test_competing_consensus_ambiguous() -> None:
    a, b = _truth_transform()
    pts = [(5.5, 4.9), (8.8, 5.0), (12.0, 4.7), (6.0, 9.5), (14.0, 12.0)]
    A = _mk((a, b), pts[:3])
    Bk = _mk((a * cmath.exp(1j * math.radians(37)), b + 5000), pts[:3])
    mixed = A + [Anchor("q" + x.id, x.src, x.dst) for x in Bk]
    r = register(mixed, tol=1.0)
    assert r.status == "ambiguous", r


def test_screen_survey_rows() -> None:
    rows = [
        {"northing": 1, "easting": 10, "meta_json": {"pairing_distance_ft": 0.2}},
        {"northing": 2, "easting": 10, "meta_json": {"pairing_distance_ft": 2.8}},
        {"northing": 3, "easting": 30, "meta_json": {"pairing_distance_ft": 0.2}},
    ]
    kept, dropped = screen_survey_rows(rows)
    assert len(kept) == 2 and len(dropped) == 1
