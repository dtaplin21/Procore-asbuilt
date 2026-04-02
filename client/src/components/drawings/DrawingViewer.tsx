import { useEffect, useMemo, useRef, useState } from "react";

import DrawingOverlayLayer from "@/components/drawing-workspace/drawing_overlay_layer";
import PanZoomContainer from "@/components/drawing-workspace/pan_zoom_container";
import WorkspaceEmptyState from "@/components/drawing-workspace/workspace_empty_state";
import AlignedSubOverlay from "@/components/drawings/AlignedSubOverlay";
import { useResizeObserver } from "@/hooks/use_resize_observer";
import type {
  DrawingAlignmentTransformResponse,
  DrawingComparisonWorkspaceResponse,
  DrawingDiff,
  DrawingWorkspaceDrawing,
} from "@/types/drawing_workspace";

type Props = {
  drawing: DrawingWorkspaceDrawing | null;
  selectedDiff: DrawingDiff | null;
  /** Compare POST payload — when set, master/sub URLs come from the same response. */
  comparisonWorkspace?: DrawingComparisonWorkspaceResponse | null;
  isLoadingComparisonWorkspace?: boolean;
  showOverlay: boolean;
  overlayOpacity: number;
};

export default function DrawingViewer({
  drawing,
  selectedDiff,
  comparisonWorkspace,
  isLoadingComparisonWorkspace,
  showOverlay,
  overlayOpacity,
}: Props) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const imageBounds = useResizeObserver(stageRef);

  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);

  const masterSrc = comparisonWorkspace?.masterDrawing.fileUrl ?? drawing?.fileUrl;
  const masterName = comparisonWorkspace?.masterDrawing.name ?? drawing?.name;

  useEffect(() => {
    setImageLoaded(false);
    setImageError(null);
  }, [masterSrc]);

  const alignmentTransform: DrawingAlignmentTransformResponse | null =
    comparisonWorkspace?.alignment?.transform ?? null;

  const canRenderOverlay = useMemo(() => {
    return imageLoaded && imageBounds.width > 0 && imageBounds.height > 0;
  }, [imageLoaded, imageBounds.width, imageBounds.height]);

  const showSubOverlay = Boolean(
    showOverlay &&
      comparisonWorkspace &&
      alignmentTransform &&
      canRenderOverlay
  );

  if (!drawing) {
    return (
      <WorkspaceEmptyState
        title="No drawing available"
        description="The workspace could not load the master drawing."
      />
    );
  }

  const status = (drawing.processingStatus ?? "pending").toLowerCase();

  if (status === "failed") {
    return (
      <div className="flex h-full min-h-[70vh] flex-col overflow-hidden rounded-xl border bg-white">
        <div className="border-b px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">{drawing.name}</h2>
          <p className="text-sm text-slate-500">Drawing #{drawing.id}</p>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
          <div className="rounded border border-red-200 bg-red-50 p-6 text-sm text-red-700">
            <div className="font-medium">Rendering failed</div>
            <div className="mt-2 text-slate-600">
              {drawing.processingError || "The drawing could not be rendered."}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (status === "pending" || status === "processing") {
    return (
      <div className="flex h-full min-h-[70vh] flex-col overflow-hidden rounded-xl border bg-white">
        <div className="border-b px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">{drawing.name}</h2>
          <p className="text-sm text-slate-500">
            Drawing #{drawing.id}
            {status === "processing" ? " • Rendering…" : " • Queued for rendering"}
          </p>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
          <p className="text-sm text-slate-500">
            {status === "processing"
              ? "Rendering drawing pages…"
              : "Waiting for render to start…"}
          </p>
        </div>
      </div>
    );
  }

  if (!drawing.fileUrl) {
    return (
      <WorkspaceEmptyState
        title="Drawing file unavailable"
        description="The drawing exists, but its file URL is missing."
      />
    );
  }

  return (
    <div className="flex h-full min-h-[70vh] flex-col overflow-hidden rounded-xl border bg-white">
      <div className="border-b px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{drawing.name}</h2>
            <p className="text-sm text-slate-500">
              Drawing #{drawing.id}
              {selectedDiff ? ` • Selected diff #${selectedDiff.id}` : ""}
            </p>
          </div>

          <div className="text-right text-xs text-slate-500">
            <div>Source: {drawing.source || "unspecified"}</div>
            <div>{selectedDiff?.diffRegions?.length ?? 0} highlighted region(s)</div>
          </div>
        </div>
      </div>

      <PanZoomContainer>
        <div
          ref={stageRef}
          className="relative inline-block w-full max-w-[1200px]"
          data-testid="drawing-viewer-stage"
        >
          {isLoadingComparisonWorkspace ? (
            <div className="flex min-h-[240px] min-w-[320px] items-center justify-center rounded border border-slate-200 bg-slate-50 text-sm text-slate-500">
              Loading comparison workspace…
            </div>
          ) : null}

          {!isLoadingComparisonWorkspace && !imageLoaded && !imageError ? (
            <div className="absolute inset-0 z-10 flex min-h-[240px] min-w-[320px] items-center justify-center rounded bg-white/80 text-sm text-slate-500">
              Loading drawing image...
            </div>
          ) : null}

          {!isLoadingComparisonWorkspace && imageError ? (
            <div className="flex min-h-[400px] min-w-[600px] items-center justify-center rounded border border-red-200 bg-red-50 p-6 text-sm text-red-700">
              {imageError}
            </div>
          ) : null}

          {!isLoadingComparisonWorkspace && !imageError ? (
            comparisonWorkspace ? (
              <div className="relative w-full overflow-hidden rounded-lg border bg-black/5">
                <img
                  src={masterSrc}
                  alt={masterName ?? "Master drawing"}
                  className="relative z-0 block h-auto w-full max-h-[80vh] select-none"
                  onLoad={() => {
                    setImageLoaded(true);
                  }}
                  onError={() => {
                    setImageError("Failed to load drawing image.");
                  }}
                  data-testid="drawing-viewer-image"
                  draggable={false}
                />

                {showSubOverlay ? (
                  <AlignedSubOverlay
                    src={comparisonWorkspace.subDrawing.fileUrl}
                    alt={comparisonWorkspace.subDrawing.name}
                    transform={alignmentTransform!}
                    opacity={overlayOpacity}
                  />
                ) : null}

                {canRenderOverlay ? (
                  <DrawingOverlayLayer
                    diff={selectedDiff}
                    viewerSize={{
                      width: imageBounds.width,
                      height: imageBounds.height,
                    }}
                  />
                ) : null}
              </div>
            ) : (
              <>
                <img
                  src={drawing.fileUrl}
                  alt={drawing.name}
                  className="relative z-0 block max-h-[80vh] max-w-[1200px] select-none rounded"
                  onLoad={() => {
                    setImageLoaded(true);
                  }}
                  onError={() => {
                    setImageError("Failed to load drawing image.");
                  }}
                  data-testid="drawing-viewer-image"
                  draggable={false}
                />

                {canRenderOverlay ? (
                  <DrawingOverlayLayer
                    diff={selectedDiff}
                    viewerSize={{
                      width: imageBounds.width,
                      height: imageBounds.height,
                    }}
                  />
                ) : null}
              </>
            )
          ) : null}
        </div>
      </PanZoomContainer>
    </div>
  );
}
