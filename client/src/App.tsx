import { useState } from "react";
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

function Router({ 
  procoreConnection, 
  onProcoreSync 
}: { 
  procoreConnection: ProcoreConnection; 
  onProcoreSync: () => void;
}) {
  return (
    <Switch>
      <Route path="/">
        <Dashboard procoreConnection={procoreConnection} onProcoreSync={onProcoreSync} />
      </Route>
      <Route path="/inspections" component={Inspections} />
      <Route path="/objects" component={Objects} />
      <Route path="/settings">
        <SettingsPage 
          procoreConnection={procoreConnection}
          onConnectProcore={onProcoreSync}
          onDisconnectProcore={() => {}}
        />
      </Route>
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  const [procoreConnection, setProcoreConnection] = useState<ProcoreConnection>({
    connected: true,
    lastSyncedAt: new Date().toISOString(),
    syncStatus: "idle",
    projectsLinked: 3,
  });

  const handleProcoreSync = () => {
    setProcoreConnection(prev => ({ ...prev, syncStatus: "syncing" }));
    setTimeout(() => {
      setProcoreConnection(prev => ({
        ...prev,
        syncStatus: "idle",
        lastSyncedAt: new Date().toISOString(),
      }));
    }, 2000);
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
