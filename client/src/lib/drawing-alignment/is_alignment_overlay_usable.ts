import type { DrawingComparisonWorkspaceResponse } from "@/types/drawing_workspace";

/** True when compare workspace alignment is safe to use for the sub overlay (status + transform matrix). */
export function isAlignmentOverlayUsable(
  workspace: DrawingComparisonWorkspaceResponse | undefined | null
): boolean {
  if (!workspace?.alignment) return false;
  const a = workspace.alignment;
  const t = a.transform;
  return (
    a.status === "complete" &&
    Boolean(t) &&
    Array.isArray(t?.matrix)
  );
}
