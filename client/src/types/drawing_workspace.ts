export type DrawingSummary = {
  id: number;
  projectId: number;
  source?: string | null;
  name: string;
  fileUrl?: string | null;
  contentType?: string | null;
  pageCount?: number | null;
};

export type DrawingBasicSummary = {
  id: number;
  name: string;
};

export type DrawingAlignment = {
  id: number;
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

export type DrawingDiffRegion = {
  page?: number | null;
  bbox?: Record<string, unknown> | null;
  changeType?: string | null;
  note?: string | null;
};

export type DrawingDiff = {
  id: number;
  alignmentId: number;
  summary?: string | null;
  severity?: string | null;
  createdAt?: string | null;
  diffRegions: DrawingDiffRegion[];
};

export type DrawingDiffsResponse = {
  diffs: DrawingDiff[];
};

export type DrawingResponse = DrawingSummary;

export type WorkspaceRouteParams = {
  projectId?: string;
  masterDrawingId?: string;
};
