import { useQuery } from "@tanstack/react-query";

import {
  fetchInspectionRunProgress,
  inspectionRunProgressUrl,
  type InspectionRunProgress,
} from "@/lib/api/inspection_run_progress";
import { isActiveInspectionRun } from "@/lib/inspection-runs/active_run";
import type { InspectionRun } from "@shared/schema";

export function useInspectionRunProgress(
  projectId: number | null,
  run: InspectionRun | null,
) {
  const runId = run?.id ?? null;
  const enabled =
    projectId != null &&
    runId != null &&
    run != null &&
    isActiveInspectionRun({ status: run.status, evidence_id: run.evidence_id });

  return useQuery<InspectionRunProgress>({
    queryKey: [projectId != null && runId != null ? inspectionRunProgressUrl(projectId, runId) : ""],
    queryFn: () => fetchInspectionRunProgress(projectId as number, runId as number),
    enabled,
    refetchInterval: enabled ? 2000 : false,
  });
}
