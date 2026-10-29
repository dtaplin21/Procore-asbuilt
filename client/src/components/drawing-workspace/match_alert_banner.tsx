import { useInspectionMatchStatus } from "@/hooks/use_inspection_match_status";

interface Props {
  evidenceId: string;
  drawingId?: string;
  runId?: string | null;
  /** When the inspection run failed (worker/placement), show immediately in dev. */
  runErrorMessage?: string | null;
}

export function MatchAlertBanner({
  evidenceId,
  drawingId,
  runId,
  runErrorMessage,
}: Props) {
  const status = useInspectionMatchStatus(evidenceId, { drawingId, runId });
  const trimmedRunError = runErrorMessage?.trim();

  if (trimmedRunError) {
    return (
      <div
        role="alert"
        data-testid="match-alert-banner"
        className="mb-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      >
        {trimmedRunError}
      </div>
    );
  }

  if (
    !status ||
    status.match_status === "matched" ||
    status.match_status === "needs_review"
  ) {
    return null;
  }

  return (
    <div
      role="alert"
      data-testid="match-alert-banner"
      className="mb-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950"
    >
      {status.match_status === "index_pending"
        ? "Master drawing is still being indexed. Location matching will run automatically when indexing finishes."
        : status.match_status === "insufficient"
          ? status.reason?.trim() || "Placement was insufficient."
          : "No likely location was found on the master drawing for this inspection."}
    </div>
  );
}
