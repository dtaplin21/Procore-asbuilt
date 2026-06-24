import { useMemo, useState } from "react";
import { useQuery, type Query } from "@tanstack/react-query";
import { ClipboardCheck, Loader2 } from "lucide-react";
import type {
  EvidenceListResponse,
  EvidenceRecordResponse,
  InspectionRun,
  InspectionRunListResponse,
} from "@shared/schema";

import EvidenceUploadField from "@/components/drawing-workspace/evidence_upload_field";
import InspectionRunRow from "@/components/drawing-workspace/inspection_run_row";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useInspectionRuns, useRunInspection } from "@/hooks/use-inspection-runs";
import { toast } from "@/hooks/use-toast";
import { fetchProjectEvidence, projectEvidenceQueryKey } from "@/lib/api/evidence";

export type InspectionRunsPanelProps = {
  projectId: number;
  masterDrawingId: number;
  selectedRunId?: number | null;
  onSelectRun?: (runId: number | null) => void;
};

const ACTIVE_RUN_STATUSES = new Set(["queued", "processing"]);

function pollWhileRunsActive(
  query: Query<InspectionRunListResponse, Error>
): number | false {
  const items = query.state.data?.items ?? [];
  return items.some((run) => ACTIVE_RUN_STATUSES.has(run.status.toLowerCase()))
    ? 3000
    : false;
}

export default function InspectionRunsPanel({
  projectId,
  masterDrawingId,
  selectedRunId = null,
  onSelectRun,
}: InspectionRunsPanelProps) {
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<number | null>(null);

  const { data: runsData, isLoading: runsLoading, isError: runsError } =
    useInspectionRuns(projectId, { masterDrawingId }, { refetchInterval: pollWhileRunsActive });

  const runs = runsData?.items ?? [];
  const hasActiveRun = runs.some((run) => ACTIVE_RUN_STATUSES.has(run.status.toLowerCase()));

  const evidenceQuery = useQuery<EvidenceListResponse>({
    queryKey: projectEvidenceQueryKey(projectId),
    queryFn: () => fetchProjectEvidence(projectId),
    enabled: Number.isFinite(projectId) && projectId > 0,
  });

  const evidenceOptions = evidenceQuery.data?.items ?? [];

  const { mutate: runInspection, isPending: runPending } = useRunInspection(
    String(projectId)
  );

  const runDisabled = runPending || hasActiveRun;

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

  const handleEvidenceUploaded = async (evidence: EvidenceRecordResponse) => {
    setSelectedEvidenceId(evidence.id);
    toast({
      title: "Evidence uploaded",
      description: evidence.title?.trim() || `Evidence ${evidence.id}`,
    });

    if (hasActiveRun || runPending) {
      toast({
        title: "Inspection not started",
        description: "Wait for the current inspection to finish, then run again.",
      });
      return;
    }

    startInspectionRun(evidence.id);
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
            "Run inspection"
          )}
        </Button>
      </header>

      <EvidenceUploadField
        projectId={projectId}
        onUploaded={handleEvidenceUploaded}
        disabled={runPending}
        uploadOptions={{ type: "inspection_doc" }}
      />

      <div className="grid gap-2">
        <Label htmlFor="inspection-evidence-select" className="text-xs text-muted-foreground">
          Link evidence (optional)
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
          No inspection runs for this sheet yet.
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
            />
          ))}
        </ul>
      )}

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
