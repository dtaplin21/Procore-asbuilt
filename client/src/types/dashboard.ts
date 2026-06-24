export type WorkspaceLink = {
  projectId: number;
  masterDrawingId: number;
  inspectionRunId?: number | null;
  overlayId?: number | null;
};

export type FindingItem = {
  id: number;
  projectId: number;
  title: string;
  description?: string | null;
  severity?: string | null;
  createdAt?: string | null;
  workspaceLink?: WorkspaceLink | null;
};

export type InsightItem = {
  id: string;
  title: string;
  body?: string | null;
  type?: string | null;
  workspaceLink?: WorkspaceLink | null;
};
