import type { JobResponse } from "@shared/schema";

const DRAWING_COMPARE = "drawing_compare";

/** In-flight worker job for POST compare that runs out-of-band after renders. */
export function findActiveDrawingCompareJob(
  jobs: JobResponse[] | undefined,
  masterDrawingId: number,
  subDrawingId: number
): JobResponse | null {
  if (!jobs?.length) return null;
  for (const job of jobs) {
    if (job.job_type !== DRAWING_COMPARE) continue;
    const st = (job.status ?? "").toLowerCase();
    if (st !== "pending" && st !== "processing") continue;
    const data = job.input_data;
    if (!data || typeof data !== "object") continue;
    const row = data as Record<string, unknown>;
    const m = Number(row.master_drawing_id);
    const s = Number(row.sub_drawing_id);
    if (m === masterDrawingId && s === subDrawingId) {
      return job;
    }
  }
  return null;
}
