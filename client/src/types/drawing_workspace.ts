export type DrawingSummary = {
  id: number;
  projectId: number;
  source?: string | null;
  name: string;
  fileUrl?: string | null;
  contentType?: string | null;
  pageCount?: number | null;
};

/** Rendition-aware drawing payload for workspace viewer (GET /projects/:id/drawings/:id) */
export type DrawingWorkspaceDrawing = {
  id: number;
  name: string;
  fileUrl: string;
  sourceFileUrl: string;
  pageCount: number;
  activePage: number;
  widthPx?: number | null;
  heightPx?: number | null;
  processingStatus: string;
  processingError?: string | null;
  projectId?: number | null;
  source?: string | null;
};

export type DrawingBasicSummary = {
  id: number;
  name: string;
};

export type ProjectDrawingCandidate = {
  id: number;
  projectId: number;
  name: string;
  source?: string | null;
  fileUrl?: string | null;
  contentType?: string | null;
  pageCount?: number | null;
};

export type ProjectDrawingsResponse = {
  drawings: ProjectDrawingCandidate[];
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

export type NormalizedPoint = {
  x: number;
  y: number;
};

export type NormalizedRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type DrawingDiffRegion = {
  id?: string | number;
  page?: number | null;

  /**
   * Supported shapes:
   * - rect: uses rect
   * - polygon: uses points
   */
  shapeType?: "rect" | "polygon" | null;

  rect?: NormalizedRect | null;
  points?: NormalizedPoint[] | null;

  /**
   * Backward-compatible support if backend still sends bbox.
   * We convert bbox -> rect in the viewer layer.
   */
  bbox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  } | null;

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
  drawingId?: string;
};
