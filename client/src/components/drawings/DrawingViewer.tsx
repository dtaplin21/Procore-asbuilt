import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import DrawingOverlayLayer from "@/components/drawing-workspace/drawing_overlay_layer";
import PanZoomContainer from "@/components/drawing-workspace/pan_zoom_container";
import WorkspaceEmptyState from "@/components/drawing-workspace/workspace_empty_state";
import { useDrawingOverlays } from "@/hooks/use-inspection-runs";
import { useResizeObserver } from "@/hooks/use_resize_observer";
import { toOverlayRegions } from "@/lib/drawing-overlays/inspection_overlay";
import type { DrawingWorkspaceDrawing } from "@/types/drawing_workspace";

import { apiUrl } from "@/lib/api/base_url";

/** True when `fileUrl` is the raw upload route (PDF/image bytes), not a rendered page PNG. */
function legacyMasterUsesPdfEmbed(drawing: DrawingWorkspaceDrawing): boolean {
  const file = drawing.fileUrl.toLowerCase();
  if (file.includes("/pages/") && file.includes("/image")) return false;
  if (file.includes("/file")) return true;
  const source = (drawing.sourceFileUrl ?? "").toLowerCase();
  if (source.includes("/file")) return true;
  return drawing.name.toLowerCase().endsWith(".pdf");
}

function messageForDrawingImageLoadFailure(relativeUrl: string): string {
  const u = relativeUrl.toLowerCase();
  if (u.includes("/file") && !u.includes("/pages/")) {
    return "Could not display the drawing as an image. The URL points at the original upload (often PDF). Run the render worker until page PNGs exist, then reload.";
  }
  return "Failed to load drawing image.";
}

type Props = {
  drawing: DrawingWorkspaceDrawing | null;
  projectId?: number | null;
  /** When set, overlays are limited to this inspection run (sidebar selection). */
  inspectionRunId?: number | null;
  /** Diff SVG: only unresolved / "changed" regions. */
  overlayShowChangesOnly?: boolean;
  /** Diff SVG: color by passed/failed/changed; when false, use a single highlight tone. */
  overlayShowInspectionStatuses?: boolean;
};

