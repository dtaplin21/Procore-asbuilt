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

export function pollWhileInspectionRunsActive(
  query: Query<InspectionRunListResponse, Error>,
): number | false {
  const items = query.state.data?.items ?? [];
  return hasActiveInspectionRun(items) ? 3000 : false;
}
