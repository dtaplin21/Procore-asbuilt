/**
 * Per merge plan: "Extend to show evidence title, 'View on drawing' action."
 * One row in the Inspections page run history list, or a selectable row in
 * the Objects/Workspace inspection runs panel.
 *
 * PR5: history rows also show linked region label (when present) and a
 * "View region" link with ?region= for Objects region focus.
 */

import type { InspectionRun as SchemaInspectionRun } from "@shared/schema";
import { Loader2, Trash2 } from "lucide-react";

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
import { evidenceFileDownloadUrl } from "@/lib/api/inspections";
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
  failed: "Failed",
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
  if (normalized === "failed") return "destructive";
  if (normalized === "processing" || normalized === "queued") return "secondary";
  return "outline";
}

function statusLabel(status: string): string {
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
};

export type InspectionRunPanelRowProps = {
  run: InspectionRunRowRun;
  projectId?: undefined;
  selected?: boolean;
  onSelect?: (runId: number) => void;
  onDelete?: (runId: number) => void;
  deletePending?: boolean;
};

export type InspectionRunRowProps = InspectionRunPanelRowProps | InspectionRunHistoryRowProps;

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
          {statusLabel(run.status)} · {formatRunTimestamp(run.created_at)}
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
            {run.status}
          </Badge>
        </div>
        {run.evidence_id != null ? (
          <p className="mt-1 text-xs text-muted-foreground">Evidence #{run.evidence_id}</p>
        ) : null}
        {run.error_message ? (
          <p className="mt-1 line-clamp-2 text-xs text-destructive">{run.error_message}</p>
        ) : null}
      </button>
      <div className="flex shrink-0 items-start py-2 pr-2">
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
    />
  );
}

export default InspectionRunRow;
