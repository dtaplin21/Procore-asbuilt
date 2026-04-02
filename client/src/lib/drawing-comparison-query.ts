/** React Query key for POST compare workspace (cached after compare + useQuery). */
export const drawingComparisonWorkspaceQueryKey = (
  projectId: number,
  masterDrawingId: number,
  subDrawingId: number
) => ["drawingComparisonWorkspace", projectId, masterDrawingId, subDrawingId] as const;
