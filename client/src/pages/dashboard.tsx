import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "wouter";
import type { InsightListResponse } from "@shared/schema";
import { useQuery } from "@tanstack/react-query";
import { 
  AlertTriangle,
  Sparkles,
  FileText,
  FolderOpen,
  FileStack,
  ClipboardList,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  FindingListResponse,
} from "@shared/schema";
import JobQueueList from "@/components/JobQueueList";
import {
  buildDrawingPickerUrl,
  buildWorkspaceUrlWithFinding,
} from "@/lib/workspace-links";

function getProjectIdFromUrl(): string | null {
  const sp = new URLSearchParams(window.location.search);
  const raw = sp.get("projectId");
  return raw && raw.trim().length > 0 ? raw : null;
}

function setProjectIdInUrl(projectId: string | null) {
  const url = new URL(window.location.href);
  if (projectId) url.searchParams.set("projectId", projectId);
  else url.searchParams.delete("projectId");
  window.history.replaceState({}, "", url.toString());
}

/** Dashboard KPI nested objects may be snake_case or camelCase (FastAPI aliases). */
function readComparisonProgressFromKpis(
  kpis: unknown
): { compared_count: number; total_relevant_count: number; label: string } | null {
  if (!kpis || typeof kpis !== "object") return null;
  const k = kpis as Record<string, unknown>;
  const raw = k.comparison_progress ?? k.comparisonProgress;
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const compared =
    (typeof o.compared_count === "number" ? o.compared_count : undefined) ??
    (typeof o.comparedCount === "number" ? o.comparedCount : undefined);
  const total =
    (typeof o.total_relevant_count === "number" ? o.total_relevant_count : undefined) ??
    (typeof o.totalRelevantCount === "number" ? o.totalRelevantCount : undefined);
  const label = typeof o.label === "string" ? o.label : "";
  if (compared === undefined || total === undefined) return null;
  return { compared_count: compared, total_relevant_count: total, label };
}

