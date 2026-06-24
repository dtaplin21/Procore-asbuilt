import { describe, expect, it } from "vitest";

import { formatInspectionCoverageKpi } from "@/lib/dashboard/inspection-coverage-kpi";

describe("formatInspectionCoverageKpi", () => {
  it("formats inspected / total masters from inspectionCoverage KPI", () => {
    expect(
      formatInspectionCoverageKpi({
        inspectedCount: 1,
        totalMastersCount: 1,
        label: "1 of 1 master drawing(s) have been inspected for this project.",
      })
    ).toEqual({
      value: "1 / 1",
      subtitle: "1 of 1 master drawing(s) have been inspected for this project.",
    });
  });

  it("defaults to zero coverage when KPI is missing", () => {
    expect(formatInspectionCoverageKpi(null)).toEqual({
      value: "0 / 0",
      subtitle: undefined,
    });
  });
});
