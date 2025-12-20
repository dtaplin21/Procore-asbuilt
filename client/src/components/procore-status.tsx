import { RefreshCw, Check, AlertCircle, Cloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ProcoreConnection } from "@shared/schema";

interface ProcoreStatusProps {
  connection: ProcoreConnection;
  onSync?: () => void;
  compact?: boolean;
}

export function ProcoreStatus({ connection, onSync, compact = false }: ProcoreStatusProps) {
  const { connected, lastSyncedAt, syncStatus, projectsLinked, errorMessage } = connection;
  
  const formatLastSync = (date?: string) => {
    if (!date) return "Never";
    const d = new Date(date);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return "Just now";
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return d.toLocaleDateString();
  };
  
  if (compact) {
    return (
      <div 
        className={cn(
          "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm",
          connected 
            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" 
            : "bg-red-500/10 text-red-600 dark:text-red-400"
        )}
        data-testid="procore-status-compact"
      >
        {syncStatus === "syncing" ? (
          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
        ) : connected ? (
          <Check className="w-3.5 h-3.5" />
        ) : (
          <AlertCircle className="w-3.5 h-3.5" />
        )}
        <span className="font-medium">
          {syncStatus === "syncing" ? "Syncing..." : connected ? "Connected" : "Disconnected"}
        </span>
      </div>
    );
  }
  
  return (
    <div className="flex items-center gap-4 p-4 rounded-lg bg-card border border-card-border" data-testid="procore-status">
      <div className={cn(
        "flex items-center justify-center w-12 h-12 rounded-full",
        connected ? "bg-emerald-500/15" : "bg-red-500/15"
      )}>
        <Cloud className={cn(
          "w-6 h-6",
          connected ? "text-emerald-500" : "text-red-500"
        )} />
      </div>
      
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="font-semibold">Procore</span>
          {connected ? (
            <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
              Connected
            </span>
          ) : (
            <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/15 text-red-600 dark:text-red-400">
              Disconnected
            </span>
          )}
        </div>
        <div className="text-sm text-muted-foreground mt-0.5">
          {connected ? (
            <>
              {projectsLinked} projects linked · Last sync: {formatLastSync(lastSyncedAt)}
            </>
          ) : (
            errorMessage || "Connect to sync your projects"
          )}
        </div>
      </div>
      
      {connected && onSync && (
        <Button 
          variant="outline" 
          size="sm"
          onClick={onSync}
          disabled={syncStatus === "syncing"}
          data-testid="button-sync-procore"
        >
          <RefreshCw className={cn("w-4 h-4 mr-2", syncStatus === "syncing" && "animate-spin")} />
          {syncStatus === "syncing" ? "Syncing..." : "Sync Now"}
        </Button>
      )}
    </div>
  );
}
