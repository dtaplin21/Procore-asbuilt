import { describe, expect, it } from "vitest";

import {
  geometryToFractionalBbox,
  polygonFromPoints,
  rectFromDragPoints,
  validateGeometry,
} from "@/lib/drawing-regions/geometry";

describe("drawing-regions geometry", () => {
  it("normalizes a drag rect regardless of direction", () => {
    const geometry = rectFromDragPoints(
      { x: 200, y: 160 },
      { x: 100, y: 80 },
      1000,
      800,
    );

    expect(geometry).toEqual({
      type: "rect",
      x: 0.1,
      y: 0.1,
      width: 0.1,
      height: 0.1,
    });
    expect(validateGeometry(geometry)).toBeNull();
  });

  it("builds polygon draft with rect hit box and polygon_points", () => {
    const draft = polygonFromPoints(
      [
        { x: 100, y: 550 },
        { x: 450, y: 550 },
        { x: 450, y: 750 },
        { x: 100, y: 750 },
      ],
      1000,
      1000,
    );

    expect(draft.geometry).toEqual({
      type: "rect",
      x: 0.1,
      y: 0.55,
      width: 0.35,
      height: 0.2,
    });
    expect(draft.polygon_points).toEqual([
      [0.1, 0.55],
      [0.45, 0.55],
      [0.45, 0.75],
      [0.1, 0.75],
    ]);
  });

  it("converts geometry to fractional bbox", () => {
    expect(
      geometryToFractionalBbox({
        type: "rect",
        x: 0.1,
        y: 0.2,
        width: 0.3,
        height: 0.4,
      }),
    ).toEqual([0.1, 0.2, 0.4, expect.closeTo(0.6)]);

    expect(
      geometryToFractionalBbox({
        type: "polygon",
        points: [
          [0.1, 0.1],
          [0.5, 0.1],
          [0.5, 0.4],
        ],
      }),
    ).toEqual([0.1, 0.1, 0.5, 0.4]);
  });

  it("rejects polygons with fewer than three points", () => {
    expect(() =>
      polygonFromPoints(
        [
          { x: 0, y: 0 },
          { x: 10, y: 10 },
        ],
        100,
        100,
      ),
    ).toThrow(/at least 3 points/);
  });
});
