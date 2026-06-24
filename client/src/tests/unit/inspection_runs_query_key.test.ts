import { describe, expect, it } from "vitest";

import {
  buildInspectionRunsUrl,
  inspectionRunsQueryKey,
} from "@/hooks/use-inspection-runs";

describe("inspection runs query keys", () => {
  it("uses the same cache key for sidebar and writeback (no status filter)", () => {
    const sidebarKey = inspectionRunsQueryKey(2, { masterDrawingId: 10 });
    const writebackKey = inspectionRunsQueryKey(2, { masterDrawingId: 10 });

    expect(sidebarKey).toEqual(writebackKey);
    expect(buildInspectionRunsUrl(2, { masterDrawingId: 10 })).toBe(
      "/api/projects/2/inspections/runs?master_drawing_id=10"
    );
  });

  it("status filter produces a distinct cache key", () => {
    const unfiltered = inspectionRunsQueryKey(2, { masterDrawingId: 10 });
    const filtered = inspectionRunsQueryKey(2, {
      masterDrawingId: 10,
      status: "complete",
    });

    expect(unfiltered).not.toEqual(filtered);
  });
});
