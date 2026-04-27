import { useEffect, useMemo, useRef, useState } from "react";
import PanZoomContainer from "@/components/drawing-workspace/pan_zoom_container";
import DrawingOverlayLayer from "@/components/drawing-workspace/drawing_overlay_layer";
import WorkspaceEmptyState from "@/components/drawing-workspace/workspace_empty_state";
import { useResizeObserver } from "@/hooks/use_resize_observer";
import type {
  DrawingDiff,
  DrawingWorkspaceDrawing,
} from "@/types/drawing_workspace";

type Props = {
  drawing: DrawingWorkspaceDrawing | null;
  selectedDiff: DrawingDiff | null;
};

export default function DrawingViewer({ drawing, selectedDiff }: Props) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const imageBounds = useResizeObserver(stageRef);

  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);

  useEffect(() => {
    setImageLoaded(false);
    setImageError(null);
  }, [drawing?.fileUrl]);

  const canRenderOverlay = useMemo(() => {
    return imageLoaded && imageBounds.width > 0 && imageBounds.height > 0;
  }, [imageLoaded, imageBounds.width, imageBounds.height]);

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
      <div className="flex h-full min-h-[70vh] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-lg font-semibold text-foreground">{drawing.name}</h2>
          <p className="text-sm text-muted-foreground">Drawing #{drawing.id}</p>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
          <div className="rounded border border-red-200 bg-red-50 p-6 text-sm text-red-700">
            <div className="font-medium">Rendering failed</div>
            <div className="mt-2 text-muted-foreground">
              {drawing.processingError || "The drawing could not be rendered."}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (status === "pending" || status === "processing") {
    return (
      <div className="flex h-full min-h-[70vh] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-lg font-semibold text-foreground">{drawing.name}</h2>
          <p className="text-sm text-muted-foreground">
            Drawing #{drawing.id}
            {status === "processing" ? " • Rendering…" : " • Queued for rendering"}
          </p>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
          <p className="text-sm text-muted-foreground">
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
    <div className="flex h-full min-h-[70vh] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      <div className="border-b border-border px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-foreground">{drawing.name}</h2>
            <p className="text-sm text-muted-foreground">
              Drawing #{drawing.id}
              {selectedDiff ? ` • Selected diff #${selectedDiff.id}` : ""}
            </p>
          </div>

          <div className="text-right text-xs text-muted-foreground">
            <div>Source: {drawing.source || "unspecified"}</div>
            <div>{selectedDiff?.diffRegions?.length ?? 0} highlighted region(s)</div>
          </div>
        </div>
      </div>

      <PanZoomContainer>
        <div
          ref={stageRef}
          className="relative inline-block"
          data-testid="drawing-viewer-stage"
        >
          {!imageLoaded && !imageError ? (
            <div className="absolute inset-0 z-10 flex min-h-[240px] min-w-[320px] items-center justify-center rounded bg-card/80 text-sm text-muted-foreground">
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
                src={drawing.fileUrl}
                alt={drawing.name}
                className="block max-h-[80vh] max-w-[1200px] select-none rounded"
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
          )}
        </div>
      </PanZoomContainer>
    </div>
  );
}
