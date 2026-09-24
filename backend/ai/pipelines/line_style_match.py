"""Shared line-style signature distance (legend + raster classifiers)."""

from __future__ import annotations

from ai.pipelines.pdf_vector_line_extractor import LineStyleSignature


def signature_distance(a: LineStyleSignature, b: LineStyleSignature) -> float:
    return (
        abs(a.stroke_width_bucket - b.stroke_width_bucket) * 10.0
        + abs(a.mean_gap_len_frac - b.mean_gap_len_frac)
        + abs(a.mean_segment_len_frac - b.mean_segment_len_frac)
    )
