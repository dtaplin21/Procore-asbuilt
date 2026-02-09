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
import type { DashboardStats, AIInsight, ProcoreConnection } from "@shared/schema";

interface DashboardProps {
  procoreConnection: ProcoreConnection;
  onProcoreSync?: () => void;
}

export default function Dashboard({ procoreConnection, onProcoreSync }: DashboardProps) {
  const { data: stats, isLoading: statsLoading } = useQuery<DashboardStats>({
    queryKey: ["/api/dashboard/stats"],
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
