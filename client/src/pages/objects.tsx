import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { 
  Layers, 
  Search, 
  Filter, 
  ZoomIn,
  Move,
  MousePointer,
  Grid3X3,
  List,
  Eye,
  AlertTriangle,
  Loader2,
} from "lucide-react";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { StatusBadge } from "@/components/status-badge";
import DrawingComparisonWorkspace from "@/components/drawings/DrawingComparisonWorkspace";
import InspectionRunsPanel from "@/components/drawing-workspace/inspection_runs_panel";
import { RegionEditor } from "@/components/drawing-workspace/region_editor";
import { ProcoreWritebackPanel } from "@/components/ProcoreWritebackPanel";
import type {
  DrawingObject,
  DrawingOverlay,
  ObjectStatus,
} from "@shared/schema";
import type { ProjectDrawingsResponse } from "@/types/drawing_workspace";
import { useDrawingOverlays } from "@/hooks/use-inspection-runs";
import { useRegionInspectionSummary } from "@/hooks/use-region-inspection-summary";
import { useCanonicalMasterDrawing } from "@/hooks/use_canonical_master_drawing";
import { useObjectsQueryParams } from "@/hooks/use_objects_query_params";
import { apiUrl } from "@/lib/api/base_url";
import { fetchProjectDrawings, projectDrawingsQueryKey } from "@/lib/api/drawings";
import { fetchMasterDrawing } from "@/lib/api/drawing_workspace";
import { toOverlayRegions } from "@/lib/drawing-overlays/inspection_overlay";
import type { RenderableRegion } from "@/lib/drawing-regions/region_display";
import { objectsPagePathWithParams } from "@/lib/objectsRoute";
import { useActiveProject } from "@/contexts/active_project_context";
import { replaceDashboardProjectIdInUrl } from "@/lib/active_project";
import {
  setDrawingReturnPath,
  setLastProjectIdForWorkspaceFallback,
  setWorkspaceReturnPath,
} from "@/lib/workspace-return-path";

/**
 * `/objects?projectId=…&drawingId=…` — project from active context; drawing from
 * deep-link `drawingId`, else canonical master from dashboard summary.
 */
