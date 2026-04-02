import { sql } from "drizzle-orm";
import { pgTable, text, varchar, integer, timestamp, boolean } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

// Project status types
export type ProjectStatus = "active" | "completed" | "on_hold";
export type SubmittalStatus = "pending" | "approved" | "rejected" | "in_review" | "revise_resubmit";
export type RFIStatus = "open" | "answered" | "closed" | "overdue";
export type InspectionStatus = "scheduled" | "in_progress" | "passed" | "failed" | "pending";
export type ObjectStatus = "not_started" | "pending_shop_drawing" | "shop_drawing_approved" | "installed" | "inspected" | "as_built";

// Project interface
export interface Project {
  id: string;
  name: string;
  address: string;
  status: ProjectStatus;
  procoreId?: string;
  procoreSynced: boolean;
  lastSyncedAt?: string;
  totalSubmittals: number;
  pendingSubmittals: number;
  totalRFIs: number;
  openRFIs: number;
  totalInspections: number;
  passedInspections: number;
}

export type InsertProject = Omit<Project, "id">;

// ----------------------------
// Project API types (matches backend ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse)
// ----------------------------

export interface ProjectCreate {
  company_id: number;
  name: string;
  status?: ProjectStatus;
  procore_project_id?: string | null;
}

export interface ProjectUpdate {
  name?: string | null;
  status?: ProjectStatus | null;
  procore_project_id?: string | null;
}

export interface ProjectResponse {
  id: number;
  company_id: number;
  name: string;
  status: ProjectStatus;
  procore_project_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  items: ProjectResponse[];
  total: number;
  limit: number;
  offset: number;
}

// ----------------------------
// Drawing API types (matches backend DrawingResponse)
// ----------------------------

export interface DrawingResponse {
  id: number;
  name: string;
  file_url?: string | null;
  content_type?: string | null;
  page_count?: number | null;
  created_at: string;
}

// ----------------------------
// Evidence API types (matches backend EvidenceRecordResponse, EvidenceListResponse)
// ----------------------------

export interface EvidenceRecordResponse {
  id: number;
  type: string;
  trade?: string | null;
  spec_section?: string | null;
  title: string;
  file_url?: string | null;
  content_type?: string | null;
  created_at: string;
}

export interface EvidenceListResponse {
  items: EvidenceRecordResponse[];
  total: number;
  limit: number;
  offset: number;
}

// ----------------------------
// Drawing Region API types (matches backend DrawingRegionCreate, DrawingRegionResponse)
// geometry: rect { type, x, y, width, height } or polygon { type, points } — normalized 0-1
// ----------------------------

export interface DrawingRegionCreate {
  label: string;
  page?: number;
  geometry: Record<string, unknown>; // { type: "rect", x, y, width, height } or { type: "polygon", points }
}

