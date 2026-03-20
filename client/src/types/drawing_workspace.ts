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
