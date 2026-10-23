/**
 * Per merge plan: "Extend to show evidence title, 'View on drawing' action."
 * One row in the Inspections page run history list, or a selectable row in
 * the Objects/Workspace inspection runs panel.
 *
 * PR5: history rows also show linked region label (when present) and a
 * "View region" link with ?region= for Objects region focus.
 */

import type { InspectionRun as SchemaInspectionRun } from "@shared/schema";
import { FileSearch, Link2, Loader2, MapPin, Trash2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { evidenceFileDownloadUrl, inspectionRunIndexInventoryUrl } from "@/lib/api/inspections";
import {
  objectsPagePathForRun,
  objectsPagePathWithParams,
} from "@/lib/objectsRoute";
import { cn } from "@/lib/utils";

type RunHistoryFields = {
  evidence_title?: string | null;
  evidence_filename?: string | null;
  overlays_created?: number;
  unresolved_count?: number;
  region_id?: number | null;
  region_label?: string | null;
};

export type InspectionRunRowRun = SchemaInspectionRun & RunHistoryFields;

const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  queued: "Queued",
  processing: "Processing…",
  complete: "Complete",
  indexed: "Indexed",
  failed: "Failed",
};

const ACTIVITY_LABEL: Record<string, string> = {
  indexing: "Indexing linked files…",
  matching: "Matching location on master…",
  investigating: "Investigating linked files…",
  stuck: "Job interrupted…",
};

function formatRunTimestamp(value: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

function statusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  const normalized = status.toLowerCase();
  if (normalized === "complete") return "default";
  if (normalized === "indexed") return "outline";
  if (normalized === "failed") return "destructive";
  if (normalized === "processing" || normalized === "queued") return "secondary";
  return "outline";
}

function statusLabel(status: string, activity?: string | null): string {
  const normalizedActivity = activity?.trim().toLowerCase();
  if (normalizedActivity && ACTIVITY_LABEL[normalizedActivity]) {
    return ACTIVITY_LABEL[normalizedActivity];
  }
  return STATUS_LABEL[status.toLowerCase()] ?? status;
}

function historyTitle(run: InspectionRunRowRun): string {
  return (
    run.evidence_title?.trim() ||
    run.inspection_type?.trim() ||
    `Run #${run.id}`
  );
}

export type InspectionRunHistoryRowProps = {
  run: InspectionRunRowRun;
  projectId: string;
  selected?: never;
  onSelect?: never;
  onDelete?: (runId: number) => void;
  deletePending?: boolean;
  onReindex?: (runId: number) => void;
  onRematch?: (runId: number) => void;
  pipelinePending?: boolean;
  pipelinePendingRunId?: number | null;
  pipelinePendingAction?: "reindex" | "rematch" | null;
};

export type InspectionRunPanelRowProps = {
  run: InspectionRunRowRun;
  projectId?: undefined;
  selected?: boolean;
  onSelect?: (runId: number) => void;
  onDelete?: (runId: number) => void;
  deletePending?: boolean;
  onReindex?: (runId: number) => void;
  onRematch?: (runId: number) => void;
  pipelinePending?: boolean;
  pipelinePendingRunId?: number | null;
  pipelinePendingAction?: "reindex" | "rematch" | null;
};

export type InspectionRunRowProps = InspectionRunPanelRowProps | InspectionRunHistoryRowProps;

