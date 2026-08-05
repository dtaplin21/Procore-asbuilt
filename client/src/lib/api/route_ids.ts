/** Positive integer id for URLs and comparisons — works for project id or drawing id route params. */
function coercePositiveIntId(id: number | string): number {
  const n = typeof id === "number" ? id : Number(id);
  if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n)) {
    throw new TypeError("Invalid id");
  }
  return n;
}

/** Route params often arrive as strings; API paths must use finite numeric project ids. */
export function coerceProjectIdForApi(projectId: number | string): number {
  try {
    return coercePositiveIntId(projectId);
  } catch {
    throw new TypeError("Invalid project id");
  }
}

/** Same rules as project id: drawing ids must be numeric for URL paths and comparisons. */
export function coerceDrawingIdForApi(drawingId: number | string): number {
  try {
    return coercePositiveIntId(drawingId);
  } catch {
    throw new TypeError("Invalid drawing id");
  }
}
