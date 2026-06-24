import { describe, expect, it } from "vitest";

import {
  includeOverlayWhenChangesOnly,
  overlayGeometryToDiffRegion,
  overlayRegionTone,
  toOverlayRegions,
} from "@/lib/drawing-overlays/inspection_overlay";

type OverlayWireRecord = Parameters<typeof toOverlayRegions>[0][number];

function makeOverlay(
  partial: Partial<OverlayWireRecord> & Pick<OverlayWireRecord, "id">
): OverlayWireRecord {
  return {
    master_drawing_id: 10,
    inspection_run_id: 5,
    diff_id: null,
    geometry: {
      page: 1,
      type: "rect",
      x: 0.1,
      y: 0.2,
      width: 0.3,
      height: 0.15,
      label: "Zone A",
    },
    status: "pass",
    meta: null,
    created_at: "2026-01-01T00:00:00Z",
    ...partial,
  };
}

describe("toOverlayRegions", () => {
  it("maps inspection overlays with rect geometry", () => {
    const regions = toOverlayRegions([makeOverlay({ id: 42 })]);

    expect(regions).toHaveLength(1);
    expect(regions[0]).toMatchObject({
      id: 42,
      kind: "inspection",
      sourceId: 5,
      label: "Zone A",
      severity: "low",
      bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.15 },
    });
    expect(regions[0].shape.shapeType).toBe("rect");
    expect(regions[0].reviewBadge).toBe("passed");
  });

  it("maps diff-sourced overlays and fail status to high severity", () => {
    const regions = toOverlayRegions([
      makeOverlay({
        id: 7,
        inspection_run_id: null,
        diff_id: 99,
        status: "fail",
        geometry: {
          page: 1,
          type: "rect",
          bbox: { x: 0.2, y: 0.3, width: 0.1, height: 0.2 },
        },
      }),
    ]);

    expect(regions[0]).toMatchObject({
      kind: "diff",
      sourceId: 99,
      severity: "high",
      reviewBadge: "failed",
    });
  });

  it("maps polygon geometry and computes bbox", () => {
    const regions = toOverlayRegions([
      makeOverlay({
        id: 8,
        geometry: {
          page: 1,
          type: "polygon",
          points: [
            { x: 0.1, y: 0.1 },
            { x: 0.4, y: 0.1 },
            { x: 0.25, y: 0.35 },
          ],
          label: "poly",
        },
      }),
    ]);

    expect(regions[0].shape.shapeType).toBe("polygon");
    expect(regions[0].bbox.x).toBeCloseTo(0.1);
    expect(regions[0].bbox.y).toBeCloseTo(0.1);
    expect(regions[0].bbox.width).toBeCloseTo(0.3);
    expect(regions[0].bbox.height).toBeCloseTo(0.25);
  });

  it("skips overlays with unparseable geometry", () => {
    const regions = toOverlayRegions([
      makeOverlay({ id: 1, geometry: {} as OverlayWireRecord["geometry"] }),
    ]);
    expect(regions).toEqual([]);
  });
});

describe("overlayGeometryToDiffRegion", () => {
  it("accepts legacy bbox-only geometry", () => {
    const shape = overlayGeometryToDiffRegion({
      bbox: { x: 0.2, y: 0.3, width: 0.1, height: 0.2 },
    });
    expect(shape?.bbox).toEqual({
      x: 0.2,
      y: 0.3,
      width: 0.1,
      height: 0.2,
    });
  });
});

describe("overlay region tone helpers", () => {
  it("uses neutral tone when inspection statuses are hidden", () => {
    const [region] = toOverlayRegions([makeOverlay({ id: 1, status: "fail" })]);
    expect(overlayRegionTone(region, false)).toBe("neutral");
  });

  it("maps severity to tone when review badge is absent", () => {
    const regions = toOverlayRegions([
      makeOverlay({
        id: 9,
        status: "unknown",
        geometry: {
          page: 1,
          type: "rect",
          x: 0,
          y: 0,
          width: 0.1,
          height: 0.1,
        },
      }),
    ]);
    regions[0].reviewBadge = undefined;
    regions[0].shape.reviewBadge = undefined;
    regions[0].severity = "high";
    expect(overlayRegionTone(regions[0], true)).toBe("failed");
  });

  it("filters out passed regions when showChangesOnly is true", () => {
    const [region] = toOverlayRegions([makeOverlay({ id: 1, status: "pass" })]);
    expect(includeOverlayWhenChangesOnly(region, true)).toBe(false);
  });
});
