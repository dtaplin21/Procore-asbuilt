import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { 
  ClipboardCheck, 
  AlertTriangle,
  TrendingUp,
  Sparkles,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/stat-card";
import { AIInsightCard } from "@/components/ai-insight-card";
import { ProcoreStatus } from "@/components/procore-status";
import type {
  DashboardStats,
  AIInsight,
  ProcoreConnection,
  DashboardSummary
} from "@shared/schema";

type Project = {
  id: string | number;
  name: string;
};

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
  // Selected project context (scopes the dashboard structurally)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(() =>
    getProjectIdFromUrl()
  );

  const { data: stats, isLoading: statsLoading } = useQuery<DashboardStats>({
    queryKey: ["/api/dashboard/stats"],
  });

  const { data: insights, isLoading: insightsLoading } = useQuery<AIInsight[]>({
    queryKey: [
      selectedProjectId
        ? `/api/insights?project_id=${encodeURIComponent(selectedProjectId)}&limit=4`
        : "/api/insights?limit=4",
    ],
    enabled: !!selectedProjectId,
  });

  // Projects list for selector (Phase 1 / Step 3)
  const { data: projects, isLoading: projectsLoading } = useQuery<Project[]>({
    queryKey: ["/api/projects"],
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

  // NOTE (future): when backend supports project-scoped stats/insights, use query params:
  // queryKey: [`/api/dashboard/stats?project_id=${selectedProjectId}`]
  // queryKey: [`/api/insights?limit=4&project_id=${selectedProjectId}`]

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold" data-testid="text-page-title">Dashboard</h1>
          <p className="text-muted-foreground">Quality control overview and AI insights</p>
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

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {statsLoading ? (
          <>
            {[1, 2, 3].map((i) => (
              <Card key={i}>
                <CardContent className="p-6">
                  <Skeleton className="h-4 w-24 mb-2" />
                  <Skeleton className="h-8 w-16 mb-2" />
                  <Skeleton className="h-4 w-32" />
                </CardContent>
              </Card>
            ))}
          </>
        ) : stats ? (
          <>
            <StatCard
              title="Active Projects"
              value={stats.activeProjects}
              subtitle={`${stats.totalProjects} total projects`}
              icon={TrendingUp}
              variant="default"
            />
            <StatCard
              title="Pending Review"
              value={stats.pendingReview}
              subtitle={`${stats.approvedToday} approved today`}
              icon={ClipboardCheck}
              variant="warning"
              trend={{ value: 12, label: "vs last week" }}
            />
            <StatCard
              title="Pass Rate"
              value={`${stats.passRate}%`}
              subtitle={`${stats.scheduledInspections} scheduled`}
              icon={ClipboardCheck}
              variant="success"
              trend={{ value: 5, label: "improvement" }}
            />
          </>
        ) : null}
      </div>

      {/* AI Insights Section */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4 pb-4">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary" />
            <CardTitle>AI Insights</CardTitle>
          </div>
          <Button variant="ghost" size="sm" data-testid="button-view-all-insights">
            View All
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {insightsLoading ? (
            <>
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-24 w-full" />
              ))}
            </>
          ) : insights && insights.length > 0 ? (
            insights.slice(0, 3).map((insight) => (
              <AIInsightCard 
                key={insight.id} 
                insight={insight}
                onViewDetails={(id) => console.log("View insight:", id)}
                onResolve={(id) => console.log("Resolve insight:", id)}
              />
            ))
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Sparkles className="w-10 h-10 mx-auto mb-3 opacity-50" />
              <p>No AI insights yet</p>
              <p className="text-sm">Insights will appear as documents are analyzed</p>
            </div>
          )}
        </CardContent>
      </Card>


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
              <Button variant="destructive" size="sm" data-testid="button-view-alerts">
                View Alerts
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
