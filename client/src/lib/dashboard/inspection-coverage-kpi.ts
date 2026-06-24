import type { ProjectInspectionCoverageMetric } from "@shared/schema";

/** Dashboard KPI display for master inspection coverage (from `inspection_runs`). */
export function formatInspectionCoverageKpi(
  coverage: ProjectInspectionCoverageMetric | null | undefined
): { value: string; subtitle: string | undefined } {
  const inspected = coverage?.inspectedCount ?? 0;
  const total = coverage?.totalMastersCount ?? 0;
  return {
    value: `${inspected} / ${total}`,
    subtitle: coverage?.label,
  };
}
