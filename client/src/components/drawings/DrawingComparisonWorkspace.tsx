import { useState } from "react";

import DrawingViewer from "@/components/drawings/DrawingViewer";
import type { DrawingWorkspaceDrawing } from "@/types/drawing_workspace";

type Props = {
  projectId: number;
  masterDrawing: DrawingWorkspaceDrawing | null;
};

/**
 * Workspace viewer shell: master sheet + inspection/diff overlays from GET /overlays.
 */
export default function DrawingComparisonWorkspace({
  projectId,
  masterDrawing,
}: Props) {
  const [showChangesOnly, setShowChangesOnly] = useState(false);
  const [showInspectionStatuses, setShowInspectionStatuses] = useState(true);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-card px-4 py-3 shadow-sm">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={showChangesOnly}
              onChange={(e) => setShowChangesOnly(e.target.checked)}
              className="rounded border-border text-primary focus:ring-primary"
            />
            Show changes only
          </label>

          <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox"
              checked={showInspectionStatuses}
              onChange={(e) => setShowInspectionStatuses(e.target.checked)}
              className="rounded border-border text-primary focus:ring-primary"
            />
            Show inspection statuses
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-4 border-t border-border pt-3 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Overlay legend</span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-amber-500" aria-hidden />
            Changed
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-green-600" aria-hidden />
            Passed
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-red-600" aria-hidden />
            Failed
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        <DrawingViewer
          projectId={projectId}
          drawing={masterDrawing}
          overlayShowChangesOnly={showChangesOnly}
          overlayShowInspectionStatuses={showInspectionStatuses}
        />
      </div>
    </div>
  );
}
