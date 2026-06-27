import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "wouter";
import type { DrawingResponse } from "@shared/schema";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  FolderOpen,
  FileStack,
  ClipboardList,
  ShieldCheck,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/stat-card";
import { ProcoreStatus } from "@/components/procore-status";
import type {
  DashboardStats,
  ProcoreConnection,
  DashboardSummary,
  ProjectListResponse,
  JobListResponse,
} from "@shared/schema";
import JobQueueList from "@/components/JobQueueList";
import { buildWorkspaceUrl } from "@/lib/workspace-links";
import { replaceDashboardProjectIdInUrl } from "@/lib/active_project";
import { useActiveProject } from "@/contexts/active_project_context";
import { fetchProjectDashboardSummary } from "@/lib/api/projects";
import { formatInspectionCoverageKpi } from "@/lib/dashboard/inspection-coverage-kpi";
import { resolveFetchUrl } from "@/lib/api/http";
import { UploadDrawingModal } from "@/components/drawing-workspace/UploadDrawingModal";

function readMasterDrawingIdFromSummary(
  summary: DashboardSummary | undefined | null
): number | undefined {
  const mid = summary?.project?.masterDrawingId;
  if (typeof mid === "number" && Number.isFinite(mid)) {
    return mid;
  }
  return undefined;
}

interface DashboardProps {
  procoreConnection: ProcoreConnection;
  /**
   * Procore user id (optional). Passed through to the backend when fetching
   * the project dashboard summary to allow the service to include the active
   * company context for the user.
   */
  procoreUserId?: string;
  onProcoreSync?: () => void;
}

