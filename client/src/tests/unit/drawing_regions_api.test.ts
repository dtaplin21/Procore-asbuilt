import { describe, expect, it } from "vitest";

import {
  buildRegionInspectionSummaryUrl,
  drawingRegionsQueryKey,
  regionInspectionSummaryQueryKey,
} from "@/lib/api/drawing_regions";

describe("drawing_regions API helpers", () => {
  it("builds project-scoped region URLs", () => {
    expect(buildRegionInspectionSummaryUrl(3, 42)).toBe(
      "/api/projects/3/drawings/42/region-inspection-summary",
    );
  });

  it("builds stable react-query keys", () => {
    expect(drawingRegionsQueryKey(3, 42)).toEqual(["drawing-regions", "3", "42"]);
    expect(regionInspectionSummaryQueryKey("3", "42")).toEqual([
      "region-inspection-summary",
      "3",
      "42",
    ]);
  });
});