export default function DrawingViewer({
  drawing,
  projectId: projectIdProp,
  inspectionRunId = null,
  overlayShowChangesOnly = false,
  overlayShowInspectionStatuses = true,
}: Props) {
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const layoutSize = useResizeObserver(layoutRef);
  const masterImgRef = useRef<HTMLImageElement | null>(null);

  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);

  const resolvedProjectId = projectIdProp ?? drawing?.projectId ?? null;
  const projectIdStr =
    resolvedProjectId != null && Number.isFinite(resolvedProjectId)
      ? String(resolvedProjectId)
      : null;
  const drawingIdStr =
    drawing?.id != null && Number.isFinite(drawing.id) ? String(drawing.id) : null;

  const { data: overlays = [], isLoading: overlaysLoading } = useDrawingOverlays(
    projectIdStr,
    drawingIdStr,
    { inspectionRunId }
  );
  const regions = useMemo(() => toOverlayRegions(overlays), [overlays]);

  const masterSrcRaw = drawing?.fileUrl ?? null;

  useEffect(() => {
    setImageLoaded(false);
    setImageError(null);
  }, [masterSrcRaw]);

  useLayoutEffect(() => {
    const img = masterImgRef.current;
    if (!img || !masterSrcRaw) return;
    if (img.complete && img.naturalWidth > 0) {
      setImageLoaded(true);
    }
  }, [masterSrcRaw]);

  const canRenderOverlay = useMemo(() => {
    return (
      !overlaysLoading &&
      imageLoaded &&
      layoutSize.width > 0 &&
      layoutSize.height > 0
    );
  }, [overlaysLoading, imageLoaded, layoutSize.width, layoutSize.height]);

  const onMasterLoad = useCallback(() => {
    setImageLoaded(true);
  }, []);

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
      <div className="flex min-h-[70vh] w-full flex-1 flex-col overflow-hidden rounded-xl border bg-white">
        <div className="border-b px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">{drawing.name}</h2>
          <p className="text-sm text-slate-500">Drawing #{drawing.id}</p>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
          <div className="rounded-md border border-red-200 bg-red-50 p-6 text-sm text-red-800">
            <div className="font-medium">Rendering failed</div>
            <div className="mt-2 text-red-700/90">
              {drawing.processingError || "The drawing could not be rendered."}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (status === "pending" || status === "processing") {
    return (
      <div className="flex min-h-[70vh] w-full flex-1 flex-col overflow-hidden rounded-xl border bg-white">
        <div className="border-b px-5 py-4">
          <h2 className="text-lg font-semibold text-slate-900">{drawing.name}</h2>
          <p className="text-sm text-slate-500">
            Drawing #{drawing.id}
            {status === "processing" ? " • Rendering…" : " • Queued for rendering"}
          </p>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
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

  const legacyPdfEmbed = legacyMasterUsesPdfEmbed(drawing);

  return (
    <div className="flex min-h-[70vh] w-full flex-1 flex-col overflow-hidden rounded-xl border bg-white">
      <div className="shrink-0 border-b px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{drawing.name}</h2>
            <p className="text-sm text-slate-500">Drawing #{drawing.id}</p>
          </div>

          <div className="text-right text-xs text-slate-500">
            <div>Source: {drawing.source || "unspecified"}</div>
            <div>
              {overlaysLoading
                ? "Loading overlays…"
                : `${regions.length} overlay region(s)`}
            </div>
          </div>
        </div>
      </div>

      <div className="flex w-full flex-1 flex-col min-h-[min(28rem,70vh)]">
        <PanZoomContainer>
          <div
            ref={layoutRef}
            className="relative inline-block w-full max-w-[1200px]"
            data-testid="drawing-viewer-stage"
          >
            {!imageLoaded && !imageError && !legacyPdfEmbed ? (
              <div className="absolute inset-0 z-10 flex min-h-[240px] min-w-[320px] items-center justify-center rounded bg-card/80 text-sm text-muted-foreground">
                Loading drawing image...
              </div>
            ) : null}

            {imageError ? (
              <div className="flex min-h-[400px] min-w-[600px] items-center justify-center rounded-md border border-red-200 bg-red-50 p-6 text-sm text-red-800">
                {imageError}
              </div>
            ) : legacyPdfEmbed ? (
              <iframe
                title={drawing.name}
                src={apiUrl(drawing.fileUrl)}
                className="relative z-0 block min-h-[min(75vh,36rem)] h-[min(85vh,56.25rem)] w-full max-w-[1200px] rounded-lg border border-border bg-card"
                data-testid="drawing-viewer-pdf"
              />
            ) : (
              <>
                <img
                  ref={masterImgRef}
                  src={drawing.fileUrl ? apiUrl(drawing.fileUrl) : ""}
                  alt={drawing.name}
                  className="relative z-0 block max-h-[80vh] max-w-[1200px] select-none rounded"
                  onLoad={onMasterLoad}
                  onError={() => {
                    setImageError(
                      messageForDrawingImageLoadFailure(drawing.fileUrl ?? "")
                    );
                  }}
                  data-testid="drawing-viewer-image"
                  draggable={false}
                />

                {canRenderOverlay && regions.length > 0 ? (
                  <DrawingOverlayLayer
                    regions={regions}
                    viewerSize={{
                      width: layoutSize.width,
                      height: layoutSize.height,
                    }}
                    showChangesOnly={overlayShowChangesOnly}
                    showInspectionStatuses={overlayShowInspectionStatuses}
                  />
                ) : null}
              </>
            )}
          </div>
        </PanZoomContainer>
      </div>
    </div>
  );
}
