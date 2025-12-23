import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { SubmittalStatus, RFIStatus, InspectionStatus } from "@shared/schema";

interface StatusBadgeProps {
  status: SubmittalStatus | RFIStatus | InspectionStatus | string;
  size?: "sm" | "default";
}

const statusConfig: Record<string, { label: string; className: string }> = {
  // Submittal statuses
  pending: { label: "Pending", className: "bg-primary/15 text-primary border-primary/30" },
  approved: { label: "Approved", className: "bg-primary/15 text-primary border-primary/30" },
  rejected: { label: "Rejected", className: "bg-foreground/15 text-foreground border-foreground/30" },
  in_review: { label: "In Review", className: "bg-primary/15 text-primary border-primary/30" },
  revise_resubmit: { label: "Revise & Resubmit", className: "bg-primary/15 text-primary border-primary/30" },
  
  // RFI statuses
  open: { label: "Open", className: "bg-primary/15 text-primary border-primary/30" },
  answered: { label: "Answered", className: "bg-primary/15 text-primary border-primary/30" },
  closed: { label: "Closed", className: "bg-foreground/15 text-foreground border-foreground/30" },
  overdue: { label: "Overdue", className: "bg-foreground/15 text-foreground border-foreground/30" },
  
  // Inspection statuses
  scheduled: { label: "Scheduled", className: "bg-primary/15 text-primary border-primary/30" },
  in_progress: { label: "In Progress", className: "bg-primary/15 text-primary border-primary/30" },
  passed: { label: "Passed", className: "bg-primary/15 text-primary border-primary/30" },
  failed: { label: "Failed", className: "bg-foreground/15 text-foreground border-foreground/30" },
  
  // Priority
  low: { label: "Low", className: "bg-foreground/15 text-foreground border-foreground/30" },
  medium: { label: "Medium", className: "bg-primary/15 text-primary border-primary/30" },
  high: { label: "High", className: "bg-primary/15 text-primary border-primary/30" },
  critical: { label: "Critical", className: "bg-foreground/15 text-foreground border-foreground/30" },
};

export function StatusBadge({ status, size = "default" }: StatusBadgeProps) {
  const config = statusConfig[status] || { label: status, className: "bg-foreground/15 text-foreground border-foreground/30" };
  
  return (
    <Badge 
      variant="outline" 
      className={cn(
        "font-medium border",
        config.className,
        size === "sm" && "text-xs px-1.5 py-0"
      )}
      data-testid={`badge-status-${status}`}
    >
      {config.label}
    </Badge>
  );
}
