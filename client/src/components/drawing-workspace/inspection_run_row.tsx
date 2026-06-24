import type { InspectionRun } from "@shared/schema";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

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
  status: string
): "default" | "secondary" | "destructive" | "outline" {
  const normalized = status.toLowerCase();
  if (normalized === "complete") return "default";
  if (normalized === "failed") return "destructive";
  if (normalized === "processing" || normalized === "queued") return "secondary";
  return "outline";
}

export type InspectionRunRowProps = {
  run: InspectionRun;
  selected?: boolean;
  onSelect?: (runId: number) => void;
};

export default function InspectionRunRow({
  run,
  selected = false,
  onSelect,
}: InspectionRunRowProps) {
  const label = run.inspection_type?.trim() || `Run #${run.id}`;
  const timestamp = formatRunTimestamp(run.completed_at ?? run.started_at ?? run.created_at);

  return (
    <li>
      <button
        type="button"
        className={cn(
          "w-full rounded-md border px-3 py-2 text-left transition-colors",
          selected
            ? "border-primary bg-primary-soft"
            : "border-border bg-background hover:bg-muted/60"
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
          <p className="mt-1 text-xs text-muted-foreground">
            Evidence #{run.evidence_id}
          </p>
        ) : null}
        {run.error_message ? (
          <p className="mt-1 text-xs text-destructive line-clamp-2">{run.error_message}</p>
        ) : null}
      </button>
    </li>
  );
}
