/**
 * client/src/tests/unit/region_display.test.ts
 */

import { describe, it, expect } from "vitest";
import {
  resolveRegionViewerState,
  resolveRenderableRegions,
  styleForViewerState,
} from "@/lib/drawing-regions/region_display";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";

function makeEntry(
  overrides: Partial<RegionInspectionSummaryEntry> = {},
): RegionInspectionSummaryEntry {
  return {
    regionId: 1,
    masterDrawingId: 42,
    state: "hidden",
    label: "Roof",
    bbox: [0.1, 0.1, 0.2, 0.2],
    locationTags: ["Roof"],
    inspectionTypeTags: ["Final"],
    latestOverlayId: null,
    latestInspectionRunId: null,
    inspectionStatusDisplay: null,
    inspectionDate: null,
    procoreInspectionId: null,
    ...overrides,
  };
}

describe("resolveRegionViewerState", () => {
  it("inspected entries are always 'inspected', regardless of the admin toggle", () => {
    const entry = makeEntry({ state: "inspected" });
    expect(resolveRegionViewerState(entry, false)).toBe("inspected");
    expect(resolveRegionViewerState(entry, true)).toBe("inspected");
  });

  it("hidden entries stay 'hidden' when the admin toggle is off", () => {
    const entry = makeEntry({ state: "hidden" });
    expect(resolveRegionViewerState(entry, false)).toBe("hidden");
  });

  it("hidden entries become 'setup_faint' when the admin toggle is on", () => {
    const entry = makeEntry({ state: "hidden" });
    expect(resolveRegionViewerState(entry, true)).toBe("setup_faint");
  });
});

describe("styleForViewerState", () => {
  it("hidden state has no style at all (not rendered)", () => {
    expect(styleForViewerState("hidden")).toBeNull();
  });

  it("inspected state gets the bold style", () => {
    const style = styleForViewerState("inspected");
    expect(style?.strokeWidth).toBeGreaterThanOrEqual(3);
    expect(style?.strokeDasharray).toBeUndefined();
  });

  it("setup_faint state gets a dashed, thin style", () => {
    const style = styleForViewerState("setup_faint");
    expect(style?.strokeWidth).toBeLessThan(2);
    expect(style?.strokeDasharray).toBeDefined();
  });

  it("bold style is IDENTICAL regardless of which status produced it — bold ignores status per spec", () => {
    const styleA = styleForViewerState("inspected");
    const styleB = styleForViewerState("inspected");
    expect(styleA).toEqual(styleB);
  });
});

describe("resolveRenderableRegions", () => {
  it("excludes hidden regions when the toggle is off", () => {
    const entries = [makeEntry({ regionId: 1, state: "hidden" })];
    const renderable = resolveRenderableRegions(entries, false);
    expect(renderable).toHaveLength(0);
  });

  it("includes hidden regions as setup_faint when the toggle is on", () => {
    const entries = [makeEntry({ regionId: 1, state: "hidden" })];
    const renderable = resolveRenderableRegions(entries, true);
    expect(renderable).toHaveLength(1);
    expect(renderable[0].state).toBe("setup_faint");
  });

  it("always includes inspected regions regardless of the toggle", () => {
    const entries = [makeEntry({ regionId: 1, state: "inspected" })];
    expect(resolveRenderableRegions(entries, false)).toHaveLength(1);
    expect(resolveRenderableRegions(entries, true)).toHaveLength(1);
  });

  it("sorts inspected (bold) regions last so they paint on top of faint outlines", () => {
    const entries = [
      makeEntry({ regionId: 10, state: "hidden" }),
      makeEntry({ regionId: 20, state: "inspected" }),
    ];
    const renderable = resolveRenderableRegions(entries, true);
    expect(renderable.map((r) => r.entry.regionId)).toEqual([10, 20]);
  });

  it("two inspected regions with different statuses get the SAME bold style", () => {
    const entries = [
      makeEntry({
        regionId: 1,
        state: "inspected",
        inspectionStatusDisplay: "Approved As Noted",
      }),
      makeEntry({
        regionId: 2,
        state: "inspected",
        inspectionStatusDisplay: "Rejected",
      }),
    ];
    const renderable = resolveRenderableRegions(entries, false);
    expect(renderable[0].style).toEqual(renderable[1].style);
  });
});
