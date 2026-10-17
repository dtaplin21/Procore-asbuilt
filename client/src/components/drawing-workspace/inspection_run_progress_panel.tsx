import { Loader2 } from "lucide-react";

import type { InspectionRunProgress } from "@/lib/api/inspection_run_progress";
import { cn } from "@/lib/utils";

type Props = {
  progress: InspectionRunProgress | undefined;
  isLoading?: boolean;
};

function stepIcon(status: string): string {
  if (status === "done") return "✓";
  if (status === "running") return "…";
  if (status === "error") return "!";
  return "○";
}

export default function InspectionRunProgressPanel({ progress, isLoading }: Props) {
  if (isLoading && !progress?.current?.label) {
    return (
      <div
        className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground flex items-center gap-2"
        data-testid="inspection-run-progress-panel"
      >
        <Loader2 className="h-4 w-4 animate-spin shrink-0" />
        Loading progress…
      </div>
    );
  }

  if (!progress?.current?.label && !(progress?.steps?.length ?? 0)) {
    return null;
  }

  const currentLabel = progress.current?.label?.trim() ?? "Working…";
  const visionModel = progress.models?.vision_model;
  const ocrBackend = progress.models?.ocr_backend;

  return (
    <div
      className="rounded-md border border-border bg-muted/30 px-3 py-2 space-y-2"
      data-testid="inspection-run-progress-panel"
    >
      <div className="flex items-start gap-2">
        <Loader2 className="h-4 w-4 animate-spin shrink-0 mt-0.5 text-amber-600" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground leading-snug">{currentLabel}</p>
          {(visionModel || ocrBackend) && (
            <p className="text-xs text-muted-foreground mt-0.5">
              {ocrBackend ? `OCR: ${ocrBackend}` : null}
              {ocrBackend && visionModel ? " · " : null}
              {visionModel ? `Vision: ${visionModel}` : null}
            </p>
          )}
          {progress.error ? (
            <p className="text-xs text-destructive mt-1">{progress.error}</p>
          ) : null}
        </div>
      </div>
      {progress.steps && progress.steps.length > 0 ? (
        <ul className="space-y-1 text-xs text-muted-foreground border-t border-border/60 pt-2">
          {progress.steps.map((step) => (
            <li
              key={step.id}
              className={cn(
                "flex items-center gap-2",
                step.status === "running" && "text-foreground font-medium",
                step.status === "error" && "text-destructive",
              )}
            >
              <span aria-hidden className="w-3 text-center shrink-0">
                {stepIcon(step.status)}
              </span>
              <span>{step.label}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
