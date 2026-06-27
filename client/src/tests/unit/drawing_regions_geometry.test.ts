/**
 * client/src/tests/unit/drawing_regions_geometry.test.ts
 */

import { describe, it, expect } from "vitest";
import {
  geometryToFractionalBbox,
  polygonFromPoints,
  polygonPointsToFractional,
  rectFromDragPoints,
  validateGeometry,
} from "@/lib/drawing-regions/geometry";

describe("rectFromDragPoints", () => {
  it("builds a normalized rect from top-left to bottom-right drag", () => {
    const geometry = rectFromDragPoints({ x: 10, y: 20 }, { x: 60, y: 80 }, 1000, 1000);
    expect(geometry).toEqual({
      type: "rect",
      x: 0.01,
      y: 0.02,
      width: 0.05,
      height: 0.06,
    });
  });

  it("normalizes a reverse drag (bottom-right to top-left) to the same rect", () => {
    const forward = rectFromDragPoints({ x: 10, y: 20 }, { x: 60, y: 80 }, 1000, 1000);
    const reverse = rectFromDragPoints({ x: 60, y: 80 }, { x: 10, y: 20 }, 1000, 1000);
    expect(reverse).toEqual(forward);
  });

  it("handles a diagonal drag in the other direction", () => {
    const geometry = rectFromDragPoints({ x: 60, y: 20 }, { x: 10, y: 80 }, 1000, 1000);
    expect(geometry.x).toBe(0.01);
    expect(geometry.y).toBe(0.02);
    expect(geometry.width).toBe(0.05);
    expect(geometry.height).toBe(0.06);
  });
});

describe("polygonFromPoints", () => {
  it("builds geometry with bbox derived from polygon extent", () => {
    const points = [{ x: 10, y: 10 }, { x: 50, y: 10 }, { x: 30, y: 60 }];
    const draft = polygonFromPoints(points, 1000, 1000);
    expect(draft.geometry.x).toBe(0.01);
    expect(draft.geometry.y).toBe(0.01);
    expect(draft.geometry.width).toBe(0.04);
    expect(draft.geometry.height).toBe(0.05);
    expect(draft.polygon_points).toEqual([
      [0.01, 0.01],
      [0.05, 0.01],
      [0.03, 0.06],
    ]);
  });

  it("throws if fewer than 3 points are given", () => {
    expect(() => polygonFromPoints([{ x: 0, y: 0 }, { x: 1, y: 1 }], 1000, 1000)).toThrow(
      /at least 3 points/,
    );
  });
});

describe("geometryToFractionalBbox", () => {
  it("converts normalized rect geometry to fractional bbox", () => {
    const bbox = geometryToFractionalBbox({
      type: "rect",
      x: 0.1,
      y: 0.2,
      width: 0.05,
      height: 0.1,
    });
    expect(bbox[0]).toBeCloseTo(0.1);
    expect(bbox[1]).toBeCloseTo(0.2);
    expect(bbox[2]).toBeCloseTo(0.15);
    expect(bbox[3]).toBeCloseTo(0.3);
  });

  it("derives bbox from polygon points", () => {
    const bbox = geometryToFractionalBbox({
      type: "polygon",
      points: [
        [0.1, 0.1],
        [0.5, 0.1],
        [0.5, 0.4],
      ],
    });
    expect(bbox).toEqual([0.1, 0.1, 0.5, 0.4]);
  });
});

describe("polygonPointsToFractional", () => {
  it("clamps each normalized point into 0–1", () => {
    const result = polygonPointsToFractional([
      [0.1, 0.2],
      [0.5, 0.5],
      [1.2, -0.1],
    ]);
    expect(result[0][0]).toBeCloseTo(0.1);
    expect(result[0][1]).toBeCloseTo(0.2);
    expect(result[1][0]).toBeCloseTo(0.5);
    expect(result[1][1]).toBeCloseTo(0.5);
    expect(result[2][0]).toBeCloseTo(1);
    expect(result[2][1]).toBeCloseTo(0);
  });
});

describe("validateGeometry", () => {
  it("returns null for a valid rect", () => {
    expect(
      validateGeometry({
        type: "rect",
        x: 0,
        y: 0,
        width: 0.1,
        height: 0.1,
      }),
    ).toBeNull();
  });

  it("rejects zero width", () => {
    expect(
      validateGeometry({
        type: "rect",
        x: 0,
        y: 0,
        width: 0,
        height: 0.1,
      }),
    ).toMatch(/positive width/);
  });

  it("rejects polygon_points with fewer than 3 points", () => {
    expect(
      validateGeometry(
        {
          type: "rect",
          x: 0,
          y: 0,
          width: 0.1,
          height: 0.1,
        },
        [
          [0, 0],
          [0.1, 0.1],
        ],
      ),
    ).toMatch(/at least 3 points/);
  });

  it("accepts polygon_points with exactly 3 points", () => {
    expect(
      validateGeometry(
        {
          type: "rect",
          x: 0,
          y: 0,
          width: 0.1,
          height: 0.1,
        },
        [
          [0, 0],
          [0.1, 0.1],
          [0.2, 0],
        ],
      ),
    ).toBeNull();
  });
});
