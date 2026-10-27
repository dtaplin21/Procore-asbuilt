import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import DrawingOverlayLayer from "@/components/drawing-workspace/drawing_overlay_layer";
import { DrawingRegionLayer } from "@/components/drawing-workspace/drawing_region_layer";
import { RegionHoverTooltip } from "@/components/drawing-workspace/region_hover_tooltip";
import { InspectionTypeFilter } from "@/components/InspectionTypeFilter";
import { MarkupLayer } from "@/components/MarkupLayer";
import PanZoomContainer from "@/components/drawing-workspace/pan_zoom_container";
import WorkspaceEmptyState from "@/components/drawing-workspace/workspace_empty_state";
import { useDrawingMarkups } from "@/hooks/useDrawingMarkups";
import { useDrawingOverlays } from "@/hooks/use-inspection-runs";
import { useResizeObserver } from "@/hooks/use_resize_observer";
import { toOverlayRegions } from "@/lib/drawing-overlays/inspection_overlay";
import type { RenderableRegion } from "@/lib/drawing-regions/region_display";
import type { RegionInspectionSummaryEntry } from "@/lib/drawing-regions/types";
import { VocabCategory, VOCABULARY } from "@shared/inspection_vocabulary";
import type { DrawingOverlay } from "@shared/schema";
import type { MarkupTool } from "@/types/drawing_markup";
import type { DrawingWorkspaceDrawing } from "@/types/drawing_workspace";

import { apiUrl } from "@/lib/api/base_url";

const INSPECTION_TYPES = VOCABULARY[VocabCategory.InspectionType];
const INSPECTION_STATUSES = VOCABULARY[VocabCategory.InspectionStatus];
const MARKUP_TOOLS: MarkupTool[] = ["select", "polyline", "cloud", "arrow", "rect", "text"];

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
  /** When set, overlays are limited to this inspection run (e.g. Objects `?run=`). */
  inspectionRunId?: number | null;
  /** When provided, skips internal overlay fetch (parent owns the query). */
  overlays?: DrawingOverlay[];
  /** Loading state when `overlays` is supplied by the parent. */
  overlaysLoading?: boolean;
  /** Highlight one overlay by id (`?overlay=` on Objects). */
  focusedOverlayId?: string | null;
  /** Diff SVG: only unresolved / "changed" regions. */
  overlayShowChangesOnly?: boolean;
  /** Diff SVG: color by passed/failed/changed; when false, use a single highlight tone. */
  overlayShowInspectionStatuses?: boolean;
  /** PR4: backend region summary — bold inspected regions + optional faint setup outlines. */
  regionSummary?: RegionInspectionSummaryEntry[];
  showInspectableAreas?: boolean;
  onRegionHoverChange?: (region: RenderableRegion | null) => void;
  onRegionClick?: (region: RenderableRegion) => void;
  /** Optional overlay click handler (wired from DrawingComparisonWorkspace). */
  onOverlayClick?: (overlay: DrawingOverlay) => void;
  /** Name stored as created_by. Sent as X-Procore-User. */
  userName?: string;
};

