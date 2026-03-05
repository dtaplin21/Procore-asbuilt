"use client";

import { useMemo } from "react";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { DrawingDiffSeverity } from "@shared/schema";

type DiffRegion = {
  page: number;
  type: "rect" | "polygon";
  points: number[][];
  label?: string;
  confidence: number;
};

type DiffItem = {
  id: number;
  alignment_id: number;
  finding_id: number | null;
  summary: string;
  severity: DrawingDiffSeverity;
  diff_regions: DiffRegion[];
  created_at: string;
};

const SEVERITY_STYLES: Record<
  DrawingDiffSeverity,
  { stroke: string; fill: string; badge: string }
> = {
  low: { stroke: "rgb(34 197 94)", fill: "rgba(34 197 94 / 0.15)", badge: "bg-green-500/90" },
  medium: { stroke: "rgb(234 179 8)", fill: "rgba(234 179 8 / 0.15)", badge: "bg-yellow-500/90" },
  high: { stroke: "rgb(249 115 22)", fill: "rgba(249 115 22 / 0.2)", badge: "bg-orange-500/90" },
  critical: { stroke: "rgb(239 68 68)", fill: "rgba(239 68 68 / 0.25)", badge: "bg-red-500/90" },
};

/**
 * Converts normalized (0-1) region points to SVG polygon/rect coordinates.
 * SVG uses viewBox="0 0 1 1" so normalized coords map directly.
 */
function regionToPathData(region: DiffRegion): string {
  const { type, points } = region;
  if (!points || points.length === 0) return "";

  if (type === "rect") {
    // Rect: 4 corners [[x,y],[x+w,y],[x+w,y+h],[x,y+h]] or single [x,y,w,h]
    let pts: [number, number][];
    if (points.length === 1 && points[0].length >= 4) {
      const [x, y, w, h] = points[0];
      pts = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
    } else if (points.length >= 4) {
      pts = points.map((p) => [p[0] ?? 0, p[1] ?? 0] as [number, number]);
    } else {
      return "";
    }
    return pts.map(([x, y]) => `${x},${y}`).join(" ");
  }

  // Polygon: [[x,y],[x,y],...]
  return points.map((p) => `${p[0] ?? 0},${p[1] ?? 0}`).join(" ");
}

interface DrawingDiffOverlayProps {
  diffs: DiffItem[];
  visible: boolean;
  onVisibilityChange: (visible: boolean) => void;
  diffRunning?: boolean;
  diffsLoading?: boolean;
  /** Optional: restrict to specific page (e.g. for multi-page PDFs) */
  page?: number;
}

export function DrawingDiffOverlay({
  diffs,
  visible,
  onVisibilityChange,
  diffRunning = false,
  diffsLoading = false,
  page = 1,
}: DrawingDiffOverlayProps) {
  const regions = useMemo(() => {
    const out: { diff: DiffItem; region: DiffRegion; regionIdx: number }[] = [];
    for (const diff of diffs) {
      (diff.diff_regions ?? []).forEach((region, idx) => {
        if (region.page === page) {
          out.push({ diff, region, regionIdx: idx });
        }
      });
    }
    return out;
  }, [diffs, page]);

  const isLoading = diffRunning || diffsLoading;

  if (isLoading) {
    return (
      <div className="absolute inset-0 flex items-center justify-center bg-background/60">
        <div className="flex items-center gap-2 rounded-lg bg-background/90 px-4 py-3 text-sm text-muted-foreground shadow-md">
          <Loader2 className="h-5 w-5 animate-spin shrink-0" />
          <span>{diffRunning ? "Running diff…" : "Loading diffs…"}</span>
        </div>
      </div>
    );
  }

  if (regions.length === 0) {
    return (
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3 rounded-lg bg-background/90 px-4 py-4 text-center text-sm text-muted-foreground shadow-md max-w-xs">
          {diffs.length === 0 ? (
            <>
              <p className="font-medium">No diffs yet</p>
              <p>
                Select a project and master drawing above, then pick an alignment with status{" "}
                <strong>Complete</strong> and click <strong>Run Diff</strong> in the Developer Panel.
              </p>
            </>
          ) : (
            <p>No diff regions on this page</p>
          )}
          <Button
            size="sm"
            variant={visible ? "secondary" : "ghost"}
            onClick={() => onVisibilityChange(!visible)}
          >
            {visible ? <EyeOff className="w-4 h-4 mr-1" /> : <Eye className="w-4 h-4 mr-1" />}
            {visible ? "Hide" : "Show"} diff overlay
          </Button>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="absolute top-2 right-2 z-10">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="sm"
              variant={visible ? "secondary" : "ghost"}
              onClick={() => onVisibilityChange(!visible)}
            >
              {visible ? <EyeOff className="w-4 h-4 mr-1" /> : <Eye className="w-4 h-4 mr-1" />}
              {visible ? "Hide" : "Show"} diffs
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>Toggle diff region overlays</p>
          </TooltipContent>
        </Tooltip>
      </div>

      {visible && (
        <svg
          className="absolute inset-0 h-full w-full"
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
        >
          {regions.map(({ diff, region, regionIdx }) => {
            const pathData = regionToPathData(region);
            if (!pathData) return null;

            const style = SEVERITY_STYLES[diff.severity] ?? SEVERITY_STYLES.medium;
            const key = `diff-${diff.id}-region-${regionIdx}`;

            return (
              <Tooltip key={key}>
                <TooltipTrigger asChild>
                  <polygon
                    points={pathData}
                    fill={style.fill}
                    stroke={style.stroke}
                    strokeWidth={0.008}
                    strokeLinejoin="round"
                    className="cursor-pointer transition-opacity hover:opacity-100 opacity-90"
                  />
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Badge className={style.badge} variant="secondary">
                        {diff.severity}
                      </Badge>
                      {region.label && (
                        <span className="text-xs text-muted-foreground">{region.label}</span>
                      )}
                    </div>
                    <p className="text-sm">{diff.summary}</p>
                    {diff.finding_id != null && (
                      <p className="text-xs text-muted-foreground">
                        Finding #{diff.finding_id}
                      </p>
                    )}
                  </div>
                </TooltipContent>
              </Tooltip>
            );
          })}
        </svg>
      )}
    </>
  );
}
