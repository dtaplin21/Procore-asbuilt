import { AlertTriangle, CheckCircle, Info, AlertCircle, Sparkles } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AIInsight } from "@shared/schema";

interface AIInsightCardProps {
  insight: AIInsight;
  onResolve?: (id: string) => void;
  onViewDetails?: (id: string) => void;
}

const typeConfig = {
  compliance: { 
    icon: CheckCircle, 
    label: "Compliance",
    className: "text-primary bg-primary/10"
  },
  deviation: { 
    icon: AlertTriangle, 
    label: "Deviation",
    className: "text-primary bg-primary/10"
  },
  recommendation: { 
    icon: Info, 
    label: "Recommendation",
    className: "text-primary bg-primary/10"
  },
  warning: { 
    icon: AlertCircle, 
    label: "Warning",
    className: "text-foreground bg-foreground/10"
  },
};

const severityConfig = {
  low: { className: "border-l-foreground/40" },
  medium: { className: "border-l-primary/60" },
  high: { className: "border-l-primary" },
  critical: { className: "border-l-foreground" },
};

export function AIInsightCard({ insight, onResolve, onViewDetails }: AIInsightCardProps) {
  const { type, severity, title, description, affectedItems, resolved, createdAt } = insight;
  const { icon: Icon, label, className: typeClassName } = typeConfig[type];
  const { className: severityClassName } = severityConfig[severity];
  
  const formatDate = (date: string) => {
    const d = new Date(date);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };
  
  return (
    <Card 
      className={cn(
        "border-l-4 transition-opacity",
        severityClassName,
        resolved && "opacity-60"
      )}
      data-testid={`ai-insight-card-${insight.id}`}
    >
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <div className={cn("p-2 rounded-md", typeClassName)}>
            <Icon className="w-4 h-4" />
          </div>
          
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={cn(
                "text-xs font-medium px-2 py-0.5 rounded-full",
                typeClassName
              )}>
                {label}
              </span>
              <span className="text-xs text-muted-foreground">
                {formatDate(createdAt)}
              </span>
              {resolved && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-primary/15 text-primary">
                  Resolved
                </span>
              )}
            </div>
            
            <h4 className="font-semibold mt-2 flex items-center gap-2">
              <Sparkles className="w-3.5 h-3.5 text-primary" />
              {title}
            </h4>
            
            <p className="text-sm text-muted-foreground mt-1">{description}</p>
            
            {affectedItems.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {affectedItems.slice(0, 3).map((item, i) => (
                  <span 
                    key={i}
                    className="text-xs font-mono px-2 py-0.5 rounded bg-muted text-muted-foreground"
                  >
                    {item}
                  </span>
                ))}
                {affectedItems.length > 3 && (
                  <span className="text-xs text-muted-foreground">
                    +{affectedItems.length - 3} more
                  </span>
                )}
              </div>
            )}
            
            <div className="flex items-center gap-2 mt-3">
              {onViewDetails && (
                <Button 
                  variant="ghost" 
                  size="sm"
                  onClick={() => onViewDetails(insight.id)}
                  data-testid={`button-view-insight-${insight.id}`}
                >
                  View Details
                </Button>
              )}
              {onResolve && !resolved && (
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => onResolve(insight.id)}
                  data-testid={`button-resolve-insight-${insight.id}`}
                >
                  Mark Resolved
                </Button>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
