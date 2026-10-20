import type { Query } from "@tanstack/react-query";
import type { InspectionRun, InspectionRunListResponse } from "@shared/schema";

type RunActivityFields = Pick<InspectionRun, "status" | "evidence_id">;

/**
 * Runs that should block new evidence uploads.
 *
 * Deferred upload placeholders (`queued` with no evidence yet) are excluded so
 * a failed upload after createRun does not permanently disable the control.
 */
export function isActiveInspectionRun(run: RunActivityFields): boolean {
  const status = run.status.toLowerCase();
  if (status === "processing") {
    return true;
  }
  if (status === "queued" && run.evidence_id != null) {
    return true;
  }
  return false;
}

export function hasActiveInspectionRun(runs: RunActivityFields[]): boolean {
  return runs.some(isActiveInspectionRun);
}

/** True while the worker may be updating coarse progress for this run. */
export function shouldPollInspectionRunProgress(
  run: RunActivityFields & { id?: number },
  pipelinePendingRunId?: number | null,
): boolean {
  if (pipelinePendingRunId != null && run.id === pipelinePendingRunId) {
    return true;
  }
  return isActiveInspectionRun(run);
}

/** Prefer selected active run, otherwise any run that is inspecting or reprocessing. */
export function pickInspectionProgressRun<
  T extends RunActivityFields & { id: number },
>(
  runs: T[],
  options?: {
    selectedRunId?: number | null;
    pipelinePendingRunId?: number | null;
  },
): T | null {
  const { selectedRunId, pipelinePendingRunId } = options ?? {};
  const isCandidate = (run: T) =>
    shouldPollInspectionRunProgress(run, pipelinePendingRunId);

  if (selectedRunId != null) {
    const selected = runs.find((r) => r.id === selectedRunId);
    if (selected && isCandidate(selected)) {
      return selected;
    }
  }
  return runs.find(isCandidate) ?? null;
}

export function pollWhileInspectionRunsActive(
  query: Query<InspectionRunListResponse, Error>,
): number | false {
  const items = query.state.data?.items ?? [];
  return hasActiveInspectionRun(items) ? 3000 : false;
}
