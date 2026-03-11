import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import type {
  DrawingResponse,
  DrawingRegionResponse,
  DrawingAlignmentCreate,
} from "@shared/schema";

interface AttachSubDrawingFormProps {
  projectId: string | null;
  masterDrawingId: string | null;
  drawings: DrawingResponse[];
  drawingsLoading?: boolean;
}

async function fetchRegions(
  projectId: string,
  masterDrawingId: string
): Promise<DrawingRegionResponse[]> {
  const res = await fetch(
    `/api/projects/${projectId}/drawings/${masterDrawingId}/regions`,
    { credentials: "include" }
  );
  if (!res.ok) throw new Error("Failed to fetch regions");
  return res.json();
}

async function createAlignment(
  projectId: string,
  masterDrawingId: string,
  body: DrawingAlignmentCreate
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
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      typeof err.detail === "string"
        ? err.detail
        : err.detail?.join?.(" ") || res.statusText || "Failed to create alignment"
    );
  }
  return res.json();
}

export function AttachSubDrawingForm({
  projectId,
  masterDrawingId,
  drawings,
  drawingsLoading,
}: AttachSubDrawingFormProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [subDrawingId, setSubDrawingId] = useState<string | null>(null);
  const [regionId, setRegionId] = useState<string | null>(null);
  const method = "manual";

  const { data: regions, isLoading: regionsLoading } = useQuery<DrawingRegionResponse[]>({
    queryKey: [
      `/api/projects/${projectId}/drawings/${masterDrawingId}/regions`,
    ],
    enabled: !!projectId && !!masterDrawingId,
  });

  const subDrawings = drawings?.filter(
    (d) => masterDrawingId && String(d.id) !== String(masterDrawingId)
  ) ?? [];

  const createMutation = useMutation({
    mutationFn: (body: DrawingAlignmentCreate) =>
      createAlignment(projectId!, masterDrawingId!, body),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [
          `/api/projects/${projectId}/drawings/${masterDrawingId}/alignments`,
        ],
      });
      setSubDrawingId(null);
      setRegionId(null);
      toast({ title: "Sub-drawing attached" });
    },
    onError: (err: Error) => {
      toast({
        title: "Failed to attach sub-drawing",
        description: err.message,
        variant: "destructive",
      });
    },
  });

  const canSubmit =
    projectId &&
    masterDrawingId &&
    subDrawingId &&
    subDrawings.some((d) => String(d.id) === subDrawingId);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    const body: DrawingAlignmentCreate = {
      sub_drawing_id: parseInt(subDrawingId!, 10),
      method,
    };
    if (regionId) body.region_id = parseInt(regionId, 10);

    createMutation.mutate(body);
  };

  if (!projectId || !masterDrawingId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Link2 className="w-5 h-5" />
            Attach Sub Drawing
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Select a project and master drawing above to attach a sub-drawing.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Link2 className="w-5 h-5" />
          Attach Sub Drawing (Manual)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="sub-drawing">Sub Drawing</Label>
            <Select
              value={subDrawingId ?? ""}
              onValueChange={setSubDrawingId}
              disabled={drawingsLoading || subDrawings.length === 0}
            >
              <SelectTrigger id="sub-drawing">
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
            {subDrawings.length === 0 && (
              <p className="text-xs text-muted-foreground">
                No other drawings in this project. Upload more drawings first.
              </p>
            )}
          </div>

          <div className="grid gap-2">
            <Label htmlFor="region">Region (optional)</Label>
            <Select
              value={regionId ?? "none"}
              onValueChange={(v) => setRegionId(v === "none" ? null : v)}
              disabled={regionsLoading}
            >
              <SelectTrigger id="region">
                <SelectValue placeholder="No region" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No region</SelectItem>
                {(regions ?? []).map((r) => (
                  <SelectItem key={r.id} value={String(r.id)}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label>Method</Label>
            <Select value={method} disabled>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="manual">Manual</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <Button
            type="submit"
            disabled={!canSubmit || createMutation.isPending}
          >
            {createMutation.isPending ? "Attaching…" : "Attach Sub Drawing"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
