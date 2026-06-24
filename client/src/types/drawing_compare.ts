import type { DrawingAlignmentPersisted, DrawingTransform } from "@shared/schema";

import type {
  DrawingDiffRegion,
  ReviewBadgeTone,
} from "@/types/drawing_workspace";

/** Legacy compare / alignment API types (backend routes remain until PR7 cleanup). */

export type DrawingBasicSummary = {
  id: number;
  name: string;
};

export type DrawingAlignment = DrawingAlignmentPersisted & {
  projectId: number;
  masterDrawingId: number;
  subDrawingId: number;
  alignmentStatus?: string | null;
  transformMatrix?: Record<string, unknown> | null;
  createdAt?: string | null;
  subDrawing: DrawingBasicSummary;
};

export type DrawingAlignmentsResponse = {
  alignments: DrawingAlignment[];
};

export type DrawingDiff = {
  id: number;
  alignmentId: number;
  summary?: string | null;
  severity?: string | null;
  resolved?: boolean;
  changeDetails?: Record<string, unknown> | null;
  semanticSummary?: Record<string, unknown> | null;
  reviewBadge?: ReviewBadgeTone | null;
  createdAt?: string | null;
  diffRegions: DrawingDiffRegion[];
};

export type DrawingOverlayDrawingSummary = {
  id: number;
  name: string;
  fileUrl: string;
  contentType?: string | null;
  pageCount?: number | null;
};

export type DrawingAlignmentTransformResponse = DrawingTransform;

export type DrawingAlignmentOverlayResponse = DrawingAlignmentPersisted & {
  method: string;
  status: string;
  alignmentStatus?: string | null;
  subDrawing: DrawingBasicSummary;
  createdAt?: string | null;
  transform: DrawingAlignmentTransformResponse | null;
  errorMessage?: string | null;
};

export type DrawingAlignmentListItem = DrawingAlignment | DrawingAlignmentOverlayResponse;

export type ProjectComparisonProgressMetric = {
  comparedCount: number;
  totalRelevantCount: number;
  label: string;
};

export type DiffRiskMetric = {
  unresolvedHighSeverityCount: number;
  label: string;
};

export type DrawingComparisonWorkspaceResponse = {
  masterDrawing: DrawingOverlayDrawingSummary;
  subDrawing: DrawingOverlayDrawingSummary;
  alignment: DrawingAlignmentOverlayResponse;
  diffs: DrawingDiff[];
  comparisonProgress?: ProjectComparisonProgressMetric | null;
  highSeverityDiffRisk?: DiffRiskMetric | null;
  reviewBadge?: ReviewBadgeTone | null;
};

export type DrawingDiffsResponse = {
  diffs: DrawingDiff[];
};