export interface DrawingRegionResponse {
  id: number;
  master_drawing_id: number;
  label: string;
  page: number;
  geometry: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// ----------------------------
// Drawing Alignment API types (matches backend DrawingAlignmentCreate, DrawingAlignmentResponse, AlignmentUpdate)
// ----------------------------

export interface DrawingAlignmentCreate {
  sub_drawing_id: number;
  region_id?: number | null;
  method: string; // "manual" | "feature_match" | "vision"
}

export interface DrawingAlignmentResponse {
  id: number;
  master_drawing_id: number;
  sub_drawing_id: number;
  region_id?: number | null;
  method: string;
  transform?: Record<string, unknown> | null;
  status: string;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlignmentUpdate {
  status?: string | null;
  transform?: Record<string, unknown> | null;
  error_message?: string | null;
}

export interface DrawingAlignmentListResponse {
  items: DrawingAlignmentResponse[];
  total: number;
  limit: number;
  offset: number;
}

// ----------------------------
// Drawing workspace overlay — POST /compare (snake_case; typed transform matrix)
// ----------------------------

/** Aligns with backend TransformKind / overlay transform JSON. */
export type DrawingTransformType = "identity" | "affine" | "homography";

/**
 * Homography (9) or affine (6) coefficients as flat numbers — never `any`.
 *
 * **Affine MVP (6 numbers)** — row-major 2×3 that maps column vectors [x, y, 1]ᵀ (sub → master):
 * `[a, b, tx, c, d, ty]`  ≡  `[[a, b, tx], [c, d, ty]]`
 * CSS `matrix(a, b, c, d, e, f)` uses columns `[[a, c, e], [b, d, f]]`, so convert in one place
 * (see `toCssMatrix` in `AlignedSubOverlay.tsx`): `matrix(a, c, b, d, tx, ty)`.
 *
 * **Homography (9)** — row-major 3×3; the affine/CSS path uses the first two rows as above.
 */
export interface DrawingTransform {
  type: DrawingTransformType;
  matrix: number[];
  confidence?: number | null;
  meta?: Record<string, unknown> | null;
}

export interface DrawingOverlayDrawingSummary {
  id: number;
  name: string;
  file_url: string;
  content_type?: string | null;
  page_count?: number | null;
}

/**
 * POST /compare alignment payload. `transform` is null when alignment is queued, failed, or not yet computed.
 * (Wire JSON may use camelCase aliases depending on client; this is the logical contract.)
 */
export interface DrawingAlignmentOverlayResponse {
  id: number;
  method: string;
  status: string;
  transform: DrawingTransform | null;
  error_message?: string | null;
}

/** Workspace bundle for drawing comparison UI (`master_drawing` / `sub_drawing` match wire snake_case). */
export interface DrawingComparisonWorkspaceResponse {
  master_drawing: DrawingOverlayDrawingSummary;
  sub_drawing: DrawingOverlayDrawingSummary;
  alignment: DrawingAlignmentOverlayResponse;
  diffs: unknown[];
}

// Submittal (Shop Drawing) interface
export interface Submittal {
  id: string;
  projectId: string;
  number: string;
  title: string;
  description: string;
  status: SubmittalStatus;
  specSection: string;
  submittedBy: string;
  submittedDate: string;
  dueDate: string;
  aiScore?: number;
  aiAnalysis?: string;
  objectsCovered: string[];
  attachmentCount: number;
  revisionNumber: number;
}

export type InsertSubmittal = Omit<Submittal, "id">;

// RFI interface
export interface RFI {
  id: string;
  projectId: string;
  number: string;
  subject: string;
  question: string;
  status: RFIStatus;
  priority: "low" | "medium" | "high" | "critical";
  createdBy: string;
  assignedTo: string;
  createdDate: string;
  dueDate: string;
  answeredDate?: string;
  answer?: string;
  drawingReferences: string[];
  aiSuggestedResponse?: string;
}

export type InsertRFI = Omit<RFI, "id">;

// Inspection interface
export interface Inspection {
  id: string;
  projectId: string;
  number: string;
  title: string;
  type: string;
  status: InspectionStatus;
  scheduledDate: string;
  completedDate?: string;
  inspector: string;
  location: string;
  checklist: InspectionChecklistItem[];
  photos: string[];
  notes?: string;
  aiFindings: string[];
}

export interface InspectionChecklistItem {
  id: string;
  item: string;
  passed: boolean | null;
  notes?: string;
}

export type InsertInspection = Omit<Inspection, "id">;

// Drawing Object interface (for object recognition)
export interface DrawingObject {
  id: string;
  projectId: string;
  drawingId: string;
  objectType: string;
  objectId: string;
  status: ObjectStatus;
  x: number;
  y: number;
  width: number;
  height: number;
  linkedSubmittalId?: string;
  linkedInspectionId?: string;
  metadata: Record<string, string>;
}

export type InsertDrawingObject = Omit<DrawingObject, "id">;

// AI Insight interface
/** Deep link into workspace (matches backend WorkspaceLinkMetadata). */
export interface WorkspaceLinkMetadata {
  projectId: number;
  masterDrawingId: number;
  alignmentId?: number;
  diffId?: number;
}

export interface AIInsight {
  id: string;
  projectId: string;
  type: "compliance" | "deviation" | "recommendation" | "warning";
  severity: "low" | "medium" | "high" | "critical";
  title: string;
  description: string;
  affectedItems: string[];
  createdAt: string;
  resolved: boolean;
  relatedSubmittalId?: string;
  relatedRFIId?: string;
  relatedInspectionId?: string;
  workspaceLink?: WorkspaceLinkMetadata;
}

export type InsertAIInsight = Omit<AIInsight, "id">;

/** Single finding row from GET /api/projects/{id}/findings (matches backend FindingResponse). */
export interface FindingResponse {
  id: number;
  projectId: number;
  title: string;
  description?: string | null;
  severity?: string | null;
  type?: string | null;
  createdAt?: string | null;
  workspaceLink?: WorkspaceLinkMetadata;
}

/** Response for GET /api/projects/{id}/findings (matches backend FindingListResponse). */
export type FindingListResponse = {
  findings: FindingResponse[];
};

/** Paginated response for insights (matches backend InsightListResponse). */
export interface InsightListResponse {
  items: AIInsight[];
  total: number;
  limit: number;
  offset: number;
}

// Drawing Diff types (matches backend DrawingDiffResponse, RunDrawingDiffRequest)
export type DrawingDiffSeverity = "low" | "medium" | "high" | "critical";

/** Body for POST run drawing diff pipeline (matches backend RunDrawingDiffRequest). */
export interface RunDrawingDiffRequest {
  alignment_id: number;
  strategy?: string;
}

export interface DrawingDiffRegion {
  page: number;
  type: "rect" | "polygon";
  points: number[][];
  label?: string;
  confidence: number;
}

export interface DrawingDiff {
  id: number;
  alignmentId: number;
  findingId: number | null;
  summary: string;
  severity: DrawingDiffSeverity;
  diffRegions: DrawingDiffRegion[];
  createdAt: string;
}

/** Single diff item (matches backend DrawingDiffResponse; snake_case from API). */
export interface DrawingDiffResponse {
  id: number;
  alignment_id: number;
  finding_id: number | null;
  summary: string;
  severity: DrawingDiffSeverity;
  diff_regions: DrawingDiffRegion[];
  created_at: string;
}

/** Paginated list of diffs (API response shape; items use snake_case from backend). */
export interface DrawingDiffsListResponse {
  items: DrawingDiffResponse[];
  total: number;
  limit: number;
  offset: number;
}

// Inspection runs (Phase 4 pipeline)
export interface InspectionRun {
  id: number;
  project_id: number;
  master_drawing_id: number;
  evidence_id: number | null;
  inspection_type: string | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface InspectionRunListResponse {
  items: InspectionRun[];
  total: number;
  limit: number;
  offset: number;
}

export interface RunInspectionRequest {
  master_drawing_id: number;
  evidence_id?: number | null;
  inspection_type?: string | null;
}

// Drawing overlays (inspection or diff geometry on master drawing)
export interface DrawingOverlay {
  id: number;
  master_drawing_id: number;
  inspection_run_id: number | null;
  diff_id: number | null;
  geometry: Record<string, unknown>;
  status: string;
  meta: Record<string, unknown> | null;
  created_at: string;
}

// Procore Connection Status
export interface ProcoreConnection {
  connected: boolean;
  lastSyncedAt?: string;
  syncStatus: "idle" | "syncing" | "error";
  projectsLinked: number;
  errorMessage?: string;
}

// Dashboard Stats
export interface DashboardStats {
  totalProjects: number;
  activeProjects: number;
  totalSubmittals: number;
  pendingReview: number;
  approvedToday: number;
  openRFIs: number;
  overdueRFIs: number;
  scheduledInspections: number;
  passRate: number;
  aiInsightsCount: number;
  criticalAlerts: number;
}

// ----------------------------
// Dashboard summary (project-level overview)
// ----------------------------

// A minimal project summary returned by the dashboard endpoint. This mirrors
// ``ProjectSummary`` on the backend and is intentionally small so the UI can
// show basic information even before the full project record is fetched.
// Uses snake_case to match API response.
export interface ProjectSummary {
  id: number;
  name: string;
  company_id: number;
  procore_project_id?: string | null;
}

// Active company context information used for display/validation.
// Uses snake_case to match API response.
export interface CompanyContext {
  active_company_id?: number | null;
  project_company_id: number;
  matches_active_company: boolean;
}

// Synchronization health status shown on the dashboard header.
// Uses snake_case to match API response.
export interface SyncHealth {
  connected: boolean;
  sync_status: "idle" | "syncing" | "error";
  project_last_sync_at?: string | null;
  token_expires_at?: string | null;
  error_message?: string | null;
}

// Summary for the currently selected drawing, if any.
// Uses snake_case to match API response.
export interface CurrentDrawing {
  id: number;
  name: string;
  updated_at: string;
}

export type ProjectSummaryKpis = {
  total_findings: number;
  open_findings: number;
  drawings_count: number;
  evidence_count: number;
  inspections_count: number;
};

// Top-level dashboard summary response type. This matches the shape of the
// ``DashboardSummaryResponse`` pydantic model on the backend and is returned by
// GET /api/projects/{project_id}/dashboard/summary.
// Uses snake_case to match API response.
export interface DashboardSummary {
  project: ProjectSummary;
  company_context: CompanyContext;
  sync_health: SyncHealth;
  current_drawing: CurrentDrawing | null;
  kpis: ProjectSummaryKpis;
}

// ----------------------------
// Inspection runs (Phase 4 pipeline)
// ----------------------------

/** Single inspection run (API response shape; snake_case from backend). */
export interface InspectionRun {
  id: number;
  project_id: number;
  master_drawing_id: number;
  evidence_id: number | null;
  inspection_type: string | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

/** Paginated list of inspection runs. */
export interface InspectionRunListResponse {
  items: InspectionRun[];
  total: number;
  limit: number;
  offset: number;
}

/** Body for POST create inspection run. */
export interface RunInspectionRequest {
  master_drawing_id: number;
  evidence_id?: number | null;
  inspection_type?: string | null;
}

/** Drawing overlay (API response shape; snake_case from backend). */
export interface DrawingOverlay {
  id: number;
  master_drawing_id: number;
  inspection_run_id: number | null;
  diff_id: number | null;
  geometry: Record<string, unknown>;
  status: string;
  meta: Record<string, unknown> | null;
  created_at: string;
}

// Procore writeback (Phase 5)
export interface ProcoreWritebackRequest {
  inspection_run_id: number;
  mode: "dry_run" | "commit";
}

export interface ProcoreWritebackResponse {
  mode: "dry_run" | "commit";
  payload?: unknown;
  committed?: boolean;
  message?: string;
  procore_response?: unknown | null;
}

// Job Queue (matches backend JobResponse)
export type JobResponse = {
  id: number;
  user_id?: number | null;
  company_id?: number | null;
  project_id?: number | null;
  job_type: string;
  status: string;
  input_data?: Record<string, unknown> | null;
  output_url?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type JobListResponse = {
  jobs: JobResponse[];
};
