import {
  DrawingAlignmentsResponse,
  DrawingDiffsResponse,
  DrawingResponse,
} from "@/types/drawing_workspace";
import { ApiError } from "@/lib/errors";

async function parseJsonSafe(response: Response) {
  const contentType = response.headers.get("content-type");

  if (contentType?.includes("application/json")) {
    return response.json();
  }

  return null;
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  const data = await parseJsonSafe(response);

  if (!response.ok) {
    const message =
      data?.detail ||
      data?.message ||
      `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status);
  }

  return data as T;
}

export async function fetchDrawing(
  projectId: number,
  drawingId: number
): Promise<DrawingResponse> {
  return requestJson<DrawingResponse>(
    `/api/projects/${projectId}/drawings/${drawingId}`
  );
}

export async function fetchAlignments(
  projectId: number,
  masterDrawingId: number
): Promise<DrawingAlignmentsResponse> {
  return requestJson<DrawingAlignmentsResponse>(
    `/api/projects/${projectId}/drawings/${masterDrawingId}/alignments`
  );
}

export async function fetchDiffs(
  projectId: number,
  masterDrawingId: number,
  alignmentId: number
): Promise<DrawingDiffsResponse> {
  const url = new URL(
    `/api/projects/${projectId}/drawings/${masterDrawingId}/diffs`,
    window.location.origin
  );

  url.searchParams.set("alignment_id", String(alignmentId));

  return requestJson<DrawingDiffsResponse>(url.pathname + url.search);
}
