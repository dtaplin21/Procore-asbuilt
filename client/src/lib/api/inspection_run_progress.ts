import { requestJson } from "@/lib/api/http";

export type InspectionRunProgressStep = {
  id: string;
  label: string;
  status: "pending" | "running" | "done" | "error" | "skipped";
};

export type InspectionRunProgress = {
  run_id: number;
  job_id?: number | null;
  mode?: "index" | "match" | "full" | null;
  phase?: string | null;
  updated_at?: string | null;
  models?: {
    ocr_backend?: string | null;
    vision_model?: string | null;
  } | null;
  current?: {
    label?: string | null;
    detail?: string | null;
    page?: number | null;
    page_total?: number | null;
    file_name?: string | null;
  } | null;
  steps?: InspectionRunProgressStep[] | null;
  error?: string | null;
};

export function inspectionRunProgressUrl(projectId: number, runId: number): string {
  return `/api/projects/${projectId}/inspections/runs/${runId}/progress`;
}

export async function fetchInspectionRunProgress(
  projectId: number,
  runId: number,
): Promise<InspectionRunProgress> {
  return requestJson<InspectionRunProgress>(inspectionRunProgressUrl(projectId, runId));
}
