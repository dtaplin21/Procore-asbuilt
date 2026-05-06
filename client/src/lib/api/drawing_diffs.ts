import type { DrawingDiffResponse } from "@shared/schema";

import { requestJson } from "@/lib/api/http";

/**
 * POST run diff pipeline — maps camelCase params to backend `alignment_id` body.
 * Sends `Idempotency-Key` (required by the API).
 * Response is a list of diff rows (see backend `run_diffs_for_alignment`).
 */
export async function runDrawingDiff(params: {
  projectId: number;
  masterDrawingId: number;
  alignmentId: number;
}): Promise<DrawingDiffResponse[]> {
  const url = `/api/projects/${params.projectId}/drawings/${params.masterDrawingId}/diffs`;

  return requestJson<DrawingDiffResponse[]>(url, {
    method: "POST",
    headers: {
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({
      alignment_id: params.alignmentId,
    }),
  });
}
