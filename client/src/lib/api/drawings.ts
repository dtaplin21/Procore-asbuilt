import type { DrawingResponse } from "@shared/schema";
import type { ProjectDrawingsResponse } from "@/types/drawing_workspace";

import { readApiError, requestJson } from "@/lib/api/http";

export async function fetchProjectDrawings(
  projectId: number
): Promise<ProjectDrawingsResponse> {
  return requestJson<ProjectDrawingsResponse>(`/api/projects/${projectId}/drawings`);
}

/**
 * POST /api/projects/{project_id}/drawings — multipart upload.
 * Form field name `file` matches FastAPI `File(...)`.
 * Only `Idempotency-Key` in headers — do not set `Content-Type` (browser sets multipart boundary).
 */
export async function uploadProjectDrawing(
  projectId: number,
  file: File
): Promise<DrawingResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`/api/projects/${projectId}/drawings`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: formData,
  });

  if (!response.ok) {
    await readApiError(response);
  }

  return (await response.json()) as DrawingResponse;
}
