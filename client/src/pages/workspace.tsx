import { useParams } from "wouter";
import { Link } from "wouter";
import { PenLine } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

/**
 * Drawing workspace route stub.
 * Links from findings use /workspace/:projectId?findingId=:findingId
 */
export default function WorkspaceStub() {
  const params = useParams<{ projectId: string }>();
  const projectId = params?.projectId ?? "";
  const search = typeof window !== "undefined" ? window.location.search : "";
  const findingId = new URLSearchParams(search).get("findingId");

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-lg mx-4">
        <CardContent className="pt-6">
          <div className="flex mb-4 gap-2">
            <PenLine className="h-8 w-8 text-foreground shrink-0" />
            <div>
              <h1 className="text-2xl font-bold text-foreground">Drawing Workspace</h1>
              <p className="text-sm text-muted-foreground mt-1">Route stub — coming soon</p>
            </div>
          </div>

          <p className="text-sm text-muted-foreground mt-4">
            Project: <span className="font-mono">{projectId || "(none)"}</span>
            {findingId && (
              <>
                <br />
                Finding: <span className="font-mono">{findingId}</span>
              </>
            )}
          </p>

          <div className="mt-6 flex gap-2">
            <Link href="/">
              <Button variant="outline">Back to Dashboard</Button>
            </Link>
            <Link href="/objects">
              <Button>Open Objects</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
