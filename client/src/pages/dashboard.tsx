import { useQuery } from "@tanstack/react-query";
import { 
  FileCheck, 
  MessageSquareText, 
  ClipboardCheck, 
  AlertTriangle,
  TrendingUp,
  Sparkles,
  Clock,
  CheckCircle
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/stat-card";
import { AIInsightCard } from "@/components/ai-insight-card";
import { ProcoreStatus } from "@/components/procore-status";
import { StatusBadge } from "@/components/status-badge";
import { AIScoreRing } from "@/components/ai-score-ring";
import type { DashboardStats, AIInsight, Submittal, RFI, ProcoreConnection } from "@shared/schema";

interface DashboardProps {
  procoreConnection: ProcoreConnection;
  onProcoreSync?: () => void;
}

export default function Dashboard({ procoreConnection, onProcoreSync }: DashboardProps) {
  const { data: stats, isLoading: statsLoading } = useQuery<DashboardStats>({
    queryKey: ["/api/dashboard/stats"],
  });

  const { data: recentSubmittals, isLoading: submittalsLoading } = useQuery<Submittal[]>({
    queryKey: ["/api/submittals?limit=5"],
  });

  const { data: recentRFIs, isLoading: rfisLoading } = useQuery<RFI[]>({
    queryKey: ["/api/rfis?limit=5"],
  });

  const { data: insights, isLoading: insightsLoading } = useQuery<AIInsight[]>({
    queryKey: ["/api/insights?limit=4"],
  });

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold" data-testid="text-page-title">Dashboard</h1>
          <p className="text-muted-foreground">Quality control overview and AI insights</p>
        </div>
        <ProcoreStatus 
          connection={procoreConnection} 
          onSync={onProcoreSync}
        />
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {statsLoading ? (
          <>
            {[1, 2, 3, 4].map((i) => (
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
              icon={FileCheck}
              variant="warning"
              trend={{ value: 12, label: "vs last week" }}
            />
            <StatCard
              title="Open RFIs"
              value={stats.openRFIs}
              subtitle={`${stats.overdueRFIs} overdue`}
              icon={MessageSquareText}
              variant={stats.overdueRFIs > 0 ? "danger" : "info"}
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

      {/* Recent Activity Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Submittals */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4 pb-4">
            <CardTitle className="flex items-center gap-2">
              <FileCheck className="w-5 h-5 text-muted-foreground" />
              Recent Submittals
            </CardTitle>
            <Button variant="ghost" size="sm" data-testid="button-view-all-submittals">
              View All
            </Button>
          </CardHeader>
          <CardContent>
            {submittalsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center gap-3">
                    <Skeleton className="h-10 w-10 rounded-full" />
                    <div className="flex-1">
                      <Skeleton className="h-4 w-32 mb-1" />
                      <Skeleton className="h-3 w-48" />
                    </div>
                  </div>
                ))}
              </div>
            ) : recentSubmittals && recentSubmittals.length > 0 ? (
              <div className="space-y-3">
                {recentSubmittals.map((submittal) => (
                  <div 
                    key={submittal.id} 
                    className="flex items-center gap-3 p-3 rounded-lg hover-elevate active-elevate-2 cursor-pointer"
                    data-testid={`submittal-row-${submittal.id}`}
                  >
                    <AIScoreRing score={submittal.aiScore || 0} size="sm" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium truncate">{submittal.title}</span>
                        <StatusBadge status={submittal.status} size="sm" />
                      </div>
                      <p className="text-sm text-muted-foreground truncate">
                        <span className="font-mono text-xs">{submittal.number}</span>
                        {" · "}
                        {submittal.specSection}
                      </p>
                    </div>
                    <div className="text-right text-sm text-muted-foreground">
                      <Clock className="w-3.5 h-3.5 inline mr-1" />
                      {new Date(submittal.dueDate).toLocaleDateString()}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <FileCheck className="w-10 h-10 mx-auto mb-3 opacity-50" />
                <p>No submittals yet</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent RFIs */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4 pb-4">
            <CardTitle className="flex items-center gap-2">
              <MessageSquareText className="w-5 h-5 text-muted-foreground" />
              Recent RFIs
            </CardTitle>
            <Button variant="ghost" size="sm" data-testid="button-view-all-rfis">
              View All
            </Button>
          </CardHeader>
          <CardContent>
            {rfisLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center gap-3">
                    <Skeleton className="h-10 w-10 rounded" />
                    <div className="flex-1">
                      <Skeleton className="h-4 w-32 mb-1" />
                      <Skeleton className="h-3 w-48" />
                    </div>
                  </div>
                ))}
              </div>
            ) : recentRFIs && recentRFIs.length > 0 ? (
              <div className="space-y-3">
                {recentRFIs.map((rfi) => (
                  <div 
                    key={rfi.id} 
                    className="flex items-start gap-3 p-3 rounded-lg hover-elevate active-elevate-2 cursor-pointer"
                    data-testid={`rfi-row-${rfi.id}`}
                  >
                    <div className={`p-2 rounded-md ${
                      rfi.status === "overdue" ? "bg-foreground/10" :
                      rfi.status === "open" ? "bg-primary/10" :
                      rfi.status === "answered" ? "bg-primary/10" :
                      "bg-foreground/10"
                    }`}>
                      {rfi.status === "answered" ? (
                        <CheckCircle className={`w-4 h-4 ${
                          rfi.status === "answered" ? "text-primary" : "text-foreground"
                        }`} />
                      ) : rfi.status === "overdue" ? (
                        <AlertTriangle className="w-4 h-4 text-foreground" />
                      ) : (
                        <MessageSquareText className="w-4 h-4 text-primary" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium truncate">{rfi.subject}</span>
                        <StatusBadge status={rfi.status} size="sm" />
                        <StatusBadge status={rfi.priority} size="sm" />
                      </div>
                      <p className="text-sm text-muted-foreground truncate">
                        <span className="font-mono text-xs">{rfi.number}</span>
                        {" · "}
                        Assigned to {rfi.assignedTo}
                      </p>
                    </div>
                    <div className="text-right text-sm text-muted-foreground whitespace-nowrap">
                      <Clock className="w-3.5 h-3.5 inline mr-1" />
                      Due {new Date(rfi.dueDate).toLocaleDateString()}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <MessageSquareText className="w-10 h-10 mx-auto mb-3 opacity-50" />
                <p>No RFIs yet</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

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