function InspectionPipelineButtons({
  runId,
  projectId,
  disabled,
  pending,
  pendingAction,
  onReindex,
  onRematch,
  variant = "history",
}: {
  runId: number;
  projectId?: string;
  disabled?: boolean;
  pending?: boolean;
  pendingAction?: "reindex" | "rematch" | null;
  onReindex?: (runId: number) => void;
  onRematch?: (runId: number) => void;
  variant?: "history" | "panel";
}) {
  if (!onReindex && !onRematch) {
    return null;
  }

  const reindexLabel =
    pending && pendingAction === "reindex" ? "Indexing…" : "Re-index files";
  const rematchLabel =
    pending && pendingAction === "rematch" ? "Placing…" : "Re-run placement";

  const indexInventoryHref =
    projectId != null ? inspectionRunIndexInventoryUrl(projectId, String(runId)) : null;

  if (variant === "panel") {
    return (
      <>
        {indexInventoryHref ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            title="View index inventory (JSON)"
            aria-label="View index inventory"
            data-testid={`inspection-run-index-inventory-${runId}`}
            asChild
          >
            <a href={indexInventoryHref} target="_blank" rel="noreferrer">
              <FileSearch className="h-3.5 w-3.5" />
            </a>
          </Button>
        ) : null}
        {onReindex ? (
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            disabled={disabled || pending}
            title={reindexLabel}
            aria-label={reindexLabel}
            data-testid={`inspection-run-reindex-${runId}`}
            onClick={(event) => {
              event.stopPropagation();
              onReindex(runId);
            }}
          >
            <Link2
              className={`h-3.5 w-3.5 ${pending && pendingAction === "reindex" ? "animate-pulse" : ""}`}
            />
          </Button>
        ) : null}
        {onRematch ? (
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            disabled={disabled || pending}
            title={rematchLabel}
            aria-label={rematchLabel}
            data-testid={`inspection-run-rematch-${runId}`}
            onClick={(event) => {
              event.stopPropagation();
              onRematch(runId);
            }}
          >
            <MapPin
              className={`h-3.5 w-3.5 ${pending && pendingAction === "rematch" ? "animate-pulse" : ""}`}
            />
          </Button>
        ) : null}
      </>
    );
  }

  return (
    <span style={{ display: "flex", gap: 12, alignItems: "center" }}>
      {indexInventoryHref ? (
        <a
          href={indexInventoryHref}
          target="_blank"
          rel="noreferrer"
          data-testid={`inspection-run-index-inventory-${runId}`}
        >
          Index report
        </a>
      ) : null}
      {onReindex ? (
        <button
          type="button"
          className="text-sm text-primary hover:underline disabled:cursor-not-allowed disabled:opacity-50"
          disabled={disabled || pending}
          data-testid={`inspection-run-reindex-${runId}`}
          onClick={() => onReindex(runId)}
        >
          {reindexLabel}
        </button>
      ) : null}
      {onRematch ? (
        <button
          type="button"
          className="text-sm text-primary hover:underline disabled:cursor-not-allowed disabled:opacity-50"
          disabled={disabled || pending}
          data-testid={`inspection-run-rematch-${runId}`}
          onClick={() => onRematch(runId)}
        >
          {rematchLabel}
        </button>
      ) : null}
    </span>
  );
}

function DeleteInspectionRunButton({
  runId,
  runLabel,
  onDelete,
  deletePending = false,
  variant = "history",
}: {
  runId: number;
  runLabel: string;
  onDelete?: (runId: number) => void;
  deletePending?: boolean;
  variant?: "history" | "panel";
}) {
  if (!onDelete) {
    return null;
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          type="button"
          variant={variant === "panel" ? "ghost" : "outline"}
          size="sm"
          disabled={deletePending}
          data-testid={`inspection-run-delete-${runId}`}
          className={
            variant === "panel"
              ? "h-7 shrink-0 px-2 text-destructive hover:text-destructive"
              : "text-destructive hover:text-destructive"
          }
          onClick={(event) => event.stopPropagation()}
        >
          {deletePending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <>
              <Trash2 className="h-4 w-4" />
              {variant === "history" ? <span className="ml-1">Delete</span> : null}
            </>
          )}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete inspection?</AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes {runLabel}, its uploaded evidence file, mapped
            overlays, and related pipeline data from the project. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <Button
            type="button"
            variant="destructive"
            disabled={deletePending}
            onClick={() => onDelete(runId)}
          >
            Delete inspection
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function InspectionRunHistoryRow({
  run,
  projectId,
  onDelete,
  deletePending = false,
  onReindex,
  onRematch,
  pipelinePending = false,
  pipelinePendingRunId = null,
  pipelinePendingAction = null,
}: InspectionRunHistoryRowProps) {
  const masterDrawingId = String(run.master_drawing_id);
  const runId = String(run.id);

  const viewOnDrawingUrl = objectsPagePathForRun({
    projectId,
    masterDrawingId,
    runId,
  });

  const regionId =
    run.region_id != null
      ? String(run.region_id)
      : null;

  const viewRegionUrl = regionId
    ? objectsPagePathWithParams({
        projectId,
        drawingId: masterDrawingId,
        runId,
        regionId,
      })
    : null;

  const evidenceFileId =
    run.evidence_id != null ? String(run.evidence_id) : null;

  return (
    <li
      data-testid="inspection-run-row"
      data-run-id={runId}
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "12px 0",
        borderBottom: "1px solid #E5E7EB",
        gap: 16,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontWeight: 500 }}>{historyTitle(run)}</span>
        <span style={{ fontSize: 13, color: "#6B7280" }}>
          {statusLabel(run.status, run.activity)} · {formatRunTimestamp(run.created_at)}
          {typeof run.overlays_created === "number" && (
            <>
              {" "}
              · {run.overlays_created} finding
              {run.overlays_created === 1 ? "" : "s"} placed
            </>
          )}
          {typeof run.unresolved_count === "number" && run.unresolved_count > 0 && (
            <> · {run.unresolved_count} needs review</>
          )}
          {run.region_label && (
            <>
              {" "}
              · region:{" "}
              <span data-testid="inspection-run-region-label">{run.region_label}</span>
            </>
          )}
        </span>
      </div>

      <div style={{ display: "flex", gap: 12, flexShrink: 0 }}>
        {evidenceFileId && (
          <a
            href={evidenceFileDownloadUrl(projectId, evidenceFileId)}
            target="_blank"
            rel="noreferrer"
            data-testid="evidence-file-link"
          >
            View original file
          </a>
        )}
        {viewRegionUrl && (
          <a href={viewRegionUrl} data-testid="view-region-link">
            View region
          </a>
        )}
        <a href={viewOnDrawingUrl} data-testid="view-on-drawing-link">
          View on drawing
        </a>
        <InspectionPipelineButtons
          runId={run.id}
          projectId={projectId}
          onReindex={onReindex}
          onRematch={onRematch}
          disabled={run.evidence_id == null || run.status === "processing" || run.status === "queued"}
          pending={pipelinePending && pipelinePendingRunId === run.id}
          pendingAction={pipelinePendingAction}
        />
        <DeleteInspectionRunButton
          runId={run.id}
          runLabel={historyTitle(run)}
          onDelete={onDelete}
          deletePending={deletePending}
        />
      </div>
    </li>
  );
}

