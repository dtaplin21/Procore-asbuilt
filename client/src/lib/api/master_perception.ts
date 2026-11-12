import type { MasterPerception } from "@/lib/testing/perception_model";
import { requestJson } from "@/lib/api/http";

export type MasterOption = {
  id: string;
  drawingNumber: string;
  projectId: number;
  projectName: string;
};

export function fetchTestingMasters(query: string): Promise<{ masters: MasterOption[] }> {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<{ masters: MasterOption[] }>(`/api/testing/masters${suffix}`);
}

export function fetchMasterPerception(
  masterId: string,
  page: number,
  evidenceRunId: string,
): Promise<MasterPerception> {
  const params = new URLSearchParams({ page: String(page) });
  if (evidenceRunId.trim()) params.set("evidenceRunId", evidenceRunId.trim());
  return requestJson<MasterPerception>(
    `/api/testing/masters/${encodeURIComponent(masterId)}/perception?${params.toString()}`,
  );
}
