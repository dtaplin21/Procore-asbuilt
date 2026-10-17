import { describe, expect, it } from "vitest";

import { overlayGeometryToDiffRegion } from "@/lib/drawing-overlays/inspection_overlay";
import {
  normalizedPointsToPixels,
  resolveOverlayRegion,
} from "@/lib/drawing-overlays/geometry";

describe("overlay line segment geometry", () => {
  it("resolveOverlayRegion polyline with 3 points becomes line segments", () => {
    const source = {
      shapeType: "polyline" as const,
      scopeKind: "utility_line",
      points: [
        { x: 0.41, y: 0.38 },
        { x: 0.43, y: 0.39 },
        { x: 0.45, y: 0.4 },
      ],
    };

    const resolved = resolveOverlayRegion(source);

    expect(resolved?.kind).toBe("line_segments");
    if (resolved?.kind !== "line_segments") {
      throw new Error("expected line_segments");
    }
    expect(resolved.segments).toHaveLength(2);
    expect(resolved.segments[0]).toEqual([
      source.points[0],
      source.points[1],
    ]);
  });

  it("normalizedPointsToPixels for polyline", () => {
    const pixels = normalizedPointsToPixels(
      [
        { x: 0.41, y: 0.38 },
        { x: 0.43, y: 0.39 },
        { x: 0.45, y: 0.4 },
      ],
      { width: 1000, height: 800 }
    );

    expect(pixels).toEqual([
      { x: 410, y: 304 },
      { x: 430, y: 312 },
      { x: 450, y: 320 },
    ]);
  });

  it("overlayGeometryToDiffRegion accepts API line_segments geometry", () => {
    const shape = overlayGeometryToDiffRegion({
      page: 1,
      type: "line_segments",
      segments: [
        [
          [0.41, 0.38],
          [0.43, 0.39],
        ],
        [
          [0.43, 0.39],
          [0.45, 0.4],
        ],
      ],
      scope_kind: "utility_line",
      label: "inspection_match",
    });

    expect(shape).toEqual({
      shapeType: "line_segments",
      segments: [
        [
          { x: 0.41, y: 0.38 },
          { x: 0.43, y: 0.39 },
        ],
        [
          { x: 0.43, y: 0.39 },
          { x: 0.45, y: 0.4 },
        ],
      ],
      page: 1,
      note: "inspection_match",
      scopeKind: "utility_line",
    });
  });

  it("legacy API polyline geometry maps to line segments", () => {
    const shape = overlayGeometryToDiffRegion({
      page: 1,
      type: "polyline",
      points: [
        [0.41, 0.38],
        [0.43, 0.39],
        [0.45, 0.4],
      ],
      scope_kind: "utility_line",
      label: "inspection_match",
    });

    expect(shape?.shapeType).toBe("line_segments");
    expect(shape?.segments).toHaveLength(2);
  });
});
