/**
 * API client for backend drawing regions — list/create/patch/delete (PR2) and
 * the region inspection summary (PR1). Calls the real routes in
 * backend/api/routes/drawing_regions.py.
 *
 * Reconciled with this codebase vs the reference wire-format client:
 *   - Project-scoped paths:
 *     `/api/projects/{projectId}/drawings/{masterDrawingId}/…`
 *   - Normalized geometry JSON on the wire (no pixel x/y/pageWidth conversion)
 *   - Integer IDs; backend summary JSON uses camelCase aliases (`regionId`, …)
 *   - POST requires `Idempotency-Key` (same as other mutating routes)
 */

import type {
  CreateDrawingRegionInput,
  DrawingRegionCreate,
  DrawingRegionResponse,
  DrawingRegionUpdate,
  UpdateDrawingRegionInput,
} from "@/lib/drawing-regions/types";
import type { RegionInspectionSummaryResponse } from "@shared/schema";

import { requestJson } from "@/lib/api/http";

export type {
  CreateDrawingRegionInput,
  DrawingRegion,
  DrawingRegionCreate,
  DrawingRegionResponse,
  DrawingRegionUpdate,
  UpdateDrawingRegionInput,
} from "@/lib/drawing-regions/types";
export type { RegionInspectionSummaryResponse } from "@shared/schema";

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

/** Alias for fetchDrawingRegions (reference naming). */
export const listDrawingRegions = fetchDrawingRegions;

export async function createDrawingRegion(params: {
  projectId: string | number;
  masterDrawingId: string | number;
  body: DrawingRegionCreate | CreateDrawingRegionInput;
}): Promise<DrawingRegionResponse> {
  const projectId = Number(params.projectId);
  const masterDrawingId = Number(params.masterDrawingId);
  return requestJson<DrawingRegionResponse>(regionsBaseUrl(projectId, masterDrawingId), {
    method: "POST",
    headers: {
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify(params.body),
  });
}

export async function updateDrawingRegion(params: {
  projectId: string | number;
  masterDrawingId: string | number;
  regionId: string | number;
  body: DrawingRegionUpdate | UpdateDrawingRegionInput;
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
