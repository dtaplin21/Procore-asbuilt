/**
 * Overlay legend + severity-filter chrome wrapped around DrawingViewer.
 * Used on Objects (parent-owned overlays) and the legacy drawing workspace route.
 */

import { useMemo, useState } from "react";

import DrawingViewer from "@/components/drawings/DrawingViewer";
import {
  overlaySeverityBucket,
  type OverlaySeverityBucket,
} from "@/lib/drawing-overlays/inspection_overlay";
import type { RenderableRegion } from "@/lib/drawing-regions/region_display";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";
import type { DrawingWorkspaceDrawing } from "@/types/drawing_workspace";
import type { DrawingOverlay } from "@shared/schema";

const SEVERITY_LABEL: Record<OverlaySeverityBucket, string> = {
  high: "High severity",
  medium: "Medium severity",
  info: "Info",
};

const SEVERITY_ORDER: OverlaySeverityBucket[] = ["high", "medium", "info"];

export type DrawingComparisonWorkspaceProps = {
  projectId: number;
  masterDrawing: DrawingWorkspaceDrawing | null;
  selectedInspectionRunId?: number | null;
  /** When provided, parent owns overlay fetch (Objects page). Enables severity filtering. */
  overlays?: DrawingOverlay[];
  overlaysLoading?: boolean;
  focusedOverlayId?: string | null;
  onOverlayClick?: (overlay: DrawingOverlay) => void;
  /** PR4: region inspection summary, threaded through to DrawingViewer. */
  regionSummary?: RegionInspectionSummaryEntry[];
  /** PR4/PR5 admin toggle — see DrawingViewer's prop of the same name. */
  showInspectableAreas?: boolean;
  onRegionHoverChange?: (region: RenderableRegion | null) => void;
  onRegionClick?: (region: RenderableRegion) => void;
};

export function DrawingComparisonWorkspace({
  projectId,
  masterDrawing,
  selectedInspectionRunId = null,
  overlays: overlaysProp,
  overlaysLoading,
  focusedOverlayId = null,
  onOverlayClick,
  regionSummary = [],
  showInspectableAreas = false,
  onRegionHoverChange,
  onRegionClick,
}: DrawingComparisonWorkspaceProps) {
  const [showChangesOnly, setShowChangesOnly] = useState(false);
  const [showInspectionStatuses, setShowInspectionStatuses] = useState(true);
  const [hiddenSeverities, setHiddenSeverities] = useState<Set<OverlaySeverityBucket>>(
    new Set(),
  );

  const overlaysControlled = overlaysProp !== undefined;
  const sourceOverlays = overlaysProp ?? [];

  const visibleOverlays = useMemo(() => {
    if (!overlaysControlled) {
      return undefined;
    }
    return sourceOverlays.filter(
      (overlay) => !hiddenSeverities.has(overlaySeverityBucket(overlay)),
    );
  }, [overlaysControlled, sourceOverlays, hiddenSeverities]);

  const countsBySeverity = useMemo(() => {
    const counts: Record<OverlaySeverityBucket, number> = { high: 0, medium: 0, info: 0 };
    for (const overlay of sourceOverlays) {
      counts[overlaySeverityBucket(overlay)] += 1;
    }
    return counts;
  }, [sourceOverlays]);

  function toggleSeverity(severity: OverlaySeverityBucket) {
    setHiddenSeverities((prev) => {
      const next = new Set(prev);
      if (next.has(severity)) {
        next.delete(severity);
      } else {
        next.add(severity);
      }
      return next;
    });
  }

  return (
    <div
      className="flex h-full min-h-0 flex-col gap-3"
      data-testid="drawing-comparison-workspace"
    >
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-card px-4 py-3 shadow-sm">
        {overlaysControlled ? (
          <div
            className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm"
            data-testid="overlay-legend"
          >
            {SEVERITY_ORDER.map((severity) => (
              <label
                key={severity}
                className="flex cursor-pointer items-center gap-2"
                style={{ opacity: hiddenSeverities.has(severity) ? 0.45 : 1 }}
              >
                <input
                  type="checkbox"
                  checked={!hiddenSeverities.has(severity)}
                  onChange={() => toggleSeverity(severity)}
                  className="rounded border-border text-primary focus:ring-primary"
                />
                {SEVERITY_LABEL[severity]} ({countsBySeverity[severity]})
              </label>
            ))}
            {selectedInspectionRunId != null ? (
              <span className="text-muted-foreground">Run: {selectedInspectionRunId}</span>
            ) : null}
          </div>
        ) : null}

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
          inspectionRunId={selectedInspectionRunId}
          overlays={visibleOverlays}
          overlaysLoading={overlaysLoading}
          focusedOverlayId={focusedOverlayId}
          onOverlayClick={onOverlayClick}
          overlayShowChangesOnly={showChangesOnly}
          overlayShowInspectionStatuses={showInspectionStatuses}
          regionSummary={regionSummary}
          showInspectableAreas={showInspectableAreas}
          onRegionHoverChange={onRegionHoverChange}
          onRegionClick={onRegionClick}
        />
      </div>
    </div>
  );
}

export default DrawingComparisonWorkspace;
