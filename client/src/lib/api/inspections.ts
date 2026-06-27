/**
 * API client for inspection runs and evidence upload. uploadInspectionRunEvidence
 * calls the backend route:
 *   POST /api/projects/{project_id}/inspections/runs/{run_id}/evidence
 *   (backend/api/routes/evidence.py — multipart file upload, returns
 *   EvidenceUploadResponse).
 *
 * createInspectionRun targets POST /api/projects/{project_id}/inspections/runs
 * (backend/api/routes/inspections.py). Downstream callers only depend on this
 * function returning an InspectionRun with an `id`.
 */

import type {
  EvidenceUploadResponse,
  InspectionRun,
} from "@/types/inspection_overlay";

import { readApiError, resolveFetchUrl } from "@/lib/api/http";

async function parseJsonOrThrow<T>(response: Response, context: string): Promise<T> {
  if (!response.ok) {
    await readApiError(response);
  }
  return (await response.json()) as T;
}

type InspectionRunWire = {
  id: number | string;
  project_id: number | string;
  master_drawing_id: number | string;
  status: string;
  created_at: string;
  evidence_title?: string | null;
  evidence_filename?: string | null;
  evidence_file_id?: number | string | null;
  overlays_created?: number;
  unresolved_count?: number;
  region_id?: number | string | null;
  region_label?: string | null;
};

function mapInspectionRun(row: InspectionRunWire): InspectionRun {
  return {
    id: String(row.id),
    projectId: String(row.project_id),
    masterDrawingId: String(row.master_drawing_id),
    status: row.status as InspectionRun["status"],
    createdAt: row.created_at,
    evidenceTitle: row.evidence_title ?? null,
    evidenceFilename: row.evidence_filename ?? null,
    evidenceFileId:
      row.evidence_file_id != null ? String(row.evidence_file_id) : null,
    overlaysCreated: row.overlays_created,
    unresolvedCount: row.unresolved_count,
    regionId: row.region_id != null ? String(row.region_id) : null,
    regionLabel: row.region_label ?? null,
  };
}

function mapEvidenceUploadResponse(data: {
  evidence_id: number | string;
  overlays_created: number;
  unresolved_count: number;
  untagged_region_count: number;
  overlay_ids: Array<number | string>;
}): EvidenceUploadResponse {
  return {
    evidence_id: String(data.evidence_id),
    overlays_created: data.overlays_created,
    unresolved_count: data.unresolved_count,
    untagged_region_count: data.untagged_region_count,
    overlay_ids: data.overlay_ids.map(String),
  };
}

export interface CreateInspectionRunParams {
  projectId: string;
  masterDrawingId: string;
  /** When true, the backend creates the run record without immediately
   * attempting any legacy auto-mapping pass — the merge plan's upload
   * flow always creates the run first, then uploads evidence against it
   * as a separate step, so the pipeline runs exactly once per evidence
   * file rather than once at run-creation and again at upload. */
  skipPipeline?: boolean;
}

export async function createInspectionRun(
  params: CreateInspectionRunParams,
): Promise<InspectionRun> {
  const response = await fetch(
    resolveFetchUrl(
      `/api/projects/${encodeURIComponent(params.projectId)}/inspections/runs`,
    ),
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({
        master_drawing_id: Number(params.masterDrawingId),
        skip_pipeline: params.skipPipeline ?? true,
      }),
    },
  );
  const data = await parseJsonOrThrow<InspectionRunWire>(
    response,
    "Creating inspection run",
  );
  return mapInspectionRun(data);
}

export interface UploadInspectionRunEvidenceParams {
  projectId: string;
  runId: string;
  masterDrawingId: string;
  file: File;
}

/**
 * Upload one evidence file against an inspection run.
 * POST /api/projects/{project_id}/inspections/runs/{run_id}/evidence
 * with the file sent as multipart/form-data field "file" — see
 * backend/api/routes/evidence.py upload_inspection_run_evidence().
 */
export async function uploadInspectionRunEvidence(
  params: UploadInspectionRunEvidenceParams,
): Promise<EvidenceUploadResponse> {
  if (!(params.file instanceof File)) {
    throw new TypeError("uploadInspectionRunEvidence requires a File instance");
  }

  const formData = new FormData();
  formData.append("file", params.file);

  const response = await fetch(
    resolveFetchUrl(
      `/api/projects/${encodeURIComponent(params.projectId)}/inspections/runs/${encodeURIComponent(params.runId)}/evidence`,
    ),
    {
      method: "POST",
      credentials: "include",
      body: formData,
      // Deliberately no Content-Type header — the browser sets the
      // correct multipart/form-data boundary automatically.
    },
  );
  const data = await parseJsonOrThrow<{
    evidence_id: number | string;
    overlays_created: number;
    unresolved_count: number;
    untagged_region_count: number;
    overlay_ids: Array<number | string>;
  }>(response, "Uploading evidence");
  return mapEvidenceUploadResponse(data);
}

export async function fetchProjectInspectionRuns(
  projectId: string,
): Promise<InspectionRun[]> {
  const response = await fetch(
    resolveFetchUrl(
      `/api/projects/${encodeURIComponent(projectId)}/inspections/runs`,
    ),
    { credentials: "include" },
  );
  const data = await parseJsonOrThrow<{ items: InspectionRunWire[] }>(
    response,
    "Fetching inspection runs",
  );
  return data.items.map(mapInspectionRun);
}

/**
 * Build the URL for downloading the original evidence file a run's
 * mapping was produced from — per the merge plan's "Reference uploaded
 * inspections" requirement ("Link to original file:
 * /api/projects/{id}/evidence/{evidence_id}/file").
 */
export function evidenceFileDownloadUrl(
  projectId: string,
  evidenceFileId: string,
): string {
  return resolveFetchUrl(
    `/api/projects/${encodeURIComponent(projectId)}/evidence/${encodeURIComponent(evidenceFileId)}/file`,
  );
}
