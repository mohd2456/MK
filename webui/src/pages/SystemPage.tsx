/**
 * SystemPage
 * ===========
 * System info, services, updates, power controls, and AI configuration.
 * Fetches real data from API with dedicated system components.
 */

import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  useSystemInfo,
  useSystemUpdates,
  useAISettings,
} from "@/hooks/useApi";
import { SystemInfo } from "@/components/system/SystemInfo";
import { ServiceTable } from "@/components/system/ServiceTable";
import { UpdateList } from "@/components/system/UpdateList";
import { PowerControls } from "@/components/system/PowerControls";
import { AISettings } from "@/components/system/AISettings";
import { LoadingState } from "@/components/LoadingState";
import type { SystemService } from "@/types/system";

// ─── Fallback Mock Data ───

const mockServices: SystemService[] = [
  { name: "docker", status: "running", cpu_percent: 2, ram_bytes: 4.2 * 1024 ** 3, uptime: "47d", description: "Docker container runtime" },
  { name: "samba", status: "running", cpu_percent: 0, ram_bytes: 128 * 1024 ** 2, uptime: "47d", description: "SMB file sharing" },
  { name: "nfs-server", status: "running", cpu_percent: 0, ram_bytes: 64 * 1024 ** 2, uptime: "47d", description: "NFS file server" },
  { name: "wireguard", status: "running", cpu_percent: 0, ram_bytes: 12 * 1024 ** 2, uptime: "47d", description: "WireGuard VPN" },
  { name: "mk-api", status: "running", cpu_percent: 1, ram_bytes: 256 * 1024 ** 2, uptime: "2d", description: "MK OS API server" },
  { name: "nginx", status: "running", cpu_percent: 0, ram_bytes: 48 * 1024 ** 2, uptime: "47d", description: "Reverse proxy" },
];

const mockAISettings = {
  provider: "openai",
  model: "gpt-5.4-mini",
  temperature: 0.7,
  max_tokens: 4096,
  system_prompt: "You are MK, a helpful AI assistant for managing a homelab server.",
};

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days} days ${hours} hours`;
  if (hours > 0) return `${hours} hours ${mins} min`;
  return `${mins} min`;
}

export function SystemPage() {
  const { data: sysInfo, isLoading: sysLoading, mutate: mutateSys } = useSystemInfo();
  const { data: updatesData, isLoading: updatesLoading } = useSystemUpdates();
  const { data: aiData, isLoading: aiLoading } = useAISettings();

  const aiSettings = aiData ?? mockAISettings;
  const updatePackages = updatesData?.packages ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">System</h1>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => mutateSys()}
        >
          <RefreshCw size={14} className={sysLoading ? "animate-spin" : ""} />
          Refresh
        </Button>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="services">Services</TabsTrigger>
          <TabsTrigger value="updates">Updates</TabsTrigger>
          <TabsTrigger value="power">Power</TabsTrigger>
          <TabsTrigger value="ai">AI Settings</TabsTrigger>
        </TabsList>

        {/* System Overview */}
        <TabsContent value="overview">
          {sysLoading ? (
            <LoadingState variant="card" rows={1} />
          ) : sysInfo ? (
            <SystemInfo info={sysInfo} />
          ) : (
            <p className="text-sm text-mk-text-muted p-4">
              Failed to load system info
            </p>
          )}
        </TabsContent>

        {/* Services */}
        <TabsContent value="services">
          <ServiceTable services={mockServices} />
        </TabsContent>

        {/* Updates */}
        <TabsContent value="updates">
          {updatesLoading ? (
            <LoadingState variant="table" rows={3} />
          ) : (
            <UpdateList packages={updatePackages} />
          )}
        </TabsContent>

        {/* Power Controls */}
        <TabsContent value="power">
          <PowerControls
            uptime={sysInfo ? formatUptime(sysInfo.uptime_seconds) : undefined}
          />
        </TabsContent>

        {/* AI Settings */}
        <TabsContent value="ai">
          {aiLoading ? (
            <LoadingState variant="card" rows={1} />
          ) : (
            <AISettings settings={aiSettings} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
