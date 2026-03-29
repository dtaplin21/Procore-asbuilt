export type WorkspaceLink = {
  projectId: number;
  masterDrawingId: number;
  alignmentId?: number | null;
  diffId?: number | null;
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
