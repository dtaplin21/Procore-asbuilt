import { useLocation, Link } from "wouter";
import { 
  LayoutDashboard, 
  FileCheck, 
  MessageSquareText, 
  ClipboardCheck,
  Layers,
  Settings,
  Cloud
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarFooter,
  SidebarSeparator,
} from "@/components/ui/sidebar";
import { ProcoreStatus } from "@/components/procore-status";
import type { ProcoreConnection } from "@shared/schema";

const mainNavItems = [
  {
    title: "Dashboard",
    url: "/",
    icon: LayoutDashboard,
  },
  {
    title: "Submittals",
    url: "/submittals",
    icon: FileCheck,
  },
  {
    title: "RFIs",
    url: "/rfis",
    icon: MessageSquareText,
  },
  {
    title: "Inspections",
    url: "/inspections",
    icon: ClipboardCheck,
  },
  {
    title: "Objects",
    url: "/objects",
    icon: Layers,
  },
];

const secondaryNavItems = [
  {
    title: "Settings",
    url: "/settings",
    icon: Settings,
  },
];

interface AppSidebarProps {
  procoreConnection: ProcoreConnection;
  onProcoreSync?: () => void;
}

export function AppSidebar({ procoreConnection, onProcoreSync }: AppSidebarProps) {
  const [location] = useLocation();

  return (
    <Sidebar>
      <SidebarHeader className="p-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-md bg-primary">
            <Cloud className="w-5 h-5 text-primary-foreground" />
          </div>
          <div>
            <h1 className="font-bold text-base">QC/QA Platform</h1>
            <p className="text-xs text-muted-foreground">AI-Powered Quality Control</p>
          </div>
        </div>
      </SidebarHeader>
      
      <SidebarSeparator />
      
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {mainNavItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton 
                    asChild 
                    isActive={location === item.url}
                    tooltip={item.title}
                  >
                    <Link href={item.url} data-testid={`nav-${item.title.toLowerCase()}`}>
                      <item.icon className="w-4 h-4" />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        
        <SidebarGroup>
          <SidebarGroupLabel>System</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {secondaryNavItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton 
                    asChild 
                    isActive={location === item.url}
                    tooltip={item.title}
                  >
                    <Link href={item.url} data-testid={`nav-${item.title.toLowerCase()}`}>
                      <item.icon className="w-4 h-4" />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      
      <SidebarFooter className="p-3">
        <div className="rounded-lg border border-sidebar-border p-3 bg-sidebar-accent/30">
          <div className="flex items-center gap-2 mb-2">
            <Cloud className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm font-medium">Procore</span>
          </div>
          <ProcoreStatus 
            connection={procoreConnection} 
            onSync={onProcoreSync}
            compact 
          />
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