function parseNumericParam(value: string | undefined): number | null {
  if (value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const statusConfig: Record<ObjectStatus, { label: string; color: string }> = {
  not_started: { label: "Not Started", color: "bg-foreground/30" },
  pending_shop_drawing: { label: "Pending Shop Drawing", color: "bg-primary/50" },
  shop_drawing_approved: { label: "Shop Drawing Approved", color: "bg-primary" },
  installed: { label: "Installed", color: "bg-primary/70" },
  inspected: { label: "Inspected", color: "bg-primary/80" },
  as_built: { label: "As-Built Complete", color: "bg-primary" },
};

function dashboardHrefForProject(projectId: number | null): string {
  if (projectId == null) return "/";
  return `/?projectId=${projectId}`;
}

export default function Objects({ procoreUserId }: { procoreUserId?: string | null }) {
  const { projectId: activeProjectId, projectName: activeProjectName } =
    useActiveProject();
  const {
    projectId: projectIdFromUrlRaw,
    drawingId: drawingIdFromUrlRaw,
    runId: runIdFromUrlRaw,
    overlayId: overlayIdFromUrlRaw,
    regionId: regionIdFromUrlRaw,
    setProject,
    setDrawing,
    setRun,
    setOverlay,
    setRegion,
  } = useObjectsQueryParams();

  const drawingIdFromUrl = parseNumericParam(drawingIdFromUrlRaw);
  const selectedProjectId = activeProjectId;

  const {
    masterDrawingId: canonicalMasterId,
    name: canonicalMasterName,
    isLoading: canonicalLoading,
  } = useCanonicalMasterDrawing(selectedProjectId);

  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [selectedTool, setSelectedTool] = useState<"select" | "pan" | "zoom">("select");
  const [selectedMasterDrawingId, setSelectedMasterDrawingId] = useState<number | null>(null);
  const [showInspectableAreas, setShowInspectableAreas] = useState(false);
  const [isManagingRegions, setIsManagingRegions] = useState(false);

  /** Sync active project into URL when landing via sidebar (not a picker). */
  useEffect(() => {
    if (activeProjectId == null) return;
    if (projectIdFromUrlRaw != null) return;
    setProject(String(activeProjectId));
  }, [activeProjectId, projectIdFromUrlRaw, setProject]);

  const drawingsQuery = useQuery<ProjectDrawingsResponse>({
    queryKey:
      selectedProjectId != null
        ? projectDrawingsQueryKey(selectedProjectId)
        : ["project-drawings", "disabled"],
    queryFn: () => {
      if (selectedProjectId === null) {
        throw new Error("Missing project selection");
      }
      return fetchProjectDrawings(selectedProjectId);
    },
    enabled: selectedProjectId !== null,
    refetchOnMount: "always",
  });

  const drawingsData = drawingsQuery.data;
  const drawingsLoading = drawingsQuery.isLoading;

  const drawings = drawingsData?.drawings ?? [];

  const masterWorkspaceQuery = useQuery({
    queryKey: [
      "objects-workspace-drawing",
      selectedProjectId,
      selectedMasterDrawingId,
    ] as const,
    queryFn: () =>
      fetchMasterDrawing(selectedProjectId!, selectedMasterDrawingId!),
    enabled:
      selectedProjectId != null &&
      selectedMasterDrawingId != null &&
      selectedProjectId > 0 &&
      selectedMasterDrawingId > 0,
  });

  const { data: objects, isLoading } = useQuery<DrawingObject[]>({
    queryKey: ["/api/objects"],
  });

  const overlayProjectId =
    selectedProjectId != null ? String(selectedProjectId) : null;
  const overlayDrawingId =
    selectedMasterDrawingId != null ? String(selectedMasterDrawingId) : null;

  const selectedInspectionRunId = useMemo(() => {
    return parseNumericParam(runIdFromUrlRaw);
  }, [runIdFromUrlRaw]);

  const {
    data: overlays = [],
    isLoading: overlaysLoading,
    isError: overlaysError,
  } = useDrawingOverlays({
    projectId: overlayProjectId ?? undefined,
    drawingId: overlayDrawingId ?? undefined,
    runId: runIdFromUrlRaw ?? null,
  });
  const overlayRegions = useMemo(() => toOverlayRegions(overlays), [overlays]);

  const regionSummaryQuery = useRegionInspectionSummary({
    projectId: selectedProjectId,
    masterDrawingId: selectedMasterDrawingId,
  });

  const handleSelectInspectionRun = useCallback(
    (runId: number | null) => {
      setRun(runId != null ? String(runId) : null);
    },
    [setRun],
  );

  const handleFocusOverlay = useCallback(
    (overlayId: string | null) => {
      setOverlay(overlayId);
    },
    [setOverlay],
  );

  const handleOverlayClick = useCallback(
    (overlay: DrawingOverlay) => {
      setOverlay(String(overlay.id));
    },
    [setOverlay],
  );

  const handleRegionClick = useCallback(
    (region: RenderableRegion) => {
      setRegion(String(region.entry.regionId));
    },
    [setRegion],
  );

  useEffect(() => {
    if (selectedProjectId === null) {
      setSelectedMasterDrawingId(null);
      return;
    }
    if (canonicalLoading || !drawingsQuery.isSuccess) {
      return;
    }

    const masters = drawingsQuery.data?.drawings ?? [];

    if (drawingIdFromUrl !== null) {
      if (masters.some((m) => m.id === drawingIdFromUrl)) {
        setSelectedMasterDrawingId(drawingIdFromUrl);
        return;
      }
    }

    if (
      canonicalMasterId != null &&
      masters.some((m) => m.id === canonicalMasterId)
    ) {
      setSelectedMasterDrawingId(canonicalMasterId);
      if (drawingIdFromUrl !== canonicalMasterId) {
        setDrawing(String(selectedProjectId), String(canonicalMasterId));
      }
      return;
    }

    setSelectedMasterDrawingId(null);
  }, [
    selectedProjectId,
    canonicalLoading,
    drawingsQuery.isSuccess,
    drawingsQuery.data,
    drawingIdFromUrl,
    canonicalMasterId,
    setDrawing,
  ]);

  const masterDrawingName = useMemo(() => {
    if (selectedMasterDrawingId == null) return null;
    if (selectedMasterDrawingId === canonicalMasterId && canonicalMasterName) {
      return canonicalMasterName;
    }
    const fromList = drawings.find((d) => d.id === selectedMasterDrawingId);
    if (fromList?.name) return fromList.name;
    if (masterWorkspaceQuery.data?.name) return masterWorkspaceQuery.data.name;
    return `Drawing ${selectedMasterDrawingId}`;
  }, [
    selectedMasterDrawingId,
    canonicalMasterId,
    canonicalMasterName,
    drawings,
    masterWorkspaceQuery.data?.name,
  ]);

  /** Keep sidebar Workspace + return path aligned with Objects project / master selection. */
  useEffect(() => {
    if (
      selectedProjectId == null ||
      selectedMasterDrawingId == null ||
      selectedProjectId <= 0 ||
      selectedMasterDrawingId <= 0
    ) {
      return;
    }
    const path = objectsPagePathWithParams({
      projectId: String(selectedProjectId),
      drawingId: String(selectedMasterDrawingId),
      runId: runIdFromUrlRaw,
      overlayId: overlayIdFromUrlRaw,
      regionId: regionIdFromUrlRaw,
    });
    if (overlayIdFromUrlRaw) {
      setWorkspaceReturnPath(path);
    } else {
      setDrawingReturnPath(
        String(selectedProjectId),
        String(selectedMasterDrawingId),
        runIdFromUrlRaw ?? null,
      );
    }
    setLastProjectIdForWorkspaceFallback(selectedProjectId);
  }, [
    selectedProjectId,
    selectedMasterDrawingId,
    runIdFromUrlRaw,
    overlayIdFromUrlRaw,
    regionIdFromUrlRaw,
  ]);

  const SEVERITY_RANK = { low: 1, medium: 2, high: 3, critical: 4 } as const;
  const MISMATCH_THRESHOLD = "high" as const;
  const thresholdRank = SEVERITY_RANK[MISMATCH_THRESHOLD];
  const mismatchCount = overlayRegions.filter((region) => {
    const rank =
      SEVERITY_RANK[region.severity as keyof typeof SEVERITY_RANK] ?? 0;
    return rank >= thresholdRank || region.reviewBadge === "failed";
  }).length;
  const showMismatchBanner = mismatchCount > 0;

  const filteredObjects = objects?.filter((obj) => {
    const matchesSearch = 
      obj.objectId.toLowerCase().includes(searchQuery.toLowerCase()) ||
      obj.objectType.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesStatus = statusFilter === "all" || obj.status === statusFilter;
    
    return matchesSearch && matchesStatus;
  });

  // Group objects by type for statistics
  const objectStats = objects?.reduce((acc, obj) => {
    if (!acc[obj.objectType]) {
      acc[obj.objectType] = { total: 0, byStatus: {} as Record<string, number> };
    }
    acc[obj.objectType].total++;
    acc[obj.objectType].byStatus[obj.status] = (acc[obj.objectType].byStatus[obj.status] || 0) + 1;
    return acc;
  }, {} as Record<string, { total: number; byStatus: Record<string, number> }>);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto" data-testid="objects-page">
      {/* Mismatch Banner: severity >= threshold */}
      {showMismatchBanner && (
        <Alert variant="destructive" className="border-destructive/50">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Drawing Mismatches Detected</AlertTitle>
          <AlertDescription>
            <span>
              {mismatchCount} inspection overlay
              {mismatchCount > 1 ? " regions" : " region"} with severity{" "}
              {MISMATCH_THRESHOLD} or higher (or failed status). Review overlays
              in the inspection runs panel.
            </span>
          </AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" data-testid="text-page-title">
            <Layers className="w-6 h-6 text-muted-foreground" />
            Object Recognition
          </h1>
          <p className="text-muted-foreground">AI-recognized construction objects and their status</p>
          {activeProjectId != null && activeProjectName ? (
            <p className="mt-2 text-sm text-muted-foreground" data-testid="objects-project-header">
              Project:{" "}
              <span className="font-medium text-foreground">{activeProjectName}</span>
              {" · "}
              <Link
                href={dashboardHrefForProject(activeProjectId)}
                className="text-primary hover:underline"
                onClick={() => {
                  replaceDashboardProjectIdInUrl(String(activeProjectId));
                }}
                data-testid="objects-change-project-link"
              >
                Change on Dashboard
              </Link>
            </p>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground" data-testid="objects-no-project">
              No project selected.{" "}
              <Link href="/" className="text-primary hover:underline">
                Choose a project on the Dashboard
              </Link>
              .
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={viewMode === "grid" ? "default" : "outline"}
            size="icon"
            onClick={() => setViewMode("grid")}
            data-testid="button-view-grid"
          >
            <Grid3X3 className="w-4 h-4" />
          </Button>
          <Button
            variant={viewMode === "list" ? "default" : "outline"}
            size="icon"
            onClick={() => setViewMode("list")}
            data-testid="button-view-list"
          >
            <List className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Object Statistics */}
      {objectStats && Object.keys(objectStats).length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-4">
          {Object.entries(objectStats).slice(0, 6).map(([type, stats]) => (
            <Card key={type}>
              <CardContent className="p-4">
                <p className="text-sm font-medium text-muted-foreground capitalize">{type}s</p>
                <p className="text-2xl font-bold">{stats.total}</p>
                <div className="flex items-center gap-1 mt-2">
                  {Object.entries(stats.byStatus).slice(0, 3).map(([status, count]) => (
                    <Tooltip key={status}>
                      <TooltipTrigger asChild>
                        <div 
                          className={`h-1.5 rounded-full ${statusConfig[status as ObjectStatus]?.color || 'bg-foreground/30'}`}
                          style={{ width: `${(count / stats.total) * 100}%`, minWidth: '4px' }}
                        />
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="text-xs">{statusConfig[status as ObjectStatus]?.label}: {count}</p>
                      </TooltipContent>
                    </Tooltip>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Procore Writeback */}
      {selectedProjectId ? (
        <ProcoreWritebackPanel
          projectId={selectedProjectId}
          procoreUserId={procoreUserId ?? null}
          projectName={activeProjectName}
          masterDrawingId={selectedMasterDrawingId}
        />
      ) : (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            <p className="text-sm">
              Choose a project on the{" "}
              <Link href="/" className="text-primary hover:underline">
                Dashboard
              </Link>{" "}
              to write inspection results back to Procore.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Drawing Viewer — master sheet source (master candidates only) */}
      <Card>
        <CardHeader className="space-y-4 pb-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-1">
              <CardTitle className="shrink-0">Drawing Viewer</CardTitle>
              {selectedProjectId != null ? (
                <p
                  className="text-sm text-muted-foreground"
                  data-testid="objects-master-header"
                >
                  Master sheet:{" "}
                  <span className="font-medium text-foreground">
                    {canonicalLoading || drawingsLoading
                      ? "Loading…"
                      : masterDrawingName ??
                        "No canonical master sheet — upload a drawing on the Dashboard first."}
                  </span>
                </p>
              ) : null}
            </div>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:flex-1 sm:justify-end">
              {selectedProjectId != null && selectedMasterDrawingId != null ? (
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <label className="flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      data-testid="show-inspectable-areas-toggle"
                      checked={showInspectableAreas}
                      onChange={(e) => setShowInspectableAreas(e.target.checked)}
                      className="rounded border-border text-primary focus:ring-primary"
                    />
                    Show inspectable areas
                  </label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    data-testid="manage-regions-button"
                    onClick={() => setIsManagingRegions((prev) => !prev)}
                  >
                    {isManagingRegions ? "Back to viewer" : "Manage regions"}
                  </Button>
                </div>
              ) : null}
              <div className="flex items-center gap-1 bg-muted rounded-lg p-1 shrink-0">
                <Button
                  variant={selectedTool === "select" ? "secondary" : "ghost"}
                  size="icon"
                  onClick={() => setSelectedTool("select")}
                  data-testid="tool-select"
                >
                  <MousePointer className="w-4 h-4" />
                </Button>
                <Button
                  variant={selectedTool === "pan" ? "secondary" : "ghost"}
                  size="icon"
                  onClick={() => setSelectedTool("pan")}
                  data-testid="tool-pan"
                >
                  <Move className="w-4 h-4" />
                </Button>
                <Button
                  variant={selectedTool === "zoom" ? "secondary" : "ghost"}
                  size="icon"
                  onClick={() => setSelectedTool("zoom")}
                  data-testid="tool-zoom"
                >
                  <ZoomIn className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div className="flex flex-col gap-2">
              <div className="relative min-h-[480px] overflow-hidden rounded-lg border bg-muted/30">
                {!selectedProjectId ? (
                <div className="flex min-h-[320px] flex-col items-center justify-center gap-2 border-2 border-dashed border-muted-foreground/25 p-8 text-center text-muted-foreground">
                  <Layers className="h-12 w-12 opacity-50" />
                  <p className="font-medium">Drawing canvas</p>
                  <p className="text-sm">
                    Choose a project on the{" "}
                    <Link href="/" className="text-primary hover:underline">
                      Dashboard
                    </Link>{" "}
                    to load a sheet.
                  </p>
                </div>
              ) : !selectedMasterDrawingId ? (
                <div className="flex min-h-[320px] flex-col items-center justify-center gap-2 border-2 border-dashed border-muted-foreground/25 p-8 text-center text-muted-foreground">
                  <Layers className="h-12 w-12 opacity-50" />
                  <p className="font-medium">Drawing canvas</p>
                  <p className="text-sm">
                    No canonical master sheet — upload a drawing on the{" "}
                    <Link href={dashboardHrefForProject(activeProjectId)} className="text-primary hover:underline">
                      Dashboard
                    </Link>{" "}
                    first.
                  </p>
                </div>
              ) : masterWorkspaceQuery.isPending ? (
                <div className="flex min-h-[320px] items-center justify-center gap-2 text-muted-foreground">
                  <Loader2 className="h-8 w-8 animate-spin" />
                  <span className="text-sm">Loading drawing…</span>
                </div>
              ) : masterWorkspaceQuery.isError ? (
                <div className="flex min-h-[320px] flex-col items-center justify-center gap-2 p-6 text-center">
                  <AlertTriangle className="h-8 w-8 text-destructive" />
                  <p className="text-sm font-medium">Could not load drawing</p>
                  <p className="text-sm text-muted-foreground">
                    {masterWorkspaceQuery.error instanceof Error
                      ? masterWorkspaceQuery.error.message
                      : "Check the network tab or try another drawing."}
                  </p>
                </div>
              ) : isManagingRegions && masterWorkspaceQuery.data ? (
                <RegionEditor
                  projectId={selectedProjectId!}
                  masterDrawingId={selectedMasterDrawingId!}
                  imageUrl={apiUrl(masterWorkspaceQuery.data.fileUrl)}
                  pageWidth={masterWorkspaceQuery.data.widthPx ?? 1000}
                  pageHeight={masterWorkspaceQuery.data.heightPx ?? 1000}
                  onClose={() => setIsManagingRegions(false)}
                />
              ) : (
                <DrawingComparisonWorkspace
                  projectId={selectedProjectId}
                  masterDrawing={masterWorkspaceQuery.data ?? null}
                  selectedInspectionRunId={selectedInspectionRunId}
                  overlays={overlays}
                  overlaysLoading={overlaysLoading}
                  focusedOverlayId={overlayIdFromUrlRaw ?? null}
                  onOverlayClick={handleOverlayClick}
                  regionSummary={regionSummaryQuery.data ?? []}
                  showInspectableAreas={showInspectableAreas}
                  onRegionClick={handleRegionClick}
                />
              )}
              </div>

              {regionIdFromUrlRaw ? (
                <p className="text-sm text-muted-foreground" data-testid="objects-focused-region">
                  Focused region: {regionIdFromUrlRaw}
                </p>
              ) : null}

              {overlaysError ? (
                <p className="text-sm text-destructive">
                  Could not load inspection overlays for this drawing. Try refreshing, or check the
                  Inspections tab for upload status.
                </p>
              ) : null}

              {!overlaysLoading &&
              selectedMasterDrawingId != null &&
              overlays.length === 0 &&
              !isManagingRegions ? (
                <p className="text-sm text-muted-foreground">
                  No inspection findings yet for this drawing
                  {selectedInspectionRunId != null ? " on this run" : ""}. Upload an inspection
                  document on the Inspections tab to get started.
                </p>
              ) : null}
            </div>

            {selectedProjectId != null && selectedMasterDrawingId != null && !isManagingRegions ? (
              <aside className="rounded-lg border border-border bg-card p-4 shadow-sm">
                <InspectionRunsPanel
                  projectId={selectedProjectId}
                  masterDrawingId={selectedMasterDrawingId}
                  selectedRunId={selectedInspectionRunId}
                  onSelectRun={handleSelectInspectionRun}
                  overlays={overlays}
                  overlaysLoading={overlaysLoading}
                  focusedOverlayId={overlayIdFromUrlRaw ?? null}
                  onFocusOverlay={handleFocusOverlay}
                />
              </aside>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search by object ID or type..."
                className="pl-9"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="input-search-objects"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-full sm:w-56" data-testid="select-status-filter">
                <Filter className="w-4 h-4 mr-2" />
                <SelectValue placeholder="Filter by status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                {Object.entries(statusConfig).map(([key, config]) => (
                  <SelectItem key={key} value={key}>{config.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Objects List/Grid */}
      {isLoading ? (
        <div className={viewMode === "grid" 
          ? "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
          : "space-y-2"
        }>
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <Skeleton className="h-5 w-32 mb-2" />
                <Skeleton className="h-4 w-24 mb-2" />
                <Skeleton className="h-6 w-28" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filteredObjects && filteredObjects.length > 0 ? (
        viewMode === "grid" ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredObjects.map((obj) => (
              <Card 
                key={obj.id}
                className="cursor-pointer hover-elevate active-elevate-2"
                data-testid={`card-object-${obj.id}`}
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className={`w-3 h-3 rounded-full ${statusConfig[obj.status]?.color}`} />
                    <Badge variant="secondary" className="text-xs capitalize">
                      {obj.objectType}
                    </Badge>
                  </div>
                  
                  <h3 className="font-mono font-semibold">{obj.objectId}</h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    {statusConfig[obj.status]?.label}
                  </p>
                  
                  {Object.keys(obj.metadata).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3">
                      {Object.entries(obj.metadata).slice(0, 2).map(([key, value]) => (
                        <span 
                          key={key}
                          className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground"
                        >
                          {key}: {value}
                        </span>
                      ))}
                    </div>
                  )}
                  
                  <div className="flex items-center gap-2 mt-4 pt-3 border-t">
                    {obj.linkedSubmittalId && (
                      <span className="text-xs text-muted-foreground">
                        Submittal linked
                      </span>
                    )}
                    {obj.linkedInspectionId && (
                      <span className="text-xs text-muted-foreground">
                        Inspection linked
                      </span>
                    )}
                    <Button variant="ghost" size="sm" className="ml-auto">
                      <Eye className="w-4 h-4 mr-1" />
                      View
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="p-0">
              <div className="divide-y">
                {filteredObjects.map((obj) => (
                  <div 
                    key={obj.id}
                    className="flex items-center gap-4 p-4 hover-elevate cursor-pointer"
                    data-testid={`row-object-${obj.id}`}
                  >
                    <div className={`w-3 h-3 rounded-full ${statusConfig[obj.status]?.color}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono font-medium">{obj.objectId}</span>
                        <Badge variant="secondary" className="text-xs capitalize">
                          {obj.objectType}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {statusConfig[obj.status]?.label}
                      </p>
                    </div>
                    <Button variant="ghost" size="icon">
                      <Eye className="w-4 h-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )
      ) : (
        <Card>
          <CardContent className="text-center py-12 text-muted-foreground">
            <Layers className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg font-medium">No objects found</p>
            <p className="text-sm">
              {searchQuery || statusFilter !== "all" 
                ? "Try adjusting your search or filters" 
                : "Upload a drawing for AI to recognize objects"}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Status Legend */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Status Legend</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-4">
            {Object.entries(statusConfig).map(([key, config]) => (
              <div key={key} className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full ${config.color}`} />
                <span className="text-sm text-muted-foreground">{config.label}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
