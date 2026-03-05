import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Wrench, MapPin, Link2, ListOrdered, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";

type Project = { id: string | number; name: string };
type Drawing = { id: number; name?: string };
type Region = { id: number; label: string };
type Alignment = {
  id: number;
  sub_drawing_id: number;
  status: "queued" | "processing" | "complete" | "failed";
  error_message: string | null;
};

const ALIGNMENT_STATUS_CONFIG: Record<
  Alignment["status"],
  { label: string; variant: "default" | "secondary" | "destructive" | "outline" }
> = {
  queued: { label: "Queued", variant: "secondary" },
  processing: { label: "Processing", variant: "outline" },
  complete: { label: "Complete", variant: "default" },
  failed: { label: "Failed", variant: "destructive" },
};

function resolveDrawingName(drawings: Drawing[], id: number): string {
  const d = drawings.find((x) => x.id === id);
  return d?.name || `Drawing ${id}`;
}

async function createRegion(
  projectId: string,
  masterDrawingId: string,
  body: unknown
) {
  const res = await fetch(
    `/api/projects/${projectId}/drawings/${masterDrawingId}/regions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    }
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Failed to create region");
  return data;
}

async function createAlignment(
  projectId: string,
  masterDrawingId: string,
  body: unknown
) {
  const res = await fetch(
    `/api/projects/${projectId}/drawings/${masterDrawingId}/alignments`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    }
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Failed to create alignment");
  return data;
}

async function fetchAlignments(
  projectId: string,
  masterDrawingId: string
): Promise<Alignment[]> {
  const res = await fetch(
    `/api/projects/${projectId}/drawings/${masterDrawingId}/alignments`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error("Failed to fetch alignments");
  return res.json();
}

interface DeveloperPanelProps {
  projectId: string | null;
  masterDrawingId: string | null;
  projects: Project[];
  drawings: Drawing[];
  projectsLoading?: boolean;
  drawingsLoading?: boolean;
  onProjectChange: (id: string | null) => void;
  onDrawingChange: (id: string | null) => void;
}

export function DeveloperPanel({
  projectId,
  masterDrawingId,
  projects,
  drawings,
  projectsLoading,
  drawingsLoading,
  onProjectChange,
  onDrawingChange,
}: DeveloperPanelProps) {
  const queryClient = useQueryClient();

  // Section A
  const [regionLabel, setRegionLabel] = useState("");
  const [regionPage, setRegionPage] = useState(1);
  const [regionRect, setRegionRect] = useState({ x: 0.25, y: 0.4, w: 0.1, h: 0.2 });
  const [regionResponse, setRegionResponse] = useState<string | null>(null);

  const clamp01 = (n: number) => Math.max(0, Math.min(1, Number(n) || 0));

  const regionMutation = useMutation({
    mutationFn: () =>
      createRegion(projectId!, masterDrawingId!, {
        label: regionLabel,
        page: regionPage,
        geometry: {
          type: "rect",
          x: clamp01(regionRect.x),
          y: clamp01(regionRect.y),
          width: clamp01(regionRect.w),
          height: clamp01(regionRect.h),
        },
      }),
    onSuccess: (data) => {
      setRegionResponse(JSON.stringify(data, null, 2));
      queryClient.invalidateQueries({
        queryKey: [`/api/projects/${projectId}/drawings/${masterDrawingId}/regions`],
      });
    },
    onError: (err) => setRegionResponse(JSON.stringify({ error: (err as Error).message }, null, 2)),
  });

  // Section B
  const { data: regions } = useQuery<Region[]>({
    queryKey: [`/api/projects/${projectId}/drawings/${masterDrawingId}/regions`],
    enabled: !!projectId && !!masterDrawingId,
  });
  const [subDrawingId, setSubDrawingId] = useState<string | null>(null);
  const [alignmentRegionId, setAlignmentRegionId] = useState<string | null>(null);
  const [alignmentResponse, setAlignmentResponse] = useState<string | null>(null);

  const subDrawings = drawings?.filter(
    (d) => masterDrawingId && String(d.id) !== String(masterDrawingId)
  ) ?? [];

  const alignmentMutation = useMutation({
    mutationFn: () => {
      const body: { sub_drawing_id: number; region_id?: number; method: string } = {
        sub_drawing_id: parseInt(subDrawingId!, 10),
        method: "manual",
      };
      if (alignmentRegionId) body.region_id = parseInt(alignmentRegionId, 10);
      return createAlignment(projectId!, masterDrawingId!, body);
    },
    onSuccess: (data) => {
      setAlignmentResponse(JSON.stringify(data, null, 2));
      queryClient.invalidateQueries({
        queryKey: [`/api/projects/${projectId}/drawings/${masterDrawingId}/alignments`],
      });
      setSubDrawingId(null);
      setAlignmentRegionId(null);
    },
    onError: (err) => setAlignmentResponse(JSON.stringify({ error: (err as Error).message }, null, 2)),
  });

  // Section C
  const {
    data: alignments,
    isLoading: alignmentsLoading,
    refetch: refetchAlignments,
    isFetching: alignmentsFetching,
  } = useQuery<Alignment[]>({
    queryKey: [`/api/projects/${projectId}/drawings/${masterDrawingId}/alignments`],
    enabled: !!projectId && !!masterDrawingId,
  });

  const canCreateRegion = projectId && masterDrawingId && regionLabel.trim();
  const canCreateAlignment = projectId && masterDrawingId && subDrawingId;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Wrench className="w-4 h-4" />
          Developer Panel <span className="text-xs font-normal text-muted-foreground">(temporary)</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Context: Project + Master Drawing */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="grid gap-2">
            <Label>Project</Label>
            <Select
              value={projectId ?? ""}
              onValueChange={(v) => {
                onProjectChange(v || null);
                onDrawingChange(null);
              }}
              disabled={projectsLoading}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select project" />
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={String(p.id)} value={String(p.id)}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Master Drawing</Label>
            <Select
              value={masterDrawingId ?? ""}
              onValueChange={(v) => onDrawingChange(v || null)}
              disabled={!projectId || drawingsLoading}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select drawing" />
              </SelectTrigger>
              <SelectContent>
                {drawings.map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>
                    {d.name || `Drawing ${d.id}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {(!projectId || !masterDrawingId) && (
          <p className="text-sm text-muted-foreground">Select project and master drawing to continue.</p>
        )}

        {projectId && masterDrawingId && (
          <>
            {/* Section A: Create Region */}
            <div className="space-y-3 rounded-lg border p-4">
              <h4 className="font-medium flex items-center gap-2">
                <MapPin className="w-4 h-4" />
                A. Create Region
              </h4>
              <div className="grid grid-cols-2 gap-2">
                <div className="grid gap-1">
                  <Label className="text-xs">Label</Label>
                  <Input
                    value={regionLabel}
                    onChange={(e) => setRegionLabel(e.target.value)}
                    placeholder="e.g. Level 1"
                  />
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">Page</Label>
                  <Input
                    type="number"
                    min={1}
                    value={regionPage}
                    onChange={(e) => setRegionPage(parseInt(e.target.value, 10) || 1)}
                  />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">x, y, w, h normalized 0–1 (no pixels)</p>
              <div className="grid grid-cols-4 gap-2">
                {(["x", "y", "w", "h"] as const).map((key) => (
                  <div key={key} className="grid gap-1">
                    <Label className="text-xs">{key}</Label>
                    <Input
                      type="number"
                      min={0}
                      max={1}
                      step={0.01}
                      value={regionRect[key]}
                      onChange={(e) =>
                        setRegionRect((r) => ({
                          ...r,
                          [key]: parseFloat(e.target.value) || 0,
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
              <Button
                size="sm"
                onClick={() => regionMutation.mutate()}
                disabled={!canCreateRegion || regionMutation.isPending}
              >
                {regionMutation.isPending ? "Creating…" : "Create Region"}
              </Button>
              {regionResponse && (
                <ScrollArea className="h-24 rounded border bg-muted/50 p-2">
                  <pre className="text-xs font-mono whitespace-pre-wrap break-all">
                    {regionResponse}
                  </pre>
                </ScrollArea>
              )}
            </div>

            {/* Section B: Create Alignment */}
            <div className="space-y-3 rounded-lg border p-4">
              <h4 className="font-medium flex items-center gap-2">
                <Link2 className="w-4 h-4" />
                B. Create Alignment
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="grid gap-1">
                  <Label className="text-xs">Sub Drawing</Label>
                  <Select
                    value={subDrawingId ?? ""}
                    onValueChange={setSubDrawingId}
                    disabled={subDrawings.length === 0}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select sub-drawing" />
                    </SelectTrigger>
                    <SelectContent>
                      {subDrawings.map((d) => (
                        <SelectItem key={d.id} value={String(d.id)}>
                          {d.name || `Drawing ${d.id}`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">Region (optional)</Label>
                  <Select
                    value={alignmentRegionId ?? "none"}
                    onValueChange={(v) => setAlignmentRegionId(v === "none" ? null : v)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="No region" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">No region</SelectItem>
                      {(regions ?? []).map((r) => (
                        <SelectItem key={r.id} value={String(r.id)}>{r.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">Method: manual</p>
              <Button
                size="sm"
                onClick={() => alignmentMutation.mutate()}
                disabled={!canCreateAlignment || alignmentMutation.isPending}
              >
                {alignmentMutation.isPending ? "Attaching…" : "Attach Sub Drawing"}
              </Button>
              {alignmentResponse && (
                <ScrollArea className="h-24 rounded border bg-muted/50 p-2">
                  <pre className="text-xs font-mono whitespace-pre-wrap break-all">
                    {alignmentResponse}
                  </pre>
                </ScrollArea>
              )}
            </div>

            {/* Section C: Alignment Status */}
            <div className="space-y-3 rounded-lg border p-4">
              <h4 className="font-medium flex items-center gap-2">
                <ListOrdered className="w-4 h-4" />
                C. Alignment Status
              </h4>
              <Button
                size="sm"
                variant="outline"
                onClick={() => refetchAlignments()}
                disabled={alignmentsLoading || alignmentsFetching}
              >
                <RefreshCw className={`w-4 h-4 mr-1 ${alignmentsFetching ? "animate-spin" : ""}`} />
                Refresh
              </Button>
              {alignmentsLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : (alignments ?? []).length === 0 ? (
                <p className="text-sm text-muted-foreground">No alignments yet.</p>
              ) : (
                <div className="space-y-2">
                  {(alignments ?? []).map((a) => {
                    const config = ALIGNMENT_STATUS_CONFIG[a.status] ?? {
                      label: a.status,
                      variant: "outline" as const,
                    };
                    return (
                      <div
                        key={a.id}
                        className="flex flex-col gap-1 rounded border p-2 text-sm"
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <span className="font-medium">
                            {resolveDrawingName(drawings, a.sub_drawing_id)}
                          </span>
                          <Badge variant={config.variant}>{config.label}</Badge>
                        </div>
                        {a.status === "failed" && a.error_message && (
                          <p className="text-xs text-destructive">{a.error_message}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