function readHighSeverityRiskFromKpis(
  kpis: unknown
): { unresolved_high_severity_count: number; label: string } | null {
  if (!kpis || typeof kpis !== "object") return null;
  const k = kpis as Record<string, unknown>;
  const raw = k.high_severity_diff_risk ?? k.highSeverityDiffRisk;
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const count =
    (typeof o.unresolved_high_severity_count === "number"
      ? o.unresolved_high_severity_count
      : undefined) ??
    (typeof o.unresolvedHighSeverityCount === "number"
      ? o.unresolvedHighSeverityCount
      : undefined);
  const label = typeof o.label === "string" ? o.label : "";
  if (count === undefined) return null;
  return { unresolved_high_severity_count: count, label };
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
  const [location] = useLocation();
  const isInsightsView = location === "/insights";

  // Selected project context (scopes the dashboard structurally)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(() =>
    getProjectIdFromUrl()
  );

  // Kept for Critical Alerts Banner only; top section uses projectSummary
  const { data: stats } = useQuery<DashboardStats>({
    queryKey: ["/api/dashboard/stats"],
  });

  const insightsLimit = isInsightsView ? 100 : 4;

  const { data: insightsPage, isLoading: insightsLoading } = useQuery<InsightListResponse>({
    queryKey: [
      selectedProjectId
        ? `/api/insights?project_id=${encodeURIComponent(selectedProjectId)}&limit=${insightsLimit}`
        : `/api/insights?limit=${insightsLimit}`,
    ],
    enabled: !!selectedProjectId,
  });

  const insights = insightsPage?.items ?? [];
  const insightsPreview = isInsightsView ? insights : insights.slice(0, 3);

  // Projects list for selector (Phase 1 / Step 3)
  const { data: projectsData, isLoading: projectsLoading } = useQuery<ProjectListResponse>({
    queryKey: ["/api/projects"],
  });

  const projects = projectsData?.items ?? [];

  const {
    data: recentFindings,
    isLoading: findingsLoading,
    error: findingsError,
  } = useQuery<FindingListResponse>({
    queryKey: ["projectFindings", selectedProjectId],
    queryFn: async () => {
      if (!selectedProjectId) {
        throw new Error("No project selected");
      }

      const res = await fetch(
        `/api/projects/${selectedProjectId}/findings?limit=5`,
        { credentials: "include" }
      );

      if (!res.ok) {
        throw new Error("Failed to load project findings");
      }

      return res.json();
    },
    enabled: !!selectedProjectId,
  });

  // Project jobs (GET /api/projects/{id}/jobs?status=active)
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
        `/api/projects/${selectedProjectId}/jobs?status=active`,
        { credentials: "include" }
      );

      if (!res.ok) {
        throw new Error("Failed to load project jobs");
      }

      return res.json();
    },
    enabled: !!selectedProjectId,
  });

  // Project-specific summary (Phase 0 change)
  const { data: projectSummary, isLoading: projectSummaryLoading } = useQuery<DashboardSummary>({
    queryKey: [
      selectedProjectId
        ? `/api/projects/${selectedProjectId}/dashboard/summary?user_id=${procoreUserId || ""}`
        : "/api/projects/" // unused but keeps key consistent
    ],
    enabled: !!selectedProjectId,
  });

  // If URL has no projectId, pick a default once projects load
  useEffect(() => {
    if (projectsLoading) return;
    if (!projects || projects.length === 0) return;
    if (selectedProjectId) return;

    const firstId = String(projects[0].id);
    setSelectedProjectId(firstId);
    setProjectIdInUrl(firstId);
  }, [projectsLoading, projects, selectedProjectId]);

  // Whenever selection changes, persist it in the URL
  useEffect(() => {
    setProjectIdInUrl(selectedProjectId);
  }, [selectedProjectId]);

  const selectedProjectName = useMemo(() => {
    if (!projects || !selectedProjectId) return null;
    const p = projects.find((x) => String(x.id) === String(selectedProjectId));
    return p?.name ?? null;
  }, [projects, selectedProjectId]);

  const summary = projectSummary;
  const comparisonProgress = readComparisonProgressFromKpis(summary?.kpis);
  const highSeverityRisk = readHighSeverityRiskFromKpis(summary?.kpis);

  // NOTE (future): when backend supports project-scoped stats/insights, use query params:
  // queryKey: [`/api/dashboard/stats?project_id=${selectedProjectId}`]
  // queryKey: [`/api/insights?limit=4&project_id=${selectedProjectId}`]

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold" data-testid="text-page-title">
            {isInsightsView ? "Insights" : "Dashboard"}
          </h1>
          <p className="text-muted-foreground">
            {isInsightsView
              ? "AI findings and drawing comparison context"
              : "Quality control overview and AI insights"}
          </p>
          {selectedProjectName && (
            <p className="text-sm text-muted-foreground mt-1" data-testid="text-selected-project">
              Project: <span className="font-medium text-foreground">{selectedProjectName}</span>
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {/* Project Selector */}
          <div className="flex flex-col">
            <label className="text-xs text-muted-foreground">Project</label>
            <select
              className="h-9 rounded-md border bg-background px-3 text-sm"
              value={selectedProjectId ?? ""}
              onChange={(e) => setSelectedProjectId(e.target.value)}
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

          {/* Existing Procore status */}
          <ProcoreStatus connection={procoreConnection} onSync={onProcoreSync} />
        </div>
      </div>

      {/* Project summary KPIs (top section) — hide on dedicated insights view */}
      {selectedProjectId && !isInsightsView && (
        projectSummaryLoading ? (
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              {[1, 2].map((i) => (
                <div key={i} className="rounded-lg border p-4">
                  <Skeleton className="h-4 w-32 mb-2" />
                  <Skeleton className="h-8 w-24 mt-2" />
                  <Skeleton className="h-3 w-full max-w-sm mt-2" />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {[1, 2, 3, 4, 5].map((i) => (
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
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border p-4">
                <div className="text-sm text-muted-foreground">Comparison progress</div>
                <div className="mt-2 text-2xl font-semibold">
                  {comparisonProgress
                    ? `${comparisonProgress.compared_count} / ${comparisonProgress.total_relevant_count}`
                    : "—"}
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  {comparisonProgress?.label ?? "Comparison progress unavailable."}
                </div>
              </div>

              <div className="rounded-lg border p-4">
                <div className="text-sm text-muted-foreground">High-severity diff risk</div>
                <div className="mt-2 text-2xl font-semibold">
                  {highSeverityRisk !== null
                    ? highSeverityRisk.unresolved_high_severity_count
                    : "—"}
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  {highSeverityRisk?.label ?? "Risk metric unavailable."}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <StatCard
                title="Total Findings"
                value={projectSummary?.kpis?.total_findings ?? 0}
                icon={FileText}
                variant="default"
              />
              <StatCard
                title="Open Findings"
                value={projectSummary?.kpis?.open_findings ?? 0}
                icon={AlertTriangle}
                variant="warning"
              />
              <StatCard
                title="Drawings"
                value={projectSummary?.kpis?.drawings_count ?? 0}
                icon={FolderOpen}
                variant="default"
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

      {/* AI Insights Section */}
      <div className="space-y-3">
        <div className="flex flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-semibold">
              {isInsightsView ? "All insights" : "AI Insights"}
            </h2>
          </div>
          {!isInsightsView ? (
            <Link href="/insights">
              <Button variant="ghost" size="sm" data-testid="button-view-all-insights">
                View All
              </Button>
            </Link>
          ) : (
            <Link href="/">
              <Button variant="ghost" size="sm" data-testid="button-back-dashboard">
                Back to dashboard
              </Button>
            </Link>
          )}
        </div>
        {insightsLoading ? (
          <div className="space-y-3">
            {(isInsightsView ? [1, 2, 3, 4, 5, 6] : [1, 2, 3]).map((i) => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border bg-white">
            <div className="border-b px-4 py-3">
              <h3 className="text-sm font-semibold text-slate-900">Insights</h3>
            </div>
            <div className="divide-y">
              {insightsPreview.length === 0 ? (
                <div className="px-4 py-6 text-sm text-slate-500">
                  No insights yet for this project.
                </div>
              ) : (
                insightsPreview.map((insight) => {
                  const content = (
                    <div className="px-4 py-3 hover:bg-slate-50">
                      <div className="text-sm font-medium text-slate-900">{insight.title}</div>
                      {insight.description ? (
                        <div className="mt-1 text-sm text-slate-500">{insight.description}</div>
                      ) : null}
                    </div>
                  );
                  const ws = insight.workspaceLink;
                  if (ws) {
                    return (
                      <Link
                        key={insight.id}
                        href={buildWorkspaceUrlWithFinding(ws, insight.id)}
                      >
                        {content}
                      </Link>
                    );
                  }
                  return (
                    <Link
                      key={insight.id}
                      href={buildDrawingPickerUrl(Number(insight.projectId), insight.id)}
                    >
                      {content}
                    </Link>
                  );
                })
              )}
            </div>
          </div>
        )}
      </div>

      {/* Active Jobs */}
      {!isInsightsView && (
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
      )}

      {!isInsightsView && (
      <div className="mt-8">
        <h2 className="text-xl font-semibold mb-4">Bottom: Recent findings</h2>

        {!selectedProjectId ? (
          <div>Select a project to view recent findings.</div>
        ) : findingsLoading ? (
          <div className="text-sm text-muted-foreground">Loading recent findings…</div>
        ) : findingsError ? (
          <div className="text-sm text-destructive">Failed to load recent findings</div>
        ) : (
          <div className="rounded-xl border bg-white">
            <div className="border-b px-4 py-3">
              <h3 className="text-sm font-semibold text-slate-900">Recent Findings</h3>
            </div>
            <div className="divide-y">
              {(recentFindings?.findings ?? []).length === 0 ? (
                <div className="px-4 py-6 text-sm text-slate-500">
                  No recent findings for this project.
                </div>
              ) : (
                (recentFindings?.findings ?? []).map((finding) => {
                  const content = (
                    <div className="px-4 py-3 hover:bg-slate-50">
                      <div className="text-sm font-medium text-slate-900">{finding.title}</div>
                      {finding.severity ? (
                        <div className="mt-1 text-xs text-slate-500">Severity: {finding.severity}</div>
                      ) : null}
                    </div>
                  );
                  const ws = finding.workspaceLink;
                  const href = ws
                    ? buildWorkspaceUrlWithFinding(ws, finding.id)
                    : buildDrawingPickerUrl(finding.projectId, finding.id);
                  return (
                    <Link key={finding.id} href={href}>
                      {content}
                    </Link>
                  );
                })
              )}
            </div>
          </div>
        )}
      </div>
      )}

      {/* Critical Alerts Banner */}
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
              <Link href="/insights">
                <Button variant="destructive" size="sm" data-testid="button-view-alerts">
                  View Alerts
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
