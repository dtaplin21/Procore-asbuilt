import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
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
import { Label } from "@/components/ui/label";
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
import DrawingViewer from "@/components/drawings/DrawingViewer";
import { ProcoreWritebackPanel } from "@/components/ProcoreWritebackPanel";
import type {
  DrawingObject,
  ObjectStatus,
  ProjectListResponse,
} from "@shared/schema";
import type { ProjectDrawingsResponse, ProjectDrawingCandidate } from "@/types/drawing_workspace";
import { useDrawingOverlays } from "@/hooks/use-inspection-runs";
import { fetchProjectDrawings, projectDrawingsQueryKey } from "@/lib/api/drawings";
import { fetchMasterDrawing } from "@/lib/api/drawing_workspace";
import { toOverlayRegions } from "@/lib/drawing-overlays/inspection_overlay";
import {
  setLastProjectIdForWorkspaceFallback,
  setWorkspaceReturnPath,
} from "@/lib/workspace-return-path";

/**
 * Part 6 (Option A): `/objects?projectId=…&drawingId=…` drives project + master selection.
 * When `drawingId` is missing or invalid, we default to the newest master candidate.
 * GET /drawings list items omit `created_at`; highest numeric `id` approximates latest upload.
 */
function pickNewestMasterId(
  masters: ProjectDrawingCandidate[]
): number | null {
  if (masters.length === 0) return null;
  return masters.reduce((max, d) => (d.id > max ? d.id : max), masters[0].id);
}

const statusConfig: Record<ObjectStatus, { label: string; color: string }> = {
  not_started: { label: "Not Started", color: "bg-foreground/30" },
  pending_shop_drawing: { label: "Pending Shop Drawing", color: "bg-primary/50" },
  shop_drawing_approved: { label: "Shop Drawing Approved", color: "bg-primary" },
  installed: { label: "Installed", color: "bg-primary/70" },
  inspected: { label: "Inspected", color: "bg-primary/80" },
  as_built: { label: "As-Built Complete", color: "bg-primary" },
};

