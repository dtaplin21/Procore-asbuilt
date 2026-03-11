import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useInspectionRuns } from "@/hooks/use-inspection-runs";
import { useProcoreWriteback } from "@/hooks/use-procore-writeback";
import { useToast } from "@/hooks/use-toast";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { ProcoreWritebackResponse, ProjectListResponse } from "@shared/schema";
import { AlertTriangle, Loader2, Upload } from "lucide-react";

interface ProcoreWritebackPanelProps {
  projectId: string | null;
  procoreUserId: string | null;
  projectName?: string | null;
  masterDrawingId?: string | null;
  onCommitSuccess?: () => void;
}

function formatCompletedAt(completedAt: string | null): string {
  if (!completedAt) return "—";
  try {
    const d = new Date(completedAt);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

export function ProcoreWritebackPanel({
  projectId,
  procoreUserId,
  projectName,
  masterDrawingId,
  onCommitSuccess,
}: ProcoreWritebackPanelProps) {
  const { toast } = useToast();
  const [selectedInspectionRunId, setSelectedInspectionRunId] = useState<number | null>(null);

  const { data: projectsData } = useQuery<ProjectListResponse>({
    queryKey: ["/api/projects"],
    enabled: !!projectId && !projectName,
  });
  const projects = projectsData?.items ?? [];
  const resolvedProjectName = projectName ?? projects.find((p) => String(p.id) === String(projectId))?.name ?? null;
  const [previewData, setPreviewData] = useState<ProcoreWritebackResponse | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [writebackError, setWritebackError] = useState<string | null>(null);
  const [commitConfirmOpen, setCommitConfirmOpen] = useState(false);

  const masterDrawingIdNum =
    masterDrawingId != null && masterDrawingId !== ""
      ? Number(masterDrawingId)
      : null;

  const { data: runsData, isLoading: runsLoading } = useInspectionRuns(projectId, {
    masterDrawingId: masterDrawingIdNum,
    status: "complete",
  });

  const runs = runsData?.items ?? [];
  const isDisabled = !projectId || !procoreUserId;
  const selectedRun = runs.find((r) => r.id === selectedInspectionRunId);
  const isSelectedRunComplete = selectedRun?.status === "complete";

  const { previewMutation, commitMutation } = useProcoreWriteback({
    projectId,
    procoreUserId,
  });

  const isPreviewDisabled =
    !selectedInspectionRunId || !isSelectedRunComplete || !procoreUserId;
  const isCommitDisabled = !previewData || !isSelectedRunComplete || !selectedInspectionRunId;

  const handlePreview = () => {
    if (!selectedInspectionRunId) return;
    setWritebackError(null);
    previewMutation.mutate(selectedInspectionRunId, {
      onSuccess: (data) => {
        setPreviewData(data);
        setIsPreviewOpen(true);
        setWritebackError(null);
      },
      onError: (err) => setWritebackError(err.message),
    });
  };

  const handleCommitClick = () => {
    setCommitConfirmOpen(true);
  };

  const handleCommitConfirm = () => {
    if (!selectedInspectionRunId) return;
    setWritebackError(null);
    commitMutation.mutate(selectedInspectionRunId, {
      onSuccess: () => {
        setPreviewData(null);
        setIsPreviewOpen(false);
        toast({ title: "Written to Procore successfully" });
        onCommitSuccess?.();
      },
      onError: (err) => setWritebackError(err.message),
      onSettled: () => setCommitConfirmOpen(false),
    });
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Upload className="w-4 h-4" />
          Procore Writeback
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {writebackError && (
          <Alert variant="destructive" className="border-destructive/50">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Writeback error</AlertTitle>
            <AlertDescription>{writebackError}</AlertDescription>
          </Alert>
        )}
        {!procoreUserId && (
          <p className="text-sm text-muted-foreground">
            Connect Procore in{" "}
            <a href="/settings" className="underline hover:no-underline">
              Settings
            </a>{" "}
            to write inspection results back.
          </p>
        )}

        <div className="grid gap-2">
          <Label>Inspection run</Label>
          <Select
            value={selectedInspectionRunId != null ? String(selectedInspectionRunId) : ""}
            onValueChange={(v) =>
              setSelectedInspectionRunId(v ? parseInt(v, 10) : null)
            }
            disabled={isDisabled || runsLoading}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select completed run" />
            </SelectTrigger>
            <SelectContent>
              {runs.map((run) => (
                <SelectItem key={run.id} value={String(run.id)}>
                  Run #{run.id} · {run.inspection_type ?? "—"} · {run.status} ·{" "}
                  {formatCompletedAt(run.completed_at)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {runs.length === 0 && projectId && procoreUserId && !runsLoading && (
            <p className="text-xs text-muted-foreground">
              No completed runs
              {masterDrawingId != null ? " for this drawing" : ""}.
            </p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={isPreviewDisabled || previewMutation.isPending}
            onClick={handlePreview}
          >
            {previewMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                Generating payload...
              </>
            ) : (
              "Preview Procore Writeback"
            )}
          </Button>
          <Button
            variant="default"
            size="sm"
            disabled={isCommitDisabled || commitMutation.isPending}
            onClick={handleCommitClick}
          >
            {commitMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                Sending to Procore...
              </>
            ) : (
              "Commit to Procore"
            )}
          </Button>
        </div>

        <AlertDialog open={commitConfirmOpen} onOpenChange={setCommitConfirmOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Confirm commit</AlertDialogTitle>
              <AlertDialogDescription>
                You are about to write this inspection result to Procore.
                {projectId && selectedInspectionRunId != null && (
                  <>
                    {" "}
                    {resolvedProjectName ? (
                      <>
                        <span className="font-medium">{resolvedProjectName}</span>
                        {" · "}
                      </>
                    ) : null}
                    Run #{selectedInspectionRunId}
                  </>
                )}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={(e) => {
                  e.preventDefault();
                  handleCommitConfirm();
                }}
              >
                Confirm Commit
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  );
}
