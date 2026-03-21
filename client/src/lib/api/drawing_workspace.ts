import type {
  DrawingAlignmentsResponse,
  DrawingDiffsResponse,
  DrawingWorkspaceDrawing,
} from "@/types/drawing_workspace";

type ApiErrorPayload = {
  detail?: string;
  message?: string;
};

async function parseJsonSafe(response: Response) {
  const contentType = response.headers.get("content-type");

  if (contentType?.includes("application/json")) {
    return response.json();
  }

  return null;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  const data = (await parseJsonSafe(response)) as ApiErrorPayload | T | null;

  if (!response.ok) {
    const message =
      (data as ApiErrorPayload | null)?.detail ||
      (data as ApiErrorPayload | null)?.message ||
      `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  return data as T;
}

export async function fetchMasterDrawing(
  projectId: number,
  drawingId: number,
  page?: number
): Promise<DrawingWorkspaceDrawing> {
  const url = new URL(
    `/api/projects/${projectId}/drawings/${drawingId}`,
    window.location.origin
  );
  if (page != null && page >= 1) {
    url.searchParams.set("page", String(page));
  }
  return requestJson<DrawingWorkspaceDrawing>(url.pathname + url.search);
}

export async function fetchMasterDrawingAlignments(
  projectId: number,
  drawingId: number
): Promise<DrawingAlignmentsResponse> {
  return requestJson<DrawingAlignmentsResponse>(
    `/api/projects/${projectId}/drawings/${drawingId}/alignments`
  );
}

export async function fetchAlignmentDiffs(
  projectId: number,
  drawingId: number,
  alignmentId: number
): Promise<DrawingDiffsResponse> {
  const url = new URL(
    `/api/projects/${projectId}/drawings/${drawingId}/diffs`,
    window.location.origin
  );

  url.searchParams.set("alignment_id", String(alignmentId));

  return requestJson<DrawingDiffsResponse>(url.pathname + url.search);
}
