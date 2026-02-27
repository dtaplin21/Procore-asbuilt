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
}

export type InsertAIInsight = Omit<AIInsight, "id">;

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
export interface ProjectSummary {
  id: string;
  name: string;
  companyId: string;
  procoreProjectId?: string;
}

// Active company context information used for display/validation.
export interface CompanyContext {
  activeCompanyId?: string; // null when there is no active connection
  projectCompanyId: string;
  matchesActiveCompany: boolean;
}

// Synchronization health status shown on the dashboard header.
export interface SyncHealth {
  connected: boolean;
  syncStatus: "idle" | "syncing" | "error";
  projectLastSyncAt?: string;
  tokenExpiresAt?: string;
  errorMessage?: string;
}

// Summary for the currently selected drawing, if any.
export interface CurrentDrawing {
  id: string;
  name: string;
  updatedAt: string;
}

// Top-level dashboard summary response type. This matches the shape of the
// ``DashboardSummaryResponse`` pydantic model on the backend and is returned by
// GET /api/projects/{project_id}/dashboard/summary.
export interface DashboardSummary {
  project: ProjectSummary;
  companyContext: CompanyContext;
  syncHealth: SyncHealth;
  currentDrawing: CurrentDrawing | null;
}