export default function Objects({ procoreUserId }: { procoreUserId?: string | null }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const projectIdFromUrlRaw = searchParams.get("projectId");
  const drawingIdFromUrlRaw = searchParams.get("drawingId");

  const projectIdFromUrl =
    projectIdFromUrlRaw !== null && Number.isFinite(Number(projectIdFromUrlRaw))
      ? Number(projectIdFromUrlRaw)
      : null;

  const drawingIdFromUrl =
    drawingIdFromUrlRaw !== null && Number.isFinite(Number(drawingIdFromUrlRaw))
      ? Number(drawingIdFromUrlRaw)
      : null;

  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [selectedTool, setSelectedTool] = useState<"select" | "pan" | "zoom">("select");
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [selectedMasterDrawingId, setSelectedMasterDrawingId] = useState<number | null>(null);

  useEffect(() => {
    if (projectIdFromUrl !== null) {
      setSelectedProjectId(projectIdFromUrl);
    }
  }, [projectIdFromUrl]);

  function handleProjectChange(nextProjectId: number | null) {
    setSelectedProjectId(nextProjectId);
    setSelectedMasterDrawingId(null);

    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);

      if (nextProjectId === null) {
        next.delete("projectId");
      } else {
        next.set("projectId", String(nextProjectId));
      }

      next.delete("drawingId");
      return next;
    });
  }

  function handleMasterDrawingChange(nextDrawingId: number | null) {
    setSelectedMasterDrawingId(nextDrawingId);

    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);

      if (nextDrawingId === null) {
        next.delete("drawingId");
      } else {
        next.set("drawingId", String(nextDrawingId));
      }

      return next;
    });
  }

  const { data: projectsData, isLoading: projectsLoading } = useQuery<ProjectListResponse>({
    queryKey: ["/api/projects"],
  });

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

  const projects = projectsData?.items ?? [];
  const drawings = drawingsData?.drawings ?? [];

  /** One project + no URL — pick it so the viewer and master auto-default can run. */
  useEffect(() => {
    if (projectIdFromUrl !== null) return;
    if (projectsLoading) return;
    if (projects.length !== 1) return;
    if (selectedProjectId !== null) return;
    const id = projects[0].id;
    setSelectedProjectId(id);
    setSelectedMasterDrawingId(null);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("projectId", String(id));
      next.delete("drawingId");
      return next;
    });
  }, [
    projectIdFromUrl,
    projectsLoading,
    projects,
    selectedProjectId,
    setSearchParams,
  ]);

  const masterDrawingOptions = drawings.filter(
    (drawing) => drawing.uploadIntent === "master" || drawing.uploadIntent == null
  );

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
  const { data: overlays = [] } = useDrawingOverlays(
    overlayProjectId,
    overlayDrawingId
  );
  const overlayRegions = useMemo(() => toOverlayRegions(overlays), [overlays]);

  useEffect(() => {
    if (selectedProjectId === null || !drawingsQuery.isSuccess) {
      return;
    }

    const rowList = drawingsQuery.data?.drawings ?? [];
    const masters = rowList.filter(
      (d) => d.uploadIntent === "master" || d.uploadIntent == null
    );
    if (masters.length === 0) {
      return;
    }

    const newestId = pickNewestMasterId(masters);
    if (newestId === null) return;

    if (drawingIdFromUrl !== null) {
      const exists = masters.some((m) => m.id === drawingIdFromUrl);
      if (exists) {
        if (selectedMasterDrawingId !== drawingIdFromUrl) {
          setSelectedMasterDrawingId(drawingIdFromUrl);
        }
        return;
      }

      setSelectedMasterDrawingId(newestId);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        next.set("drawingId", String(newestId));
        return next;
      });
      return;
    }

    const stateMasterInProject =
      selectedMasterDrawingId !== null &&
      masters.some((m) => m.id === selectedMasterDrawingId);
    if (selectedMasterDrawingId !== null && !stateMasterInProject) {
      setSelectedMasterDrawingId(newestId);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (selectedProjectId !== null) {
          next.set("projectId", String(selectedProjectId));
        }
        next.set("drawingId", String(newestId));
        return next;
      });
      return;
    }

    if (selectedMasterDrawingId === null) {
      setSelectedMasterDrawingId(newestId);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (selectedProjectId !== null) {
          next.set("projectId", String(selectedProjectId));
        }
        next.set("drawingId", String(newestId));
        return next;
      });
    }
  }, [
    selectedProjectId,
    drawingsQuery.isSuccess,
    drawingsQuery.data,
    drawingIdFromUrl,
    selectedMasterDrawingId,
    setSearchParams,
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
    setWorkspaceReturnPath(
      `/projects/${selectedProjectId}/drawings/${selectedMasterDrawingId}/workspace`
    );
    setLastProjectIdForWorkspaceFallback(selectedProjectId);
  }, [selectedProjectId, selectedMasterDrawingId]);

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
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Mismatch Banner: severity >= threshold */}
      {showMismatchBanner && (
        <Alert variant="destructive" className="border-destructive/50">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Drawing Mismatches Detected</AlertTitle>
          <AlertDescription>
            <span>
              {mismatchCount} inspection overlay
              {mismatchCount > 1 ? " regions" : " region"} with severity{" "}
              {MISMATCH_THRESHOLD} or higher (or failed status).
              {" "}
              <Link
                href="/insights"
                className="font-medium underline underline-offset-4 hover:no-underline"
              >
                View insights
              </Link>
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
          projectName={projects.find((p) => p.id === selectedProjectId)?.name ?? null}
          masterDrawingId={selectedMasterDrawingId}
        />
      ) : (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            <p className="text-sm">
              Select a project in the Drawing Viewer to write inspection results back to Procore.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Drawing Viewer — master sheet source (master candidates only) */}
      <Card>
        <CardHeader className="space-y-4 pb-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <CardTitle className="shrink-0">Drawing Viewer</CardTitle>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:flex-1 sm:justify-end">
              <div className="grid gap-2 w-full sm:max-w-xs">
                <Label htmlFor="objects-project">Project</Label>
                <Select
                  value={selectedProjectId != null ? String(selectedProjectId) : ""}
                  onValueChange={(v) => {
                    const id = v ? parseInt(v, 10) : null;
                    handleProjectChange(id);
                  }}
                  disabled={projectsLoading}
                >
                  <SelectTrigger id="objects-project" data-testid="select-objects-project">
                    <SelectValue placeholder="Select project" />
                  </SelectTrigger>
                  <SelectContent>
                    {projects.map((p) => (
                      <SelectItem key={String(p.id)} value={String(p.id)}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2 w-full sm:max-w-xs">
                <Label htmlFor="objects-master-drawing">Master drawing</Label>
                <Select
                  value={selectedMasterDrawingId != null ? String(selectedMasterDrawingId) : ""}
                  onValueChange={(v) => {
                    handleMasterDrawingChange(v ? parseInt(v, 10) : null);
                  }}
                  disabled={!selectedProjectId || drawingsLoading}
                >
                  <SelectTrigger id="objects-master-drawing" data-testid="select-objects-master-drawing">
                    <SelectValue placeholder="Select master drawing" />
                  </SelectTrigger>
                  <SelectContent>
                    {masterDrawingOptions.map((drawing) => (
                      <SelectItem key={drawing.id} value={String(drawing.id)}>
                        {drawing.name || `Drawing ${drawing.id}`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
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
          <div className="relative min-h-[480px] overflow-hidden rounded-lg border bg-muted/30">
            {!selectedProjectId || !selectedMasterDrawingId ? (
              <div className="flex min-h-[320px] flex-col items-center justify-center gap-2 border-2 border-dashed border-muted-foreground/25 p-8 text-center text-muted-foreground">
                <Layers className="h-12 w-12 opacity-50" />
                <p className="font-medium">Drawing canvas</p>
                <p className="text-sm">Select a project and master drawing to load the sheet.</p>
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
            ) : (
              <DrawingViewer
                projectId={selectedProjectId}
                drawing={masterWorkspaceQuery.data ?? null}
              />
            )}
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
