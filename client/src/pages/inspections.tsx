import { useMemo, useState } from "react";
import { useLocation, Link } from "wouter";
import { useQuery, type Query } from "@tanstack/react-query";
import { ClipboardCheck, Filter, Loader2, Search } from "lucide-react";

import InspectionRunRow from "@/components/drawing-workspace/inspection_run_row";
import InspectionUploadForm from "@/components/inspections/inspection_upload_form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveProject } from "@/contexts/active_project_context";
import { useInspectionRuns } from "@/hooks/use-inspection-runs";
import { replaceDashboardProjectIdInUrl } from "@/lib/active_project";
import { buildObjectsUrlWithRun } from "@/lib/workspace-links";
import {
  setDrawingReturnPath,
  setLastProjectIdForWorkspaceFallback,
} from "@/lib/workspace-return-path";
import type { InspectionRunListResponse } from "@shared/schema";

const ACTIVE_RUN_STATUSES = new Set(["queued", "processing"]);

function pollWhileRunsActive(
  query: Query<InspectionRunListResponse, Error>
): number | false {
  const items = query.state.data?.items ?? [];
  return items.some((run) => ACTIVE_RUN_STATUSES.has(run.status.toLowerCase()))
    ? 3000
    : false;
}

function dashboardHrefForProject(projectId: number | null): string {
  if (projectId == null) return "/";
  return `/?projectId=${projectId}`;
}

export default function Inspections() {
  const [, setLocation] = useLocation();
  const { projectId: selectedProjectId, projectName } = useActiveProject();
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const statusParam =
    statusFilter === "all" ? null : statusFilter;

  const {
    data: runsData,
    isLoading: runsLoading,
    isError: runsError,
  } = useInspectionRuns(
    selectedProjectId,
    { status: statusParam },
    { refetchInterval: pollWhileRunsActive }
  );

  const runs = runsData?.items ?? [];

  const filteredRuns = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return runs;
    return runs.filter((run) => {
      const haystack = [
        String(run.id),
        run.inspection_type ?? "",
        run.status,
        run.evidence_id != null ? String(run.evidence_id) : "",
        run.master_drawing_id != null ? String(run.master_drawing_id) : "",
        run.error_message ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [runs, searchQuery]);

  const openRunOnObjects = (runId: number) => {
    if (selectedProjectId == null) return;
    const run = runs.find((item) => item.id === runId);
    if (!run) return;
    const path = buildObjectsUrlWithRun(
      String(selectedProjectId),
      String(run.master_drawing_id),
      String(runId),
    );
    setDrawingReturnPath(
      String(selectedProjectId),
      String(run.master_drawing_id),
      String(runId),
    );
    setLastProjectIdForWorkspaceFallback(selectedProjectId);
    setLocation(path);
  };

  const handleInspectionUploaded = (result: {
    runId: string;
    masterDrawingId: string;
  }) => {
    if (selectedProjectId == null) return;
    const path = buildObjectsUrlWithRun(
      String(selectedProjectId),
      result.masterDrawingId,
      result.runId,
    );
    setDrawingReturnPath(
      String(selectedProjectId),
      result.masterDrawingId,
      result.runId,
    );
    setLastProjectIdForWorkspaceFallback(selectedProjectId);
    setLocation(path);
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1
            className="flex items-center gap-2 text-2xl font-bold"
            data-testid="text-page-title"
          >
            <ClipboardCheck className="h-6 w-6 text-muted-foreground" />
            Inspections
          </h1>
          <p className="text-muted-foreground">
            Upload inspection documents, then review mapped findings on the Objects drawing
            viewer.
          </p>
          {selectedProjectId != null && projectName ? (
            <p className="mt-2 text-sm text-muted-foreground" data-testid="inspections-project-header">
              Project:{" "}
              <span className="font-medium text-foreground">{projectName}</span>
              {" · "}
              <Link
                href={dashboardHrefForProject(selectedProjectId)}
                className="text-primary hover:underline"
                onClick={() => {
                  if (selectedProjectId != null) {
                    replaceDashboardProjectIdInUrl(String(selectedProjectId));
                  }
                }}
                data-testid="inspections-change-project-link"
              >
                Change on Dashboard
              </Link>
            </p>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground" data-testid="inspections-no-project">
              No project selected.{" "}
              <Link href="/" className="text-primary hover:underline">
                Choose a project on the Dashboard
              </Link>
              .
            </p>
          )}
        </div>
      </div>

      {selectedProjectId != null ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">New inspection upload</CardTitle>
          </CardHeader>
          <CardContent>
            <InspectionUploadForm
              projectId={selectedProjectId}
              onUploaded={handleInspectionUploaded}
            />
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className="grid gap-4 p-4 sm:grid-cols-2">
          <div className="grid gap-2 sm:col-span-1">
            <Label htmlFor="inspections-search">Search</Label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="inspections-search"
                placeholder="Search runs…"
                className="pl-9"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                disabled={selectedProjectId == null}
                data-testid="input-search-inspections"
              />
            </div>
          </div>

          <div className="grid gap-2 sm:col-span-1">
            <Label htmlFor="inspections-status-filter">Status</Label>
            <Select
              value={statusFilter}
              onValueChange={setStatusFilter}
              disabled={selectedProjectId == null}
            >
              <SelectTrigger id="inspections-status-filter" data-testid="select-status-filter">
                <Filter className="mr-2 h-4 w-4" />
                <SelectValue placeholder="Filter by status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="queued">Queued</SelectItem>
                <SelectItem value="processing">Processing</SelectItem>
                <SelectItem value="complete">Complete</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {selectedProjectId == null ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <ClipboardCheck className="mx-auto mb-4 h-12 w-12 opacity-50" />
            <p className="text-lg font-medium">No project selected</p>
            <p className="text-sm">
              Choose a project on the{" "}
              <Link href="/" className="text-primary hover:underline">
                Dashboard
              </Link>{" "}
              to view inspection runs.
            </p>
          </CardContent>
        </Card>
      ) : runsLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-md" />
          ))}
        </div>
      ) : runsError ? (
        <Card>
          <CardContent className="py-8 text-center text-destructive">
            Could not load inspection runs for this project.
          </CardContent>
        </Card>
      ) : filteredRuns.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <ClipboardCheck className="mx-auto mb-4 h-12 w-12 opacity-50" />
            <p className="text-lg font-medium">No inspection runs found</p>
            <p className="text-sm">
              {searchQuery || statusFilter !== "all"
                ? "Try adjusting your search or filters"
                : "Upload an inspection document above to start a run"}
            </p>
          </CardContent>
        </Card>
      ) : (
        <ul className="flex flex-col gap-2">
          {filteredRuns.map((run) => (
            <InspectionRunRow
              key={run.id}
              run={run}
              onSelect={openRunOnObjects}
            />
          ))}
        </ul>
      )}

      {selectedProjectId != null &&
      runs.some((run) => ACTIVE_RUN_STATUSES.has(run.status.toLowerCase())) ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Refreshing while runs are queued or processing…
        </p>
      ) : null}
    </div>
  );
}
