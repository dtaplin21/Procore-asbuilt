import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import DrawingOverlayLayer from "@/components/drawing-workspace/drawing_overlay_layer";
import PanZoomContainer from "@/components/drawing-workspace/pan_zoom_container";
import WorkspaceEmptyState from "@/components/drawing-workspace/workspace_empty_state";
import AlignedSubOverlay from "@/components/drawings/AlignedSubOverlay";
import { isAlignmentOverlayUsable } from "@/lib/drawing-alignment/is_alignment_overlay_usable";
import { computeComparisonRenderBox } from "@/lib/drawing-viewer/comparison-layout";
import { useResizeObserver } from "@/hooks/use_resize_observer";
import type {
  DrawingAlignmentTransformResponse,
  DrawingComparisonWorkspaceResponse,
  DrawingDiff,
  DrawingWorkspaceDrawing,
} from "@/types/drawing_workspace";

import { apiUrl } from "@/lib/api/base_url";

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
  /** Shared width probe for comparison layout (max-w-[1200px] row). */
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const layoutSize = useResizeObserver(layoutRef);

  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);
  /** Master intrinsic pixels — used with available width to size one shared render box. */
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);
  /** Sub intrinsic pixels — required to map alignment from natural space into the shared render box. */
  const [subNaturalSize, setSubNaturalSize] = useState<{ w: number; h: number } | null>(null);
  /** Fixed CSS px box for master + sub + diff overlay (same for all layers). */
  const [comparisonStackBox, setComparisonStackBox] = useState<{
    width: number;
    height: number;
  } | null>(null);

  const masterSrcRaw =
    comparisonWorkspace?.masterDrawing.fileUrl ?? drawing?.fileUrl;
  const masterName = comparisonWorkspace?.masterDrawing.name ?? drawing?.name;

  useEffect(() => {
    setImageLoaded(false);
    setImageError(null);
    setNaturalSize(null);
    setSubNaturalSize(null);
    setComparisonStackBox(null);
  }, [masterSrcRaw, comparisonWorkspace?.subDrawing.fileUrl]);

  /** Recompute the comparison box when the row width changes (resize) or natural size updates. */
  useEffect(() => {
    if (!comparisonWorkspace || !naturalSize) return;
    if (layoutSize.width <= 0) return;
    const box = computeComparisonRenderBox(
      naturalSize.w,
      naturalSize.h,
      layoutSize.width
    );
    if (box.width > 0 && box.height > 0) {
      setComparisonStackBox(box);
    }
  }, [comparisonWorkspace, naturalSize, layoutSize.width]);

  const alignmentTransform: DrawingAlignmentTransformResponse | null =
    comparisonWorkspace?.alignment?.transform ?? null;

  const alignmentOverlayUsable = useMemo(
    () => isAlignmentOverlayUsable(comparisonWorkspace),
    [comparisonWorkspace]
  );

  const viewerSize = useMemo(() => {
    if (comparisonWorkspace && comparisonStackBox) {
      return {
        width: comparisonStackBox.width,
        height: comparisonStackBox.height,
      };
    }
    return {
      width: layoutSize.width,
      height: layoutSize.height,
    };
  }, [comparisonWorkspace, comparisonStackBox, layoutSize.width, layoutSize.height]);

  const canRenderOverlay = useMemo(() => {
    if (comparisonWorkspace && !comparisonStackBox) return false;
    return (
      imageLoaded && viewerSize.width > 0 && viewerSize.height > 0
    );
  }, [
    comparisonWorkspace,
    comparisonStackBox,
    imageLoaded,
    viewerSize.width,
    viewerSize.height,
  ]);

  const showSubOverlay = Boolean(
    showOverlay &&
      comparisonWorkspace &&
      alignmentOverlayUsable &&
      alignmentTransform &&
      canRenderOverlay &&
      comparisonStackBox
  );

  const onComparisonMasterLoad = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      const img = e.currentTarget;
      setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
      setImageLoaded(true);
    },
    []
  );

  const onComparisonSubLoad = useCallback(
    (e: React.SyntheticEvent<HTMLImageElement>) => {
      const img = e.currentTarget;
      setSubNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
    },
    []
  );

  const onLegacyMasterLoad = useCallback(() => {
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
      <div className="flex h-full min-h-[70vh] flex-col overflow-hidden rounded-xl border bg-white">
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
      <div className="flex h-full min-h-[70vh] flex-col overflow-hidden rounded-xl border bg-white">
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
          ref={layoutRef}
          className="relative inline-block w-full max-w-[1200px]"
          data-testid="drawing-viewer-stage"
        >
          {isLoadingComparisonWorkspace ? (
            <div className="flex min-h-[240px] min-w-[320px] items-center justify-center rounded-md border border-border bg-muted/40 text-sm text-muted-foreground">
              Loading comparison workspace…
            </div>
          ) : null}

          {!isLoadingComparisonWorkspace && !imageLoaded && !imageError ? (
            <div className="absolute inset-0 z-10 flex min-h-[240px] min-w-[320px] items-center justify-center rounded bg-card/80 text-sm text-muted-foreground">
              Loading drawing image...
            </div>
          ) : null}

          {!isLoadingComparisonWorkspace && imageError ? (
            <div className="flex min-h-[400px] min-w-[600px] items-center justify-center rounded-md border border-red-200 bg-red-50 p-6 text-sm text-red-800">
              {imageError}
            </div>
          ) : null}

          {!isLoadingComparisonWorkspace && !imageError ? (
            comparisonWorkspace ? (
              <>
                {!alignmentOverlayUsable ? (
                  <div className="mb-2 rounded-md border border-primary/30 bg-primary-soft px-3 py-2 text-sm text-foreground">
                    Overlay unavailable for this alignment.
                  </div>
                ) : null}
                <div
                  className="relative mx-auto overflow-hidden rounded-lg border bg-black/5"
                  style={
                    comparisonStackBox
                      ? {
                          width: comparisonStackBox.width,
                          height: comparisonStackBox.height,
                        }
                      : { minHeight: 240 }
                  }
                >
                  <img
                  src={masterSrcRaw ? apiUrl(masterSrcRaw) : ""}
                  alt={masterName ?? "Master drawing"}
                  className={
                    comparisonStackBox
                      ? "absolute inset-0 z-0 h-full w-full select-none object-contain"
                      : "relative z-0 block h-auto w-full max-h-[80vh] select-none"
                  }
                  onLoad={onComparisonMasterLoad}
                  onError={() => {
                    setImageError("Failed to load drawing image.");
                  }}
                  data-testid="drawing-viewer-image"
                  draggable={false}
                />

                {showSubOverlay && alignmentTransform ? (
                  <AlignedSubOverlay
                    src={
                      comparisonWorkspace.subDrawing.fileUrl
                        ? apiUrl(comparisonWorkspace.subDrawing.fileUrl)
                        : ""
                    }
                    alt={comparisonWorkspace.subDrawing.name}
                    transform={alignmentTransform}
                    opacity={overlayOpacity}
                    masterNatural={naturalSize}
                    subNatural={subNaturalSize}
                    renderBox={
                      comparisonStackBox
                        ? {
                            w: comparisonStackBox.width,
                            h: comparisonStackBox.height,
                          }
                        : null
                    }
                    onLoad={onComparisonSubLoad}
                  />
                ) : null}

                {canRenderOverlay ? (
                  <DrawingOverlayLayer
                    diff={selectedDiff}
                    viewerSize={{
                      width: viewerSize.width,
                      height: viewerSize.height,
                    }}
                  />
                ) : null}
                </div>
              </>
            ) : (
              <>
                <img
                  src={drawing.fileUrl ? apiUrl(drawing.fileUrl) : ""}
                  alt={drawing.name}
                  className="relative z-0 block max-h-[80vh] max-w-[1200px] select-none rounded"
                  onLoad={onLegacyMasterLoad}
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
                      width: layoutSize.width,
                      height: layoutSize.height,
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
