import type {
  DrawingRegionCreate,
  DrawingRegionResponse,
  DrawingRegionUpdate,
  RegionInspectionSummaryResponse,
} from "@shared/schema";

import { requestJson } from "@/lib/api/http";

export function drawingRegionsQueryKey(
  projectId: string | number,
  masterDrawingId: string | number,
) {
  return ["drawing-regions", String(projectId), String(masterDrawingId)] as const;
}

export function regionInspectionSummaryQueryKey(
  projectId: string | number,
  masterDrawingId: string | number,
) {
  return [
    "region-inspection-summary",
    String(projectId),
    String(masterDrawingId),
  ] as const;
}

function regionsBaseUrl(projectId: number, masterDrawingId: number): string {
  return `/api/projects/${projectId}/drawings/${masterDrawingId}/regions`;
}

export function buildRegionInspectionSummaryUrl(
  projectId: number,
  masterDrawingId: number,
): string {
  return `/api/projects/${projectId}/drawings/${masterDrawingId}/region-inspection-summary`;
}

export async function fetchDrawingRegions(params: {
  projectId: string | number;
  masterDrawingId: string | number;
}): Promise<DrawingRegionResponse[]> {
  const projectId = Number(params.projectId);
  const masterDrawingId = Number(params.masterDrawingId);
  if (!Number.isFinite(projectId) || !Number.isFinite(masterDrawingId)) {
    return [];
  }
  return requestJson<DrawingRegionResponse[]>(
    regionsBaseUrl(projectId, masterDrawingId),
  );
}

export async function createDrawingRegion(params: {
  projectId: string | number;
  masterDrawingId: string | number;
  body: DrawingRegionCreate;
}): Promise<DrawingRegionResponse> {
  const projectId = Number(params.projectId);
  const masterDrawingId = Number(params.masterDrawingId);
  return requestJson<DrawingRegionResponse>(regionsBaseUrl(projectId, masterDrawingId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params.body),
  });
}

export async function updateDrawingRegion(params: {
  projectId: string | number;
  masterDrawingId: string | number;
  regionId: string | number;
  body: DrawingRegionUpdate;
}): Promise<DrawingRegionResponse> {
  const projectId = Number(params.projectId);
  const masterDrawingId = Number(params.masterDrawingId);
  const regionId = Number(params.regionId);
  return requestJson<DrawingRegionResponse>(
    `${regionsBaseUrl(projectId, masterDrawingId)}/${regionId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params.body),
    },
  );
}

export async function deleteDrawingRegion(params: {
  projectId: string | number;
  masterDrawingId: string | number;
  regionId: string | number;
}): Promise<void> {
  const projectId = Number(params.projectId);
  const masterDrawingId = Number(params.masterDrawingId);
  const regionId = Number(params.regionId);
  await requestJson<void>(
    `${regionsBaseUrl(projectId, masterDrawingId)}/${regionId}`,
    { method: "DELETE" },
  );
}

export async function fetchRegionInspectionSummary(params: {
  projectId: string | number;
  masterDrawingId: string | number;
}): Promise<RegionInspectionSummaryResponse> {
  const projectId = Number(params.projectId);
  const masterDrawingId = Number(params.masterDrawingId);
  if (!Number.isFinite(projectId) || !Number.isFinite(masterDrawingId)) {
    return { items: [] };
  }
  return requestJson<RegionInspectionSummaryResponse>(
    buildRegionInspectionSummaryUrl(projectId, masterDrawingId),
  );
}
