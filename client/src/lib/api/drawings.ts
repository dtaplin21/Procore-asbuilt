import type { DrawingResponse } from "@shared/schema";
import type { ProjectDrawingsResponse } from "@/types/drawing_workspace";

import { readApiError, requestJson } from "@/lib/api/http";

/** Positive integer id for URLs and comparisons — works for project id or drawing id route params. */
function coercePositiveIntId(id: number | string): number {
  const n = typeof id === "number" ? id : Number(id);
  if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) {
    throw new TypeError("Invalid id");
  }
  return n;
}

/**
 * Route params often arrive as strings; the upload URL must use a finite numeric id.
 * Call this so `uploadProjectDrawing` never sends `NaN` or `"12"` in the path by accident.
 */
function coerceProjectIdForApi(projectId: number | string): number {
  try {
    return coercePositiveIntId(projectId);
  } catch {
    throw new TypeError("Invalid project id");
  }
}

/**
 * Same rules as project id: master/sub drawing ids must be numeric and match `drawing.id` comparisons.
 */
export function coerceDrawingIdForApi(drawingId: number | string): number {
  try {
    return coercePositiveIntId(drawingId);
  } catch {
    throw new TypeError("Invalid drawing id");
  }
}

/** Minimal shape check so callers never treat `{ drawing: {...} }` as a drawing row. */
function assertDrawingResponseShape(data: unknown): asserts data is DrawingResponse {
  if (!data || typeof data !== "object") {
    throw new Error("Drawing upload response is not an object");
  }
  const row = data as Record<string, unknown>;
  if (typeof row.id !== "number" || typeof row.name !== "string") {
    throw new Error(
      "Drawing upload response must be a flat DrawingResponse (check API helper unwrap)"
    );
  }
}

/** Normalize upload JSON: flat `DrawingResponse`, or unwrap `{ drawing: DrawingResponse }`. Always returns a plain row. */
function parseDrawingResponsePayload(json: unknown): DrawingResponse {
  let payload: unknown = json;
  if (
    payload &&
    typeof payload === "object" &&
    "drawing" in payload &&
    (payload as { drawing: unknown }).drawing &&
    typeof (payload as { drawing: unknown }).drawing === "object"
  ) {
    payload = (payload as { drawing: unknown }).drawing;
  }
  assertDrawingResponseShape(payload);
  return payload;
}

export async function fetchProjectDrawings(
  projectId: number | string
): Promise<ProjectDrawingsResponse> {
  const pid = coerceProjectIdForApi(projectId);
  return requestJson<ProjectDrawingsResponse>(`/api/projects/${pid}/drawings`);
}

/**
 * POST /api/projects/{project_id}/drawings — multipart upload.
 * Form field name `file` matches FastAPI `File(...)`.
 * Only `Idempotency-Key` in headers — do not set `Content-Type` (browser sets multipart boundary).
 *
 * Always resolves to a **plain** {@link DrawingResponse} (never `{ drawing: ... }` at the type level).
 * Imports: use `@shared/schema` and `@/lib/api/drawings` (see root `tsconfig.json` paths).
 */
export async function uploadProjectDrawing(
  projectId: number | string,
  file: File
): Promise<DrawingResponse> {
  if (!(file instanceof File)) {
    throw new TypeError("uploadProjectDrawing requires a File instance");
  }

  const pid = coerceProjectIdForApi(projectId);
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`/api/projects/${pid}/drawings`, {
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

  return parseDrawingResponsePayload(await response.json());
}