export default function Dashboard({ procoreConnection, procoreUserId, onProcoreSync }: DashboardProps) {
  const [, setLocation] = useLocation();
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const queryClient = useQueryClient();
  const { projectId, projectName: selectedProjectName, setActiveProjectId } =
    useActiveProject();
  const selectedProjectId =
    projectId != null ? String(projectId) : null;

  const { data: stats } = useQuery<DashboardStats>({
    queryKey: ["/api/dashboard/stats"],
  });

  const { data: projectsData, isLoading: projectsLoading } = useQuery<ProjectListResponse>({
    queryKey: ["/api/projects"],
  });

  const projects = projectsData?.items ?? [];

  const {
    data: projectJobs,
    isLoading: jobsLoading,
    error: jobsError,
  } = useQuery<JobListResponse>({
    queryKey: ["projectJobs", selectedProjectId],
    queryFn: async () => {
      if (!selectedProjectId) {
        throw new Error("No project selected");
      }

      const res = await fetch(
        resolveFetchUrl(`/api/projects/${selectedProjectId}/jobs?status=active`),
        { credentials: "include" }
      );

      if (!res.ok) {
        throw new Error("Failed to load project jobs");
      }

      return res.json();
    },
    enabled: !!selectedProjectId,
  });

  const { data: projectSummary, isLoading: projectSummaryLoading } = useQuery<DashboardSummary>({
    queryKey: ["project-dashboard-summary", selectedProjectId, null, procoreUserId ?? null],
    queryFn: () =>
      fetchProjectDashboardSummary(Number(selectedProjectId), {
        userId: procoreUserId ?? undefined,
      }),
    enabled: !!selectedProjectId && Number.isFinite(Number(selectedProjectId)),
  });

  useEffect(() => {
    if (projectsLoading) return;
    if (!projects || projects.length === 0) return;
    if (projectId != null) return;

    const firstId = projects[0].id;
    setActiveProjectId(firstId);
    replaceDashboardProjectIdInUrl(String(firstId));
  }, [projectsLoading, projects, projectId, setActiveProjectId]);

  function handleProjectSelect(nextProjectIdStr: string) {
    const nextProjectId =
      nextProjectIdStr && Number.isFinite(Number(nextProjectIdStr))
        ? Number(nextProjectIdStr)
        : null;
    setActiveProjectId(nextProjectId);
    replaceDashboardProjectIdInUrl(nextProjectIdStr || null);
  }

  const summary = projectSummary;

  const inspectionCoverageKpi = useMemo(
    () => formatInspectionCoverageKpi(projectSummary?.kpis?.inspectionCoverage),
    [projectSummary?.kpis?.inspectionCoverage]
  );

  const handleDashboardUploadSuccess = async (drawing: DrawingResponse) => {
    if (!selectedProjectId) return;
    const pid = Number(selectedProjectId);
    if (!Number.isFinite(pid)) return;
    await queryClient.invalidateQueries({
      queryKey: ["project-dashboard-summary"],
    });
    setLocation(
      buildWorkspaceUrl({ projectId: pid, masterDrawingId: drawing.id })
    );
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold" data-testid="text-page-title">
            Dashboard
          </h1>
          <p className="text-muted-foreground">
            Quality control overview for your project
          </p>
          {selectedProjectName && (
            <div className="text-sm text-muted-foreground mt-1 space-y-1" data-testid="text-selected-project">
              <p>
                Project: <span className="font-medium text-foreground">{selectedProjectName}</span>
              </p>
              {selectedProjectId ? (
                <p>
                  <Link
                    href={`/projects/${selectedProjectId}/drawings/manage`}
                    className="text-primary hover:underline font-normal"
                    data-testid="dashboard-manage-drawings-project-link"
                  >
                    Manage project drawings
                  </Link>
                </p>
              ) : null}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col">
            <label className="text-xs text-muted-foreground">Project</label>
            <select
              className="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground"
              value={selectedProjectId ?? ""}
              onChange={(e) => handleProjectSelect(e.target.value)}
              disabled={projectsLoading || !projects || projects.length === 0}
              data-testid="project-selector"
            >
              {projectsLoading ? (
                <option value="">Loading projects…</option>
              ) : !projects || projects.length === 0 ? (
                <option value="">No projects found</option>
              ) : (
                projects.map((p) => (
                  <option key={String(p.id)} value={String(p.id)}>
                    {p.name}
                  </option>
                ))
              )}
            </select>
          </div>

          {selectedProjectId ? (
            <Button
              type="button"
              className="h-9 px-5"
              onClick={() => setUploadModalOpen(true)}
              data-testid="dashboard-upload-drawing"
            >
              Upload drawing
            </Button>
          ) : null}

          <ProcoreStatus connection={procoreConnection} onSync={onProcoreSync} />
        </div>
      </div>

      {selectedProjectId && (
        projectSummaryLoading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[1, 2, 3, 4].map((i) => (
                <Card key={i}>
                  <CardContent className="p-4">
                    <Skeleton className="h-4 w-20 mb-2" />
                    <Skeleton className="h-7 w-10" />
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                title="Drawings"
                value={projectSummary?.kpis?.drawings_count ?? 0}
                icon={FolderOpen}
                variant="default"
                footer={
                  <Link
                    href={`/projects/${selectedProjectId}/drawings/manage`}
                    className="text-sm font-medium text-primary hover:underline"
                    data-testid="dashboard-manage-drawings-kpi-link"
                  >
                    Manage drawings
                  </Link>
                }
              />
              <StatCard
                title="Inspection coverage"
                value={inspectionCoverageKpi.value}
                subtitle={inspectionCoverageKpi.subtitle}
                icon={ShieldCheck}
                variant="info"
              />
              <StatCard
                title="Evidence"
                value={projectSummary?.kpis?.evidence_count ?? 0}
                icon={FileStack}
                variant="default"
              />
              <StatCard
                title="Inspections"
                value={projectSummary?.kpis?.inspections_count ?? 0}
                icon={ClipboardList}
                variant="default"
              />
            </div>
          </div>
        )
      )}

      <div className="mt-8">
        <h2 className="text-xl font-semibold mb-4">Active Jobs</h2>

        {!selectedProjectId ? (
          <div>Select a project to view active jobs.</div>
        ) : (
          <JobQueueList
            jobs={projectJobs?.jobs ?? []}
            isLoading={jobsLoading}
            error={jobsError ? "Failed to load jobs" : null}
          />
        )}
      </div>

      {stats && stats.criticalAlerts > 0 && (
        <Card className="border-foreground/30 bg-foreground/5">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-full bg-foreground/15">
                <AlertTriangle className="w-5 h-5 text-foreground" />
              </div>
              <div className="flex-1">
                <p className="font-semibold text-foreground">
                  {stats.criticalAlerts} Critical Alert{stats.criticalAlerts > 1 ? "s" : ""}
                </p>
                <p className="text-sm text-muted-foreground">
                  Immediate attention required for compliance issues
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {selectedProjectId && Number.isFinite(Number(selectedProjectId)) ? (
        <UploadDrawingModal
          open={uploadModalOpen}
          onOpenChange={setUploadModalOpen}
          projectId={Number(selectedProjectId)}
          workspaceMasterDrawingId={readMasterDrawingIdFromSummary(summary) ?? null}
          onUploadSuccess={handleDashboardUploadSuccess}
        />
      ) : null}
    </div>
  );
}