function InspectionRunPanelRow({
  run,
  selected = false,
  onSelect,
  onDelete,
  deletePending = false,
  onReindex,
  onRematch,
  pipelinePending = false,
  pipelinePendingRunId = null,
  pipelinePendingAction = null,
}: InspectionRunPanelRowProps) {
  const label = run.inspection_type?.trim() || `Run #${run.id}`;
  const timestamp = formatRunTimestamp(run.completed_at ?? run.started_at ?? run.created_at);

  return (
    <li
      className={cn(
        "flex items-stretch gap-1 rounded-md border transition-colors",
        selected
          ? "border-primary bg-primary-soft"
          : "border-border bg-background",
      )}
    >
      <button
        type="button"
        className={cn(
          "min-w-0 flex-1 rounded-md px-3 py-2 text-left hover:bg-muted/60",
          selected ? "bg-transparent" : "bg-background",
        )}
        onClick={() => onSelect?.(run.id)}
        data-testid={`inspection-run-row-${run.id}`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-foreground">{label}</p>
            <p className="text-xs text-muted-foreground">{timestamp}</p>
          </div>
          <Badge variant={statusVariant(run.status)} className="shrink-0 capitalize">
            {statusLabel(run.status, run.activity)}
          </Badge>
        </div>
        {run.evidence_id != null ? (
          <p className="mt-1 text-xs text-muted-foreground">Evidence #{run.evidence_id}</p>
        ) : null}
        {run.error_message ? (
          <p className="mt-1 line-clamp-2 text-xs text-destructive">{run.error_message}</p>
        ) : null}
      </button>
      <div className="flex shrink-0 items-start gap-1 py-2 pr-2">
        <InspectionPipelineButtons
          runId={run.id}
          onReindex={onReindex}
          onRematch={onRematch}
          disabled={run.evidence_id == null || run.status === "processing" || run.status === "queued"}
          pending={pipelinePending && pipelinePendingRunId === run.id}
          pendingAction={pipelinePendingAction}
          variant="panel"
        />
        <DeleteInspectionRunButton
          runId={run.id}
          runLabel={label}
          onDelete={onDelete}
          deletePending={deletePending}
          variant="panel"
        />
      </div>
    </li>
  );
}

export function InspectionRunRow(props: InspectionRunRowProps) {
  if (props.projectId) {
    return (
      <InspectionRunHistoryRow
        run={props.run}
        projectId={props.projectId}
        onDelete={props.onDelete}
        deletePending={props.deletePending}
        onReindex={props.onReindex}
        onRematch={props.onRematch}
        pipelinePending={props.pipelinePending}
        pipelinePendingRunId={props.pipelinePendingRunId}
        pipelinePendingAction={props.pipelinePendingAction}
      />
    );
  }
  return (
    <InspectionRunPanelRow
      run={props.run}
      selected={props.selected}
      onSelect={props.onSelect}
      onDelete={props.onDelete}
      deletePending={props.deletePending}
      onReindex={props.onReindex}
      onRematch={props.onRematch}
      pipelinePending={props.pipelinePending}
      pipelinePendingRunId={props.pipelinePendingRunId}
      pipelinePendingAction={props.pipelinePendingAction}
    />
  );
}

export default InspectionRunRow;
