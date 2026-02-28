import { useEffect, useState } from "react";
import { Switch, Route } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/theme-provider";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import Dashboard from "@/pages/dashboard";
import Inspections from "@/pages/inspections";
import Objects from "@/pages/objects";
import SettingsPage from "@/pages/settings";
import NotFound from "@/pages/not-found";
import type { ProcoreConnection } from "@shared/schema";

type ProcoreStatusResponse = {
  connected: boolean;
  last_synced_at: string | null;
  sync_status: "idle" | "syncing" | "error";
  projects_linked: number;
  error_message: string | null;
  active_company_id: number | null;
};

const PROCORE_USER_ID_STORAGE_KEY = "procore_user_id";

function Router({ 
  procoreConnection, 
  onProcoreSync,
  onConnectProcore,
  onDisconnectProcore,
  procoreUserId,
  activeCompanyId,
  onRefreshProcoreStatus,
  onInvalidateCompanyScopedData,
}: { 
  procoreConnection: ProcoreConnection; 
  onProcoreSync: () => void;
  onConnectProcore: () => void;
  onDisconnectProcore: () => void;
  procoreUserId: string | null;
  activeCompanyId: number | null;
  onRefreshProcoreStatus: () => Promise<void>;
  onInvalidateCompanyScopedData: () => void;
}) {
  return (
    <Switch>
      <Route path="/">
        <Dashboard
          procoreConnection={procoreConnection}
          onProcoreSync={onProcoreSync}
          procoreUserId={procoreUserId ?? undefined}
        />
      </Route>
      <Route path="/inspections" component={Inspections} />
      <Route path="/objects" component={Objects} />
      <Route path="/settings">
        <SettingsPage 
          procoreConnection={procoreConnection}
          onConnectProcore={onConnectProcore}
          onDisconnectProcore={onDisconnectProcore}
          userId={procoreUserId}
          activeCompanyId={activeCompanyId}
          onRefreshProcoreStatus={onRefreshProcoreStatus}
          onInvalidateCompanyScopedData={onInvalidateCompanyScopedData}
        />
      </Route>
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  const [procoreConnection, setProcoreConnection] = useState<ProcoreConnection>({
    syncStatus: "idle",
    connected: false,
    projectsLinked: 0,
    errorMessage: "Not connected to Procore",
  });

  const [procoreUserId, setProcoreUserId] = useState<string | null>(null);
  const [activeCompanyId, setActiveCompanyId] = useState<number | null>(null);

  async function loadProcoreStatus(userId: string) {
    const res = await fetch(`/api/procore/status?user_id=${encodeURIComponent(userId)}`, {
      credentials: "include",
    });
    const status = await res.json();

    setProcoreUserId(status.procore_user_id ?? null);
    setActiveCompanyId(status.active_company_id ?? null);
    setProcoreConnection({
      connected: !!status.connected,
      lastSyncedAt: status.last_synced_at ?? undefined,
      syncStatus: status.sync_status ?? "idle",
      projectsLinked: status.projects_linked ?? 0,
      errorMessage: status.error_message ?? undefined,
    });
  }

  useEffect(() => {
    // Prefer URL param (OAuth callback) then fall back to localStorage.
    const sp = new URLSearchParams(window.location.search);
    const fromUrl = sp.get("user_id");
    const fromStorage = window.localStorage.getItem(PROCORE_USER_ID_STORAGE_KEY);
    const userId = (fromUrl || fromStorage || "").trim() || null;

    if (userId) {
      window.localStorage.setItem(PROCORE_USER_ID_STORAGE_KEY, userId);
      setProcoreUserId(userId);
      void loadProcoreStatus(userId);
      return;
    }

    setProcoreUserId(null);
    setActiveCompanyId(null);
    setProcoreConnection({
      connected: false,
      syncStatus: "idle",
      projectsLinked: 0,
      errorMessage: "Not connected to Procore",
    });
  }, []);

  const handleConnectProcore = () => {
    window.location.href = "/api/procore/oauth/authorize";
  };

  const handleDisconnectProcore = async () => {
    if (!procoreUserId) return;

    const qs = new URLSearchParams({ user_id: procoreUserId });
    if (activeCompanyId) qs.set("company_id", String(activeCompanyId));
    await fetch(`/api/procore/disconnect?${qs.toString()}`, {
      method: "POST",
      credentials: "include",
    });

    window.localStorage.removeItem(PROCORE_USER_ID_STORAGE_KEY);
    setProcoreUserId(null);
    setActiveCompanyId(null);
    setProcoreConnection({
      connected: false,
      syncStatus: "idle",
      projectsLinked: 0,
      errorMessage: "Not connected to Procore",
    });
  };

  const handleProcoreSync = async () => {
    if (!procoreUserId) {
      handleConnectProcore();
      return;
    }

    setProcoreConnection((prev) => ({ ...prev, syncStatus: "syncing" }));
    try {
      await fetch(`/api/procore/sync?user_id=${encodeURIComponent(procoreUserId)}`, {
        method: "POST",
        credentials: "include",
      });
      await loadProcoreStatus(procoreUserId);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Sync failed";
      setProcoreConnection((prev) => ({
        ...prev,
        syncStatus: "error",
        errorMessage: msg,
      }));
    }
  };

  const refreshProcoreStatus = async () => {
    if (!procoreUserId) return;
    await loadProcoreStatus(procoreUserId);
  };

  const invalidateCompanyScopedData = () => {
    // Company context influences which local projects should appear.
    // Invalidate active queries so UI refetches immediately.
    queryClient.invalidateQueries({ queryKey: ["/api/projects"] });
  };

  const sidebarStyle = {
    "--sidebar-width": "16rem",
    "--sidebar-width-icon": "3rem",
  };

  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <SidebarProvider style={sidebarStyle as React.CSSProperties}>
            <div className="flex h-screen w-full">
              <AppSidebar 
                procoreConnection={procoreConnection} 
                onProcoreSync={handleProcoreSync}
              />
              <div className="flex flex-col flex-1 min-w-0">
                <header className="flex items-center justify-between gap-4 px-4 h-14 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
                  <SidebarTrigger data-testid="button-sidebar-toggle" />
                </header>
                <main className="flex-1 overflow-auto bg-muted/30">
                  <Router 
                    procoreConnection={procoreConnection}
                    onProcoreSync={handleProcoreSync}
                    onConnectProcore={handleConnectProcore}
                    onDisconnectProcore={handleDisconnectProcore}
                    procoreUserId={procoreUserId}
                    activeCompanyId={activeCompanyId}
                    onRefreshProcoreStatus={refreshProcoreStatus}
                    onInvalidateCompanyScopedData={invalidateCompanyScopedData}
                  />
                </main>
              </div>
            </div>
          </SidebarProvider>
          <Toaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

export default App;