export default function DrawingViewer({
  drawing,
  projectId: projectIdProp,
  inspectionRunId = null,
  overlays: overlaysProp,
  overlaysLoading: overlaysLoadingProp,
  focusedOverlayId = null,
  overlayShowChangesOnly = false,
  overlayShowInspectionStatuses = true,
  regionSummary = [],
  showInspectableAreas = false,
  onRegionHoverChange,
  onRegionClick,
  userName,
}: Props) {
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const layoutSize = useResizeObserver(layoutRef);
  const masterImgRef = useRef<HTMLImageElement | null>(null);

  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState<string | null>(null);
  const [hoveredRegion, setHoveredRegion] = useState<RenderableRegion | null>(null);
  const [cursorPosition, setCursorPosition] = useState<{ x: number; y: number } | null>(null);
  const page = drawing != null && drawing.activePage >= 1 ? drawing.activePage : 1;
  const { markups, summary, error: markupError, create, update, remove } = useDrawingMarkups(
    drawing?.id ?? null,
    page,
    { userName },
  );
  const [tool, setTool] = useState<MarkupTool>("select");
  const [inspectionType, setInspectionType] = useState(INSPECTION_TYPES[0] ?? "");
  const [markupStatus, setMarkupStatus] = useState("Open");
  const [selectedTypes, setSelectedTypes] = useState<Set<string> | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const allTypes = useMemo(
    () => new Set(summary.map((row) => row.inspection_type ?? "")),
    [summary],
  );
  const visibleTypes = selectedTypes ?? allTypes;
  const selectedMarkup = markups.find((markup) => markup.id === selectedId) ?? null;

  useEffect(() => {
    if (selectedId != null && !markups.some((markup) => markup.id === selectedId)) {
      setSelectedId(null);
    }
  }, [markups, selectedId]);

  const resolvedProjectId = projectIdProp ?? drawing?.projectId ?? null;
  const projectIdStr =
    resolvedProjectId != null && Number.isFinite(resolvedProjectId)
      ? String(resolvedProjectId)
      : null;
  const drawingIdStr =
    drawing?.id != null && Number.isFinite(drawing.id) ? String(drawing.id) : null;

  const overlaysControlled = overlaysProp !== undefined;

  const { data: fetchedOverlays = [], isLoading: fetchedOverlaysLoading } =
    useDrawingOverlays({
      projectId: projectIdStr ?? undefined,
      drawingId: drawingIdStr ?? undefined,
      runId: inspectionRunId != null ? String(inspectionRunId) : null,
      enabled: !overlaysControlled,
    });

  const overlays = overlaysControlled ? overlaysProp : fetchedOverlays;
  const overlaysLoading = overlaysControlled
    ? (overlaysLoadingProp ?? false)
    : fetchedOverlaysLoading;

  const regions = useMemo(() => toOverlayRegions(overlays), [overlays]);

  const visibleRegions = useMemo(() => {
    const inspectedRegionIds = new Set(
      regionSummary.filter((entry) => entry.state === "inspected").map((entry) => entry.regionId),
    );
    return regions.filter(
      (region) =>
        region.linkedRegionId == null || !inspectedRegionIds.has(region.linkedRegionId),
    );
  }, [regions, regionSummary]);

  const handleRegionHoverChange = useCallback(
    (region: RenderableRegion | null, position?: { x: number; y: number }) => {
      setHoveredRegion(region);
      if (position) {
        setCursorPosition(position);
      } else if (!region) {
        setCursorPosition(null);
      }
      onRegionHoverChange?.(region);
    },
    [onRegionHoverChange],
  );

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

      <div className="flex w-full min-h-[min(28rem,70vh)] flex-1">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
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
                <div className="relative inline-block" data-testid="drawing-viewer-page">
                  <img
                    ref={masterImgRef}
                    src={drawing.fileUrl ? apiUrl(drawing.fileUrl) : ""}
                    alt={drawing.name}
                    className="relative z-0 block max-h-[80vh] max-w-[1200px] select-none rounded"
                    onLoad={onMasterLoad}
                    onError={() => {
                      setImageError(messageForDrawingImageLoadFailure(drawing.fileUrl ?? ""));
                    }}
                    data-testid="drawing-viewer-image"
                    draggable={false}
                  />
                  <div
                    className="absolute inset-0 z-20"
                    onPointerDown={(event) => event.stopPropagation()}
                    onPointerMove={(event) => event.stopPropagation()}
                    onPointerUp={(event) => event.stopPropagation()}
                  >
                    <MarkupLayer
                      markups={markups}
                      tool={tool}
                      visibleTypes={visibleTypes}
                      selectedId={selectedId}
                      onSelect={setSelectedId}
                      onCreate={(kind, points, label) => {
                        void create({
                          page,
                          kind,
                          points,
                          label,
                          inspectionType,
                          status: markupStatus,
                        }).then((made) => {
                          if (made) setSelectedId(made.id);
                        });
                      }}
                    />
                  </div>
                </div>

                {canRenderOverlay ? (
                  <DrawingRegionLayer
                    summary={regionSummary}
                    showInspectableAreas={showInspectableAreas}
                    onRegionHoverChange={handleRegionHoverChange}
                    onRegionClick={onRegionClick}
                  />
                ) : null}

                <RegionHoverTooltip
                  hoveredRegion={hoveredRegion}
                  anchorPosition={cursorPosition}
                />

                {canRenderOverlay && visibleRegions.length > 0 ? (
                  <DrawingOverlayLayer
                    regions={visibleRegions}
                    viewerSize={{
                      width: layoutSize.width,
                      height: layoutSize.height,
                    }}
                    focusedOverlayId={focusedOverlayId}
                    showChangesOnly={overlayShowChangesOnly}
                    showInspectionStatuses={overlayShowInspectionStatuses}
                  />
                ) : null}
              </>
            )}
          </div>
        </PanZoomContainer>
        </div>
        {!legacyPdfEmbed ? (
          <aside
            aria-label="Markups"
            className="flex w-[280px] shrink-0 flex-col gap-3 overflow-y-auto border-l border-slate-200 p-3"
          >
            <div role="toolbar" aria-label="Markup tools" style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {MARKUP_TOOLS.map((markupTool) => (
                <button
                  key={markupTool}
                  type="button"
                  aria-pressed={tool === markupTool}
                  onClick={() => setTool(markupTool)}
                  style={{ fontWeight: tool === markupTool ? 700 : 400 }}
                >
                  {markupTool}
                </button>
              ))}
              <select aria-label="Inspection type" value={inspectionType} onChange={(event) => setInspectionType(event.target.value)}>
                {INSPECTION_TYPES.map((typeName) => <option key={typeName}>{typeName}</option>)}
              </select>
              <select aria-label="Status" value={markupStatus} onChange={(event) => setMarkupStatus(event.target.value)}>
                {INSPECTION_STATUSES.map((statusName) => <option key={statusName}>{statusName}</option>)}
              </select>
            </div>
            {markupError ? <p role="alert" style={{ color: "#b00020" }}>{markupError}</p> : null}
            <h3 style={{ margin: 0 }}>Inspection types</h3>
            <InspectionTypeFilter summary={summary} selected={visibleTypes} onChange={setSelectedTypes} />
            {selectedMarkup ? (
              <section aria-label="Selected markup" style={{ marginTop: 8, fontSize: 13 }}>
                <strong>{selectedMarkup.kind}</strong> #{selectedMarkup.id} by {selectedMarkup.createdBy}
                <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  <select
                    aria-label="Selected status"
                    value={selectedMarkup.status ?? ""}
                    onChange={(event) => update(selectedMarkup.id, { status: event.target.value || null })}
                  >
                    <option value="">No status</option>
                    {INSPECTION_STATUSES.map((statusName) => <option key={statusName}>{statusName}</option>)}
                  </select>
                  <button type="button" onClick={() => remove(selectedMarkup.id)}>Delete</button>
                </div>
              </section>
            ) : null}
          </aside>
        ) : null}
      </div>
    </div>
  );
}
