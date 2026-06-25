/**
 * Shared frontend types for the inspection-on-master-drawing data flow.
 * These mirror the JSON shapes the backend actually serializes:
 *   - DrawingOverlay: EvidenceUploadResponse.overlay_ids resolve to rows
 *     persisted by backend/services/overlay_storage.py, shaped per
 *     backend/models/drawing_overlay.py + DrawingOverlayRecord.to_dict()
 *     in backend/ai/pipelines/inspection_mapping.py.
 *   - InspectionRun: a run record from backend/api/routes/inspections.py.
 *   - EvidenceUploadResponse: the exact response shape from
 *     POST /inspections/runs/{run_id}/evidence (backend/api/routes/evidence.py).
 *
 * Field names are camelCase to match the backend's to_dict() serialization
 * convention used throughout this pipeline (see e.g.
 * NormalizedEvidenceTags.to_dict() — inspectionTypes, fieldConditions, etc).
 */

export type OverlaySeverity = "high" | "medium" | "info";

export type ConfidenceLabel = "High Confidence" | "Medium Confidence" | "Low Confidence";

/** Mirrors NormalizedEvidenceTags.to_dict() from inspection_mapping.py. */
export interface NormalizedEvidenceTags {
  inspectionTypes: string[];
  inspectionStatuses: string[];
  locations: string[];
  trades: string[];
  fieldConditions: string[];
  actions: string[];
  markupTerms: string[];
  confidenceLabel: ConfidenceLabel;
}

/** Mirrors DrawingOverlayRecord.to_dict() — what the backend returns for
 * each resolved finding placed on a master drawing. */
export interface DrawingOverlay {
  id: string;
  drawingId: string;
  inspectionRunId: string;
  /** Fractional (0-1) [x0, y0, x1, y1] on the master drawing, or null
   * for an overlay that hasn't been geometrically placed (shouldn't
   * normally occur for persisted overlays — unresolved evidence is
   * tracked separately, see UnresolvedEvidenceSummary below). */
  bbox: [number, number, number, number] | null;
  label: string;
  severity: OverlaySeverity;
  tags: NormalizedEvidenceTags;
  /** Date the inspection was PERFORMED, per the document text — ISO
   * date string (YYYY-MM-DD), or null if the document didn't state one
   * the extractor recognized. Distinct from uploadedAt. */
  inspectionDate: string | null;
  /** When this record was created in our system (the upload moment).
   * ISO 8601 datetime string, always set. */
  uploadedAt: string;
}

export type InspectionRunStatus =
  | "pending"
  | "processing"
  | "complete"
  | "failed";

/** A single inspection run — created when a user starts an inspection
 * upload flow on the Inspections page, and the target of evidence
 * uploads via POST .../runs/{id}/evidence. */
export interface InspectionRun {
  id: string;
  projectId: string;
  masterDrawingId: string;
  status: InspectionRunStatus;
  createdAt: string;
  /** Populated once at least one evidence file has been processed for
   * this run. Optional join field — see backend/models/schemas.py note
   * in the merge plan about embedding evidence_title on
   * InspectionRunResponse to avoid N+1 fetches. */
  evidenceTitle?: string | null;
  evidenceFilename?: string | null;
  evidenceFileId?: string | null;
  overlaysCreated?: number;
  unresolvedCount?: number;
}

/** A piece of evidence that could not be automatically placed on the
 * master drawing — mirrors UnresolvedEvidence from
 * backend/models/drawing_overlay.py. Surfaced on Inspections so a
 * reviewer knows a submission needs manual follow-up. */
export interface UnresolvedEvidenceSummary {
  id: string;
  evidenceId: string;
  inspectionRunId: string;
  drawingId: string;
  reason: string;
  uploadedAt: string;
  resolvedByHuman: boolean;
}

/** Exact response shape of POST /inspections/runs/{run_id}/evidence —
 * see EvidenceUploadResponse in backend/api/routes/evidence.py. */
export interface EvidenceUploadResponse {
  evidence_id: string;
  overlays_created: number;
  unresolved_count: number;
  untagged_region_count: number;
  overlay_ids: string[];
}
