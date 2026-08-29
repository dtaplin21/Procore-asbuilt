#!/usr/bin/env python3
"""Convert a pixel pick on a page PNG to fractional page coordinates.

Usage (from ``backend/``)::

    ./venv/bin/python scripts/pick_fractional_point.py \\
      --image tests/fixtures/digitization/aux_c420_page1.png --x 120 --y 400

Prints ``frac_x`` / ``frac_y`` (pixel / image size) for editing viewport bbox
corners in ``seed_drawing_viewports.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def pick_fractional_point(*, image_path: Path, x: float, y: float) -> tuple[float, float, int, int]:
    """Return (frac_x, frac_y, width, height) for a pixel on ``image_path``."""
    path = image_path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    with Image.open(path) as im:
        width, height = im.size
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid image size {width}x{height}")

    frac_x = float(x) / float(width)
    frac_y = float(y) / float(height)
    return frac_x, frac_y, width, height


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True, help="Page PNG path")
    parser.add_argument("--x", type=float, required=True, help="Pixel x (from left)")
    parser.add_argument("--y", type=float, required=True, help="Pixel y (from top)")
    args = parser.parse_args()

    frac_x, frac_y, width, height = pick_fractional_point(
        image_path=args.image,
        x=args.x,
        y=args.y,
    )
    print(f"image={args.image} size={width}x{height}")
    print(f"pixel=({args.x:g}, {args.y:g})")
    print(f"fractional=({frac_x:.6f}, {frac_y:.6f})")
    print(f"  # bbox corner hint: x={frac_x:.4f}, y={frac_y:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
