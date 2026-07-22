import { useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, Loader2 } from "lucide-react";
import type {
  DrawingOverlay,
  EvidenceListResponse,
  InspectionRun,
} from "@shared/schema";

import InspectionRunRow from "@/components/drawing-workspace/inspection_run_row";
import { MatchAlertBanner } from "@/components/drawing-workspace/match_alert_banner";
import { Badge } from "@/components/ui/badge";
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
  useCreateInspectionRun,
  useDeleteInspectionRun,
  useDrawingOverlays,
  useInspectionRuns,
  useRunInspection,
  useUploadInspectionRunEvidence,
} from "@/hooks/use-inspection-runs";
import { toast } from "@/hooks/use-toast";
import { fetchProjectEvidence, projectEvidenceQueryKey } from "@/lib/api/evidence";
import { refreshInspectionWorkspaceQueries } from "@/lib/api/inspection_runs";
import { formatOverlayListItem } from "@/lib/drawing-overlays/overlay_display";
import {
  hasActiveInspectionRun,
  pollWhileInspectionRunsActive,
} from "@/lib/inspection-runs/active_run";

export type InspectionRunsPanelProps = {
  projectId: number;
  masterDrawingId: number;
  selectedRunId?: number | null;
  onSelectRun?: (runId: number | null) => void;
  /** When provided, skips internal overlay fetch (parent owns the query). */
  overlays?: DrawingOverlay[];
  overlaysLoading?: boolean;
  focusedOverlayId?: string | null;
  onFocusOverlay?: (overlayId: string | null) => void;
};

