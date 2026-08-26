import type { QueryClient } from "@tanstack/react-query";
import type { DrawingResponse } from "@shared/schema";
import type { ProjectDrawingsResponse } from "@/types/drawing_workspace";

import { readApiError, requestJson, resolveFetchUrl } from "@/lib/api/http";
import {
  coerceDrawingIdForApi,
  coerceProjectIdForApi,
} from "@/lib/api/route_ids";

export { coerceDrawingIdForApi, coerceProjectIdForApi } from "@/lib/api/route_ids";

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

/** React Query key for GET /api/projects/{id}/drawings (shared list queries). */
export function projectDrawingsQueryKey(
  projectId: number
): readonly ["project-drawings", number] {
  return ["project-drawings", projectId];
}

/** Invalidate cached GET /api/projects/{id}/drawings for all mounted list consumers. */
export function invalidateProjectDrawingsQueries(
  queryClient: QueryClient,
  projectId: number
): Promise<void> {
  return queryClient.invalidateQueries({
    queryKey: projectDrawingsQueryKey(projectId),
  });
}

/** Refresh drawing lists and dashboard counts after a drawing is deleted. */
export function invalidateProjectDrawingListQueries(
  queryClient: QueryClient,
  projectId: number
): Promise<void> {
  return Promise.all([
    invalidateProjectDrawingsQueries(queryClient, projectId),
    queryClient.invalidateQueries({
      queryKey: ["drawing-manage-dashboard-summary", projectId],
    }),
    queryClient.invalidateQueries({
      queryKey: ["drawing-picker-dashboard-summary", projectId],
    }),
    queryClient.invalidateQueries({
      queryKey: ["project-dashboard-summary", projectId],
    }),
  ]).then(() => undefined);
}

export async function fetchProjectDrawings(
  projectId: number | string
): Promise<ProjectDrawingsResponse> {
  const pid = coerceProjectIdForApi(projectId);
  return requestJson<ProjectDrawingsResponse>(`/api/projects/${pid}/drawings`);
}

/** Rendition-aware master drawing payload for DrawingViewer consumers. */
export interface MasterDrawing {
  id: string;
  projectId: string;
  name: string;
  /** URL of the rendered drawing image to display in DrawingViewer. */
  imageUrl: string;
}

export interface ProjectDrawingSummary {
  id: string;
  name: string;
}

type WorkspaceDrawingWire = {
  id: number;
  name: string;
  fileUrl: string;
  projectId?: number | null;
};

/**
 * GET /api/projects/{project_id}/drawings/{drawing_id}
 * Returns the workspace drawing payload mapped to {@link MasterDrawing}.
 */
export async function fetchMasterDrawing(
  projectId: number | string,
  drawingId: number | string,
  page?: number,
): Promise<MasterDrawing> {
  const pid = coerceProjectIdForApi(projectId);
  const did = coerceDrawingIdForApi(drawingId);
  let path = `/api/projects/${pid}/drawings/${did}`;
  if (page != null && page >= 1) {
    path += `?page=${encodeURIComponent(String(page))}`;
  }
  const data = await requestJson<WorkspaceDrawingWire>(path);
  return {
    id: String(data.id),
    projectId: String(data.projectId ?? pid),
    name: data.name,
    imageUrl: data.fileUrl,
  };
}

/** CamelCase summaries for master-drawing pickers (Inspections upload, etc.). */
export async function fetchProjectDrawingSummaries(
  projectId: number | string,
): Promise<ProjectDrawingSummary[]> {
  const response = await fetchProjectDrawings(projectId);
  return response.drawings.map((drawing) => ({
    id: String(drawing.id),
    name: drawing.name,
  }));
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
  projectId: number,
  file: File
): Promise<DrawingResponse> {
  if (!(file instanceof File)) {
    throw new TypeError("uploadProjectDrawing requires a File instance");
  }

  const pid = coerceProjectIdForApi(projectId);
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(resolveFetchUrl(`/api/projects/${pid}/drawings`), {
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
