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

/** Overlay / inspection UI chrome (amber=changed, green=passed, red=failed). */
export type ReviewBadgeTone = "changed" | "passed" | "failed";

/** Normalized geometry for inspection overlays (rect or polygon). */
export type DrawingDiffRegion = {
  id?: string | number;
  page?: number | null;
  shapeType?: "rect" | "polygon" | null;
  rect?: NormalizedRect | null;
  points?: NormalizedPoint[] | null;
  bbox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  } | null;
  changeType?: string | null;
  note?: string | null;
  reviewBadge?: ReviewBadgeTone | null;
};

export type DrawingResponse = DrawingSummary;

export type WorkspaceRouteParams = {
  projectId?: string;
  drawingId?: string;
};