export default function InspectionRunsPanel({
  projectId,
  masterDrawingId,
  selectedRunId = null,
  onSelectRun,
  overlays: overlaysProp,
  overlaysLoading: overlaysLoadingProp,
  focusedOverlayId = null,
  onFocusOverlay,
}: InspectionRunsPanelProps) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const { data: runsData, isLoading: runsLoading, isError: runsError } =
    useInspectionRuns(projectId, { masterDrawingId }, { refetchInterval: pollWhileInspectionRunsActive });

  const runs = runsData?.items ?? [];
  const hasActiveRun = hasActiveInspectionRun(runs);

  const evidenceQuery = useQuery<EvidenceListResponse>({
    queryKey: projectEvidenceQueryKey(projectId),
    queryFn: () => fetchProjectEvidence(projectId),
    enabled: Number.isFinite(projectId) && projectId > 0,
  });

  const evidenceOptions = evidenceQuery.data?.items ?? [];

  const { mutate: runInspection, isPending: runPending } = useRunInspection(
    String(projectId)
  );
  const { mutateAsync: createRun, isPending: createRunPending } =
    useCreateInspectionRun(projectId);
  const { mutateAsync: uploadRunEvidence, isPending: uploadPending } =
    useUploadInspectionRunEvidence(projectId);
  const { mutate: deleteInspectionRun, isPending: deletePending } =
    useDeleteInspectionRun(projectId);

  const uploadBusy = uploadPending || createRunPending;
  const runDisabled = runPending || hasActiveRun || uploadBusy;

  const overlaysControlled = overlaysProp !== undefined;

  const { data: fetchedOverlays = [], isLoading: fetchedOverlaysLoading } =
    useDrawingOverlays({
      projectId: String(projectId),
      drawingId: String(masterDrawingId),
      runId: selectedRunId != null ? String(selectedRunId) : null,
      enabled: !overlaysControlled,
    });

  const overlays = overlaysControlled ? overlaysProp : fetchedOverlays;
  const overlaysLoading = overlaysControlled
    ? (overlaysLoadingProp ?? false)
    : fetchedOverlaysLoading;

  const overlayItems = useMemo(
    () => overlays.map((overlay) => formatOverlayListItem(overlay)),
    [overlays]
  );

  const matchInspectionId = useMemo(() => {
    if (selectedRunId == null) return null;
    const selectedRun = runs.find((run) => run.id === selectedRunId);
    return String(selectedRun?.evidence_id ?? selectedRunId);
  }, [runs, selectedRunId]);

  const evidenceLabelById = useMemo(() => {
    const map = new Map<number, string>();
    for (const record of evidenceOptions) {
      map.set(record.id, record.title?.trim() || `Evidence ${record.id}`);
    }
    return map;
  }, [evidenceOptions]);

  const startInspectionRun = (evidenceId: number | null) => {
    runInspection(
      {
        master_drawing_id: masterDrawingId,
        evidence_id: evidenceId,
      },
      {
        onSuccess: (run: InspectionRun) => {
          toast({
            title: "Inspection started",
            description: `Run #${run.id} is ${run.status}.`,
          });
          onSelectRun?.(run.id);
        },
        onError: (error) => {
          toast({
            title: "Inspection failed",
            description: error.message,
            variant: "destructive",
          });
        },
      }
    );
  };

  const handleRunInspection = () => {
    startInspectionRun(selectedEvidenceId);
  };

  const ensureRunForUpload = async (): Promise<number> => {
    if (selectedRunId != null) {
      return selectedRunId;
    }
    const run = await createRun({
      master_drawing_id: masterDrawingId,
      skip_pipeline: true,
    });
    return run.id;
  };

  const handlePickEvidenceFile = () => {
    fileInputRef.current?.click();
  };

  const handleEvidenceFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (hasActiveRun) {
      toast({
        title: "Upload blocked",
        description: "Wait for the current inspection to finish before uploading.",
        variant: "destructive",
      });
      return;
    }

    setUploadError(null);
    void (async () => {
      try {
        const runId = await ensureRunForUpload();
        const result = await uploadRunEvidence({
          inspectionRunId: runId,
          file,
          masterDrawingId,
        });

        onSelectRun?.(runId);

        const parts = [
          `${result.overlays_created} overlay${result.overlays_created === 1 ? "" : "s"} mapped`,
        ];
        if (result.unresolved_count > 0) {
          parts.push(`${result.unresolved_count} need review`);
        }
        if (result.untagged_region_count > 0) {
          parts.push(`${result.untagged_region_count} untagged region(s) on sheet`);
        }

        toast({
          title: "Evidence processed",
          description: `Run #${runId}: ${parts.join(" · ")}`,
        });
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Failed to upload inspection evidence";
        setUploadError(message);
        void refreshInspectionWorkspaceQueries(
          queryClient,
          projectId,
          masterDrawingId,
        );
        toast({
          title: "Upload failed",
          description: message,
          variant: "destructive",
        });
      }
    })();
  };

  const handleDeleteRun = (runId: number) => {
    deleteInspectionRun(runId, {
      onSuccess: () => {
        if (selectedRunId === runId) {
          onSelectRun?.(null);
        }
        void refreshInspectionWorkspaceQueries(
          queryClient,
          projectId,
          masterDrawingId,
        );
        toast({
          title: "Inspection deleted",
          description: `Run #${runId} and its evidence were removed from the project.`,
        });
      },
      onError: (error) => {
        toast({
          title: "Delete failed",
          description: error.message,
          variant: "destructive",
        });
      },
    });
  };

  return (
    <section
      className="flex flex-col gap-3 border-t border-border pt-4"
      data-testid="inspection-runs-panel"
    >
      <header className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <ClipboardCheck className="h-4 w-4 shrink-0 text-primary" aria-hidden />
          <h3 className="text-sm font-semibold text-foreground">Inspections</h3>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={handleRunInspection}
          disabled={runDisabled}
          data-testid="inspection-runs-run"
        >
          {runPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Running…
            </>
          ) : (
            "Legacy run"
          )}
        </Button>
      </header>

      <div className="space-y-2">
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf,image/*"
          className="hidden"
          data-testid="inspection-run-evidence-file-input"
          aria-label="Upload inspection evidence file"
          onChange={handleEvidenceFileChange}
          disabled={uploadBusy || hasActiveRun}
        />
        <button
          type="button"
          onClick={handlePickEvidenceFile}
          disabled={uploadBusy || hasActiveRun}
          data-testid="inspection-run-evidence-upload"
          className="w-full rounded-md border border-primary bg-background px-3 py-2 text-sm font-medium text-primary hover:bg-primary-soft disabled:opacity-60"
        >
          {uploadBusy ? "Processing evidence…" : "Upload inspection evidence…"}
        </button>
        <p className="text-xs text-muted-foreground">
          Maps the document onto this sheet via the inspection pipeline. Select a run first to
          add another upload to it, or leave unselected to start a new run.
        </p>
        {uploadError ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-800">
            {uploadError}
          </div>
        ) : null}
      </div>

      <div className="grid gap-2">
        <Label htmlFor="inspection-evidence-select" className="text-xs text-muted-foreground">
          Link evidence for legacy run (optional)
        </Label>
        <Select
          value={selectedEvidenceId != null ? String(selectedEvidenceId) : "none"}
          onValueChange={(value) => {
            setSelectedEvidenceId(value === "none" ? null : Number(value));
          }}
          disabled={evidenceQuery.isLoading || runPending}
        >
          <SelectTrigger id="inspection-evidence-select" data-testid="inspection-evidence-select">
            <SelectValue placeholder="No evidence linked" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">No evidence linked</SelectItem>
            {evidenceOptions.map((record) => (
              <SelectItem key={record.id} value={String(record.id)}>
                {record.title?.trim() || `Evidence ${record.id}`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {runsLoading ? (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading inspection runs…
        </div>
      ) : runsError ? (
        <p className="text-sm text-destructive">Could not load inspection runs.</p>
      ) : runs.length === 0 ? (
        <p className="text-sm text-muted-foreground py-2">
          No inspection runs for this sheet yet. Upload evidence to create one.
        </p>
      ) : (
        <ul className="flex max-h-[min(24rem,50vh)] flex-col gap-2 overflow-y-auto pr-1">
          {runs.map((run) => (
            <InspectionRunRow
              key={run.id}
              run={run}
              selected={selectedRunId === run.id}
              onSelect={(runId) => {
                onSelectRun?.(selectedRunId === runId ? null : runId);
              }}
              onDelete={handleDeleteRun}
              deletePending={deletePending}
            />
          ))}
        </ul>
      )}

      {selectedRunId != null ? (
        <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
          {matchInspectionId ? (
            <MatchAlertBanner inspectionId={matchInspectionId} />
          ) : null}
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Overlays on sheet
            </p>
            <span className="text-xs text-muted-foreground">
              {overlaysLoading ? "Loading…" : `${overlays.length} shown`}
            </span>
          </div>
          {overlaysLoading ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              Loading overlays…
            </div>
          ) : overlayItems.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No overlays for run #{selectedRunId} yet. Upload evidence to map findings on the
              drawing.
            </p>
          ) : (
            <ul className="space-y-2" data-testid="inspection-run-overlay-list">
              {overlayItems.map((item, index) => {
                const overlayId = overlays[index]?.id;
                const overlayKey =
                  overlayId != null ? String(overlayId) : String(index);
                const isFocused =
                  focusedOverlayId != null &&
                  overlayId != null &&
                  String(overlayId) === String(focusedOverlayId);

                return (
                  <li key={overlayKey}>
                    <button
                      type="button"
                      className={`w-full rounded border px-2 py-1.5 text-left transition-colors ${
                        isFocused
                          ? "border-primary bg-primary-soft"
                          : "border-border bg-background hover:bg-muted/40"
                      }`}
                      data-testid={`inspection-overlay-item-${overlayKey}`}
                      onClick={() => {
                        if (overlayId == null) return;
                        onFocusOverlay?.(
                          isFocused ? null : String(overlayId),
                        );
                      }}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-foreground">
                            {item.title}
                          </p>
                          <p className="text-xs text-muted-foreground">{item.subtitle}</p>
                        </div>
                        <Badge variant="outline" className="shrink-0 capitalize">
                          {item.status}
                        </Badge>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}

      {selectedRunId != null && evidenceLabelById.size > 0 ? (
        <p className="text-xs text-muted-foreground">
          Selected run #{selectedRunId}
          {runs.find((r) => r.id === selectedRunId)?.evidence_id != null
            ? ` • ${evidenceLabelById.get(
                runs.find((r) => r.id === selectedRunId)!.evidence_id!
              ) ?? "Evidence"}`
            : ""}
        </p>
      ) : null}
    </section>
  );
}
