import { describe, expect, it } from "vitest";

import { buildRegionTooltipContent } from "@/lib/drawing-regions/region_tooltip";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";

function entry(
  overrides: Partial<RegionInspectionSummaryEntry> & Pick<RegionInspectionSummaryEntry, "regionId">,
): RegionInspectionSummaryEntry {
  return {
    masterDrawingId: 1,
    state: "hidden",
    label: "Zone A",
    bbox: [0, 0, 0.1, 0.1],
    locationTags: [],
    inspectionTypeTags: [],
    ...overrides,
  };
}

describe("region_tooltip", () => {
  it("formats faint uninspected regions with minimal lines", () => {
    const content = buildRegionTooltipContent(
      entry({
        regionId: 53,
        locationTags: ["Storm Drain #53"],
      }),
      "setup_faint",
    );

    expect(content).toEqual({
      locationLine: "Storm Drain #53",
      inspectionLine: "Not yet inspected",
      dateLine: null,
      inspectionNumberLine: null,
      statusLine: null,
    });
  });

  it("falls back to label then region id for location", () => {
    expect(
      buildRegionTooltipContent(entry({ regionId: 7, label: "Utility MR" }), "setup_faint")
        .locationLine,
    ).toBe("Utility MR");

    expect(
      buildRegionTooltipContent(
        entry({ regionId: 7, label: "", locationTags: [] }),
        "setup_faint",
      ).locationLine,
    ).toBe("Region 7");
  });

  it("formats inspected regions with full vocab status", () => {
    const content = buildRegionTooltipContent(
      entry({
        regionId: 44,
        state: "inspected",
        locationTags: ["Storm Drain #44"],
        inspectionTypeTags: ["Underground Storm Drain"],
        inspectionDate: "2026-03-15",
        latestInspectionRunId: 128,
        procoreInspectionId: "PC-991",
        inspectionStatusDisplay: "Approved As Noted",
      }),
      "inspected",
    );

    expect(content.locationLine).toBe("Storm Drain #44");
    expect(content.inspectionLine).toBe("Underground Storm Drain");
    expect(content.dateLine).toBe("Mar 15, 2026");
    expect(content.inspectionNumberLine).toBe("Run 128 (Procore PC-991)");
    expect(content.statusLine).toBe("Approved As Noted");
  });

  it("omits status line when inspectionStatusDisplay is absent", () => {
    const content = buildRegionTooltipContent(
      entry({
        regionId: 1,
        state: "inspected",
        locationTags: ["Roof"],
        inspectionTypeTags: ["Final"],
        latestInspectionRunId: 5,
      }),
      "inspected",
    );

    expect(content.statusLine).toBeNull();
  });

  it("uses inspectionType when tags are empty", () => {
    const content = buildRegionTooltipContent(
      entry({
        regionId: 2,
        state: "inspected",
        locationTags: ["Yard"],
        inspectionType: "fire_protection",
      }),
      "inspected",
    );

    expect(content.inspectionLine).toBe("fire_protection");
  });
});
