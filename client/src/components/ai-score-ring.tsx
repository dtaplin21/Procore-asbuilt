import { cn } from "@/lib/utils";

interface AIScoreRingProps {
  score: number;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}

export function AIScoreRing({ score, size = "md", showLabel = true }: AIScoreRingProps) {
  const sizes = {
    sm: { container: "w-10 h-10", stroke: 3, text: "text-xs" },
    md: { container: "w-14 h-14", stroke: 4, text: "text-sm" },
    lg: { container: "w-20 h-20", stroke: 5, text: "text-base" },
  };
  
  const { container, stroke, text } = sizes[size];
  
  const radius = 50 - stroke;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  
  const getColor = (score: number) => {
    if (score >= 90) return "stroke-emerald-500";
    if (score >= 70) return "stroke-amber-500";
    if (score >= 50) return "stroke-orange-500";
    return "stroke-red-500";
  };
  
  return (
    <div className={cn("relative", container)} data-testid="ai-score-ring">
      <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          strokeWidth={stroke}
          className="stroke-muted"
        />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className={cn("transition-all duration-500", getColor(score))}
        />
      </svg>
      {showLabel && (
        <div className={cn("absolute inset-0 flex items-center justify-center font-semibold", text)}>
          {score}
        </div>
      )}
    </div>
  );
}
