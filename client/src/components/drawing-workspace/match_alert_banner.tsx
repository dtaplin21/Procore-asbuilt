import { useInspectionMatchStatus } from "@/hooks/use_inspection_match_status";

interface Props {
  inspectionId: string;
}

export function MatchAlertBanner({ inspectionId }: Props) {
  const status = useInspectionMatchStatus(inspectionId);

  if (!status || status.match_status === "matched") {
    return null;
  }

  return (
    <div
      role="alert"
      data-testid="match-alert-banner"
      className="mb-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950"
    >
      {status.match_status === "needs_review"
        ? "This inspection could not be automatically placed. Please review and confirm the location on the drawing."
        : "No likely location was found on the master drawing for this inspection."}
    </div>
  );
}
