/**
 * client/src/tests/unit/region_tooltip.test.ts
 *
 * Per the file map: "All 12 status strings in hover" — this test
 * exercises every controlled-vocabulary inspection status to confirm
 * the tooltip always surfaces the exact vocab string, never a derived
 * pass/fail simplification.
 */

import { describe, it, expect } from "vitest";
import { buildRegionTooltipContent } from "@/lib/drawing-regions/region_tooltip";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";

const ALL_12_STATUSES = [
  "Open",
  "Closed",
  "Approved",
  "Approved As Noted",
  "Rejected",
  "Pending",
  "In Progress",
  "Scheduled",
  "Completed",
  "Passed",
  "Failed",
  "Deferred",
];

function makeEntry(
  overrides: Partial<RegionInspectionSummaryEntry> = {},
): RegionInspectionSummaryEntry {
  return {
    regionId: 1,
    masterDrawingId: 42,
    state: "inspected",
    label: "Storm Drain #44",
    bbox: [0.1, 0.1, 0.2, 0.2],
    locationTags: ["Storm Drain #44"],
    inspectionTypeTags: ["Underground Storm Drain"],
    latestOverlayId: 11,
    latestInspectionRunId: 128,
    inspectionStatusDisplay: "Approved As Noted",
    inspectionDate: "2026-03-15",
    procoreInspectionId: null,
    ...overrides,
  };
}

describe("buildRegionTooltipContent — inspected region", () => {
  it("matches the spec §4 example exactly", () => {
    const content = buildRegionTooltipContent(makeEntry(), "inspected");
    expect(content.locationLine).toBe("Storm Drain #44");
    expect(content.inspectionLine).toBe("Underground Storm Drain");
    expect(content.dateLine).toBe("Mar 15, 2026");
    expect(content.inspectionNumberLine).toBe("Run 128");
    expect(content.statusLine).toBe("Approved As Noted");
  });

  it.each(ALL_12_STATUSES)(
    "surfaces the exact vocab string '%s', not a derived label",
    (status) => {
      const content = buildRegionTooltipContent(
        makeEntry({ inspectionStatusDisplay: status }),
        "inspected",
      );
      expect(content.statusLine).toBe(status);
    },
  );

  it("includes the Procore id alongside the run id when synced", () => {
    const content = buildRegionTooltipContent(
      makeEntry({ procoreInspectionId: "PRO-456" }),
      "inspected",
    );
    expect(content.inspectionNumberLine).toBe("Run 128 (Procore PRO-456)");
  });

  it("omits the Procore id when the run isn't synced", () => {
    const content = buildRegionTooltipContent(
      makeEntry({ procoreInspectionId: null }),
      "inspected",
    );
    expect(content.inspectionNumberLine).toBe("Run 128");
  });

  it("omits the status line (does not show 'Unknown') when no status was extracted", () => {
    const content = buildRegionTooltipContent(
      makeEntry({ inspectionStatusDisplay: null }),
      "inspected",
    );
    expect(content.statusLine).toBeNull();
  });

  it("omits the date line when no inspection date was extracted", () => {
    const content = buildRegionTooltipContent(
      makeEntry({ inspectionDate: null }),
      "inspected",
    );
    expect(content.dateLine).toBeNull();
  });

  it("falls back to a generic region label when no location tag exists", () => {
    const content = buildRegionTooltipContent(
      makeEntry({ regionId: 7, label: "", locationTags: [] }),
      "inspected",
    );
    expect(content.locationLine).toBe("Region 7");
  });

  it("falls back to a generic inspection label when no type tag exists", () => {
    const content = buildRegionTooltipContent(
      makeEntry({ inspectionTypeTags: [] }),
      "inspected",
    );
    expect(content.inspectionLine).toBe("Inspection");
  });
});

describe("buildRegionTooltipContent — uninspected region (admin mode)", () => {
  it("matches the spec §4 admin-mode example", () => {
    const content = buildRegionTooltipContent(
      makeEntry({ locationTags: ["Storm Drain #53"], state: "hidden" }),
      "setup_faint",
    );
    expect(content.locationLine).toBe("Storm Drain #53");
    expect(content.inspectionLine).toBe("Not yet inspected");
    expect(content.dateLine).toBeNull();
    expect(content.inspectionNumberLine).toBeNull();
    expect(content.statusLine).toBeNull();
  });

  it("never shows status/date/number fields for an uninspected region, even if oddly present on the entry", () => {
    const content = buildRegionTooltipContent(
      makeEntry({
        state: "hidden",
        inspectionStatusDisplay: "Approved",
        inspectionDate: "2026-01-01",
        latestInspectionRunId: 999,
      }),
      "setup_faint",
    );
    expect(content.statusLine).toBeNull();
    expect(content.dateLine).toBeNull();
    expect(content.inspectionNumberLine).toBeNull();
  });
});
