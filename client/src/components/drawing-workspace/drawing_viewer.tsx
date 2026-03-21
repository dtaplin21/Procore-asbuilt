import { useEffect, useMemo, useRef, useState } from "react";
import PanZoomContainer from "@/components/drawing-workspace/pan_zoom_container";
import DrawingOverlayLayer from "@/components/drawing-workspace/drawing_overlay_layer";
import WorkspaceEmptyState from "@/components/drawing-workspace/workspace_empty_state";
import type {
  DrawingDiff,
  DrawingWorkspaceDrawing,
} from "@/types/drawing_workspace";
import type { ViewerSize } from "@/lib/drawing-overlays/overlay-types";

type Props = {
  drawing: DrawingWorkspaceDrawing | null;
  selectedDiff: DrawingDiff | null;
};

export default function DrawingViewer({ drawing, selectedDiff }: Props) {
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [viewerSize, setViewerSize] = useState<ViewerSize>({ width: 0, height: 0 });
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);

  useEffect(() => {
    setImageLoaded(false);
    setImageError(null);
    setViewerSize({ width: 0, height: 0 });
  }, [drawing?.fileUrl]);

  const canRenderOverlay = useMemo(() => {
    return viewerSize.width > 0 && viewerSize.height > 0;
  }, [viewerSize]);

  const updateViewerSize = () => {
    if (!imgRef.current) return;

    const nextWidth = imgRef.current.clientWidth;
    const nextHeight = imgRef.current.clientHeight;

    if (!nextWidth || !nextHeight) return;

    setViewerSize({
      width: nextWidth,
      height: nextHeight,
    });
  };

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
        <div className="relative inline-block" data-testid="drawing-viewer-stage">
          {!imageLoaded && !imageError ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded bg-white/80 text-sm text-slate-500">
              Loading drawing image...
            </div>
          ) : null}

          {imageError ? (
            <div className="flex min-h-[400px] min-w-[600px] items-center justify-center rounded border border-red-200 bg-red-50 p-6 text-sm text-red-700">
              {imageError}
            </div>
          ) : (
            <>
              <img
                ref={imgRef}
                src={drawing.fileUrl}
                alt={drawing.name}
                className="block max-h-[80vh] max-w-[1200px] select-none rounded"
                onLoad={() => {
                  setImageLoaded(true);
                  updateViewerSize();
                }}
                onError={() => {
                  setImageError("Failed to load drawing image.");
                }}
                data-testid="drawing-viewer-image"
                draggable={false}
              />

              {imageLoaded && canRenderOverlay ? (
                <DrawingOverlayLayer
                  diff={selectedDiff}
                  viewerSize={viewerSize}
                />
              ) : null}
            </>
          )}
        </div>
      </PanZoomContainer>
    </div>
  );
}
