import type { QueryClient } from "@tanstack/react-query";
import type { EvidenceListResponse, EvidenceRecordResponse } from "@shared/schema";

import { readApiError, requestJson, resolveFetchUrl } from "@/lib/api/http";

export type EvidenceUploadType = "spec" | "inspection_doc";

export type UploadEvidenceOptions = {
  type?: EvidenceUploadType;
  title?: string;
  trade?: string;
  specSection?: string;
  meta?: Record<string, unknown>;
};

function coerceProjectIdForApi(projectId: number | string): number {
  const n = typeof projectId === "number" ? projectId : Number(projectId);
  if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) {
    throw new TypeError("Invalid project id");
  }
  return n;
}

/** React Query key for GET /api/projects/{id}/evidence. */
export function projectEvidenceQueryKey(
  projectId: number
): readonly ["/api/projects", number, "evidence"] {
  return ["/api/projects", projectId, "evidence"];
}

export function invalidateProjectEvidenceQueries(
  queryClient: QueryClient,
  projectId: number
): Promise<void> {
  return queryClient.invalidateQueries({
    queryKey: projectEvidenceQueryKey(projectId),
  });
}

export async function fetchProjectEvidence(
  projectId: number | string,
  filters?: { type?: EvidenceUploadType; limit?: number; offset?: number }
): Promise<EvidenceListResponse> {
  const pid = coerceProjectIdForApi(projectId);
  const params = new URLSearchParams();
  if (filters?.type) params.set("type", filters.type);
  if (filters?.limit != null) params.set("limit", String(filters.limit));
  if (filters?.offset != null) params.set("offset", String(filters.offset));
  const query = params.toString();
  return requestJson<EvidenceListResponse>(
    `/api/projects/${pid}/evidence${query ? `?${query}` : ""}`
  );
}

/**
 * POST /api/projects/{project_id}/evidence — multipart upload.
 * Form fields match FastAPI `upload_evidence` in backend/api/routes/evidence.py.
 */
export async function uploadEvidence(
  projectId: number,
  file: File,
  options: UploadEvidenceOptions = {}
): Promise<EvidenceRecordResponse> {
  if (!(file instanceof File)) {
    throw new TypeError("uploadEvidence requires a File instance");
  }

  const pid = coerceProjectIdForApi(projectId);
  const formData = new FormData();
  formData.append("file", file);
  formData.append("type", options.type ?? "inspection_doc");
  if (options.title?.trim()) formData.append("title", options.title.trim());
  if (options.trade?.trim()) formData.append("trade", options.trade.trim());
  if (options.specSection?.trim()) {
    formData.append("spec_section", options.specSection.trim());
  }
  if (options.meta) {
    formData.append("meta", JSON.stringify(options.meta));
  }

  const response = await fetch(resolveFetchUrl(`/api/projects/${pid}/evidence`), {
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

  return response.json() as Promise<EvidenceRecordResponse>;
}
