/**
 * Objects page deep links (Part 6 — Option A).
 * `projectId` + optional `drawingId` are the source of truth for which project / master sheet
 * the page targets; bookmarkable and deterministic.
 */
export function objectsPagePath(
  projectId: number,
  drawingId?: number | null
): string {
  const q = new URLSearchParams({ projectId: String(projectId) });
  if (drawingId != null && Number.isFinite(drawingId)) {
    q.set("drawingId", String(drawingId));
  }
  return `/objects?${q.toString()}`;
}
