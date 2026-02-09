import { useState } from "react";
import { 
  Settings, 
  User, 
  Cloud, 
  Bell, 
  Webhook,
  ExternalLink,
  Check
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import type { ProcoreConnection } from "@shared/schema";

interface SettingsProps {
  procoreConnection: ProcoreConnection;
  onConnectProcore?: () => void;
  onDisconnectProcore?: () => void;
}

export default function SettingsPage({ procoreConnection, onConnectProcore, onDisconnectProcore }: SettingsProps) {
  const [notifications, setNotifications] = useState({
    emailInspections: true,
    pushAlerts: true,
    aiInsights: true,
  });

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2" data-testid="text-page-title">
          <Settings className="w-6 h-6 text-muted-foreground" />
          Settings
        </h1>
        <p className="text-muted-foreground">Manage your account and platform preferences</p>
      </div>

      <Tabs defaultValue="general" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="general" data-testid="tab-general">General</TabsTrigger>
          <TabsTrigger value="integrations" data-testid="tab-integrations">Integrations</TabsTrigger>
          <TabsTrigger value="notifications" data-testid="tab-notifications">Notifications</TabsTrigger>
        </TabsList>

        {/* General Settings */}
        <TabsContent value="general" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <User className="w-5 h-5" />
                Profile
              </CardTitle>
              <CardDescription>Your personal information and preferences</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="firstName">First Name</Label>
                  <Input id="firstName" placeholder="John" data-testid="input-first-name" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="lastName">Last Name</Label>
                  <Input id="lastName" placeholder="Smith" data-testid="input-last-name" />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" placeholder="john@example.com" data-testid="input-email" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="company">Company</Label>
                <Input id="company" placeholder="ABC Construction" data-testid="input-company" />
              </div>
              <Button data-testid="button-save-profile">Save Changes</Button>
            </CardContent>
          </Card>

        </TabsContent>

        {/* Integrations */}
        <TabsContent value="integrations" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cloud className="w-5 h-5" />
                Procore Integration
              </CardTitle>
              <CardDescription>Connect to sync your Procore projects</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between p-4 rounded-lg bg-muted/50">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-full ${
                    procoreConnection.connected ? "bg-primary/15" : "bg-foreground/15"
                  }`}>
                    <Cloud className={`w-5 h-5 ${
                      procoreConnection.connected ? "text-primary" : "text-foreground"
                    }`} />
                  </div>
                  <div>
                    <p className="font-medium">Procore</p>
                    <p className="text-sm text-muted-foreground">
                      {procoreConnection.connected 
                        ? `${procoreConnection.projectsLinked} projects linked` 
                        : "Not connected"}
                    </p>
                  </div>
                </div>
                {procoreConnection.connected ? (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-primary flex items-center gap-1">
                      <Check className="w-4 h-4" />
                      Connected
                    </span>
                    <Button 
                      variant="outline" 
                      size="sm"
                      onClick={onDisconnectProcore}
                      data-testid="button-disconnect-procore"
                    >
                      Disconnect
                    </Button>
                  </div>
                ) : (
                  <Button onClick={onConnectProcore} data-testid="button-connect-procore">
                    <ExternalLink className="w-4 h-4 mr-2" />
                    Connect Procore
                  </Button>
                )}
              </div>
              
              {procoreConnection.connected && (
                <>
                  <Separator />
                  <div className="space-y-3">
                    <h4 className="text-sm font-medium">Sync Settings</h4>
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium">Push AI insights to Procore</p>
                        <p className="text-xs text-muted-foreground">Add AI analysis as comments on Procore items</p>
                      </div>
                      <Switch defaultChecked data-testid="switch-push-insights" />
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Webhook className="w-5 h-5" />
                Webhooks
              </CardTitle>
              <CardDescription>Configure webhooks for external integrations</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-4 rounded-lg border border-dashed border-muted-foreground/30 text-center">
                <Webhook className="w-8 h-8 mx-auto mb-2 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">No webhooks configured</p>
                <Button variant="outline" size="sm" className="mt-2" data-testid="button-add-webhook">
                  Add Webhook
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Notifications */}
        <TabsContent value="notifications" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="w-5 h-5" />
                Notification Preferences
              </CardTitle>
              <CardDescription>Control how you receive updates</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <h4 className="text-sm font-medium">Email Notifications</h4>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">Inspection reminders</p>
                      <p className="text-xs text-muted-foreground">Upcoming inspection alerts</p>
                    </div>
                    <Switch 
                      checked={notifications.emailInspections}
                      onCheckedChange={(checked) => setNotifications(n => ({...n, emailInspections: checked}))}
                      data-testid="switch-email-inspections"
                    />
                  </div>
                </div>
              </div>
              
              <Separator />
              
              <div className="space-y-4">
                <h4 className="text-sm font-medium">Push Notifications</h4>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">Critical alerts</p>
                      <p className="text-xs text-muted-foreground">Immediate notifications for urgent issues</p>
                    </div>
                    <Switch 
                      checked={notifications.pushAlerts}
                      onCheckedChange={(checked) => setNotifications(n => ({...n, pushAlerts: checked}))}
                      data-testid="switch-push-alerts"
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">AI insights</p>
                      <p className="text-xs text-muted-foreground">Notifications when AI detects issues</p>
                    </div>
                    <Switch 
                      checked={notifications.aiInsights}
                      onCheckedChange={(checked) => setNotifications(n => ({...n, aiInsights: checked}))}
                      data-testid="switch-ai-insights"
                    />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
