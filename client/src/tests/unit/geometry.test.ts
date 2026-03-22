import { describe, expect, it } from "vitest";
import {
  normalizedPointsToPixels,
  normalizedRectToPixels,
  polygonPointsToSvgString,
  resolveOverlayRegion,
} from "@/lib/drawing-overlays/geometry";

describe("drawing overlay geometry", () => {
  it("converts normalized rect to pixel rect", () => {
    const result = normalizedRectToPixels(
      { x: 0.1, y: 0.2, width: 0.5, height: 0.25 },
      { width: 1000, height: 800 }
    );

    expect(result).toEqual({
      x: 100,
      y: 160,
      width: 500,
      height: 200,
    });
  });

  it("converts normalized polygon points to pixels", () => {
    const result = normalizedPointsToPixels(
      [
        { x: 0.1, y: 0.2 },
        { x: 0.5, y: 0.75 },
      ],
      { width: 1000, height: 800 }
    );

    expect(result).toEqual([
      { x: 100, y: 160 },
      { x: 500, y: 600 },
    ]);
  });

  it("builds svg polygon string", () => {
    const result = polygonPointsToSvgString([
      { x: 10, y: 20 },
      { x: 30, y: 40 },
      { x: 50, y: 60 },
    ]);

    expect(result).toBe("10,20 30,40 50,60");
  });

  it("resolves bbox fallback as rect", () => {
    const resolved = resolveOverlayRegion({
      bbox: {
        x: 0.2,
        y: 0.3,
        width: 0.1,
        height: 0.2,
      },
    });

    expect(resolved).toEqual({
      kind: "rect",
      rect: {
        x: 0.2,
        y: 0.3,
        width: 0.1,
        height: 0.2,
      },
      source: {
        bbox: {
          x: 0.2,
          y: 0.3,
          width: 0.1,
          height: 0.2,
        },
      },
    });
  });

  it("resolves polygon region", () => {
    const resolved = resolveOverlayRegion({
      shapeType: "polygon",
      points: [
        { x: 0.1, y: 0.1 },
        { x: 0.2, y: 0.1 },
        { x: 0.15, y: 0.2 },
      ],
    });

    expect(resolved?.kind).toBe("polygon");
  });
});
