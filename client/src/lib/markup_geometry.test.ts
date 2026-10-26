import { describe, expect, it } from "vitest";
import { cloudPath, distToSegment, hitTest, outline, toFraction, typeColor } from "./markup_geometry";
import type { DrawingMarkup } from "../types/drawing_markup";

const mk = (id: number, kind: DrawingMarkup["kind"], points: [number, number][], inspectionType: string | null = null): DrawingMarkup => ({
  id, drawingId: 1, page: 1, kind, points, label: null, inspectionType, status: null, color: null, createdBy: "t", createdAt: "", updatedAt: "",
});

describe("geometry", () => {
  it("maps pointer to fractions, y down from the top, and clamps", () => {
    const rect = { left: 100, top: 50, width: 200, height: 100 };
    expect(toFraction(rect, 200, 100)).toEqual([0.5, 0.5]);
    expect(toFraction(rect, 0, 1000)).toEqual([0, 1]);
    expect(toFraction({ ...rect, width: 0 }, 5, 5)).toEqual([0, 0]);
  });
  it("measures distance to a segment, including past the ends", () => {
    expect(distToSegment([0.5, 0.2], [0, 0], [1, 0])).toBeCloseTo(0.2);
    expect(distToSegment([2, 0], [0, 0], [1, 0])).toBeCloseTo(1);
    expect(distToSegment([0.3, 0.4], [0.1, 0.1], [0.1, 0.1])).toBeCloseTo(Math.hypot(0.2, 0.3));
  });
  it("closes rectangles and clouds", () => {
    expect(outline(mk(1, "rect", [[0.1, 0.1], [0.3, 0.2]]))).toHaveLength(5);
    const c = outline(mk(1, "cloud", [[0, 0], [1, 0], [1, 1]]));
    expect(c[c.length - 1]).toEqual(c[0]);
  });
  it("hits the nearest markup, the later one on a tie, and nothing outside tolerance", () => {
    const a = mk(1, "polyline", [[0.1, 0.5], [0.9, 0.5]]);
    const b = mk(2, "polyline", [[0.1, 0.5], [0.9, 0.5]]);
    expect(hitTest([a, b], [0.5, 0.505])?.id).toBe(2);
    expect(hitTest([a, b], [0.5, 0.7])).toBeNull();
    const box = mk(3, "rect", [[0.2, 0.2], [0.6, 0.6]]);
    expect(hitTest([box], [0.4, 0.4])?.id).toBe(3);
    expect(hitTest([mk(4, "text", [[0.5, 0.5]])], [0.505, 0.5])?.id).toBe(4);
  });
  it("draws a cloud as arcs that end back at the start", () => {
    const d = cloudPath([[0.1, 0.1], [0.4, 0.1], [0.4, 0.3]]);
    expect(d.startsWith("M 0.1 0.1")).toBe(true);
    expect((d.match(/ A /g) ?? []).length).toBeGreaterThan(10);
    expect(d.endsWith("Z")).toBe(true);
    expect(cloudPath([[0, 0], [1, 1]])).toBe("");
  });
  it("gives a type the same colour every time", () => {
    expect(typeColor("Final")).toBe(typeColor("Final"));
    expect(typeColor(null)).toBe("#555555");
  });
});
