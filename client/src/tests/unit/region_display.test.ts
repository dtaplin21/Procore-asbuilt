import { describe, expect, it } from "vitest";

import {
  resolveRegionViewerState,
  resolveRenderableRegions,
  styleForViewerState,
} from "@/lib/drawing-regions/region_display";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";

function entry(
  overrides: Partial<RegionInspectionSummaryEntry> & Pick<RegionInspectionSummaryEntry, "regionId" | "state">,
): RegionInspectionSummaryEntry {
  return {
    masterDrawingId: 1,
    label: "Zone",
    bbox: [0, 0, 0.1, 0.1],
    locationTags: [],
    inspectionTypeTags: [],
    ...overrides,
  };
}

describe("region_display", () => {
  it("hides uninspected regions when the admin toggle is off", () => {
    const hidden = entry({ regionId: 1, state: "hidden" });
    expect(resolveRegionViewerState(hidden, false)).toBe("hidden");
    expect(styleForViewerState("hidden")).toBeNull();
  });

  it("shows faint outlines for uninspected regions when toggle is on", () => {
    const hidden = entry({ regionId: 1, state: "hidden" });
    expect(resolveRegionViewerState(hidden, true)).toBe("setup_faint");
    expect(styleForViewerState("setup_faint")).toMatchObject({
      strokeDasharray: "4,3",
      fillOpacity: 0,
    });
  });

  it("always renders inspected regions as bold regardless of toggle", () => {
    const inspected = entry({ regionId: 2, state: "inspected" });
    expect(resolveRegionViewerState(inspected, false)).toBe("inspected");
    expect(resolveRegionViewerState(inspected, true)).toBe("inspected");
    expect(styleForViewerState("inspected")).toMatchObject({
      strokeWidth: 3.5,
      strokeDasharray: undefined,
    });
  });

  it("sorts inspected regions after faint ones for paint order", () => {
    const result = resolveRenderableRegions(
      [
        entry({ regionId: 1, state: "inspected" }),
        entry({ regionId: 2, state: "hidden" }),
      ],
      true,
    );

    expect(result.map((r) => r.state)).toEqual(["setup_faint", "inspected"]);
    expect(result.map((r) => r.entry.regionId)).toEqual([2, 1]);
  });

  it("omits hidden regions when toggle is off", () => {
    const result = resolveRenderableRegions(
      [
        entry({ regionId: 1, state: "hidden" }),
        entry({ regionId: 2, state: "inspected" }),
      ],
      false,
    );

    expect(result).toHaveLength(1);
    expect(result[0]?.state).toBe("inspected");
  });
});
