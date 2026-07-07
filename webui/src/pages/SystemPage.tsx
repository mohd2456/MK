/**
 * SystemPage
 * ===========
 * System info, services, updates, power controls, and AI configuration.
 */

import { RefreshCw, Power, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { cn, formatBytes } from "@/lib/utils";

// Mock data
const systemInfo = {
  hostname: "mk-server",
  os: "MK OS 1.0 (Debian 12 base)",
  kernel: "6.6.10-amd64",
  uptime: "47 days 3 hours",
  cpu: "AMD Ryzen 9 7950X (16C/32T)",
  ram: "64 GB DDR5-5600 (32 GB used)",
  bootDrive: "Samsung 980 Pro 500GB (NVMe)",
};

const services = [
  { name: "docker", status: "running", cpu: 2, ram: 4.2 * 1024 ** 3, uptime: "47d", description: "Docker Engine" },
  { name: "samba", status: "running", cpu: 0, ram: 128 * 1024 ** 2, uptime: "47d", description: "Samba File Sharing" },
  { name: "nfs-server", status: "running", cpu: 0, ram: 64 * 1024 ** 2, uptime: "47d", description: "NFS Server" },
  { name: "wireguard", status: "running", cpu: 0, ram: 12 * 1024 ** 2, uptime: "47d", description: "WireGuard VPN" },
  { name: "mk-api", status: "running", cpu: 1, ram: 256 * 1024 ** 2, uptime: "2d", description: "MK OS API Server" },
  { name: "nginx", status: "running", cpu: 0, ram: 48 * 1024 ** 2, uptime: "47d", description: "Nginx Reverse Proxy" },
  { name: "cron", status: "running", cpu: 0, ram: 8 * 1024 ** 2, uptime: "47d", description: "Cron Scheduler" },
];

const updates = [
  { pkg: "linux-image", current: "6.6.8", available: "6.6.10", priority: "security" },
  { pkg: "docker-ce", current: "24.0.7", available: "25.0.1", priority: "feature" },
  { pkg: "mk-server", current: "1.0.2", available: "1.0.3", priority: "bugfix" },
];

const priorityBadge: Record<string, "error" | "accent" | "info"> = {
  security: "error",
  feature: "accent",
  bugfix: "info",
};

export function SystemPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">System</h1>
        <Button variant="secondary" size="sm">
          <RefreshCw size={14} />
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
          <Card>
            <CardContent className="p-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-3 gap-x-8">
                {Object.entries(systemInfo).map(([key, value]) => (
                  <div key={key} className="flex items-baseline gap-2">
                    <span className="text-sm text-mk-text-muted capitalize min-w-[90px]">
                      {key.replace(/([A-Z])/g, " $1").trim()}:
                    </span>
                    <span className="text-sm text-mk-text-primary">{value}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Services */}
        <TabsContent value="services">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Service</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>CPU</TableHead>
                <TableHead>RAM</TableHead>
                <TableHead>Uptime</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {services.map((svc) => (
                <TableRow key={svc.name}>
                  <TableCell>
                    <div>
                      <span className="font-medium text-mk-text-primary">{svc.name}</span>
                      <p className="text-[11px] text-mk-text-muted">{svc.description}</p>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={svc.status === "running" ? "success" : "error"}>
                      {svc.status}
                    </Badge>
                  </TableCell>
                  <TableCell>{svc.cpu}%</TableCell>
                  <TableCell>{formatBytes(svc.ram)}</TableCell>
                  <TableCell className="text-mk-text-muted">{svc.uptime}</TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon-sm" aria-label="Restart service">
                      <RotateCcw size={13} />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TabsContent>

        {/* Updates */}
        <TabsContent value="updates">
          <div className="space-y-4">
            <p className="text-sm text-mk-text-secondary">
              Available updates: <span className="text-mk-text-primary font-medium">{updates.length} packages</span>
            </p>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Package</TableHead>
                  <TableHead>Current</TableHead>
                  <TableHead>Available</TableHead>
                  <TableHead>Priority</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {updates.map((upd) => (
                  <TableRow key={upd.pkg}>
                    <TableCell className="font-medium text-mk-text-primary font-mono">
                      {upd.pkg}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{upd.current}</TableCell>
                    <TableCell className="font-mono text-xs text-mk-accent">{upd.available}</TableCell>
                    <TableCell>
                      <Badge variant={priorityBadge[upd.priority]}>
                        {upd.priority}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="flex gap-3">
              <Button>Update All</Button>
              <Button variant="secondary">Update Selected</Button>
            </div>
          </div>
        </TabsContent>

        {/* Power */}
        <TabsContent value="power">
          <Card>
            <CardContent className="p-6 space-y-6">
              <div className="flex flex-wrap gap-3">
                <Button variant="secondary" size="lg">
                  <RotateCcw size={16} />
                  Reboot
                </Button>
                <Button variant="destructive" size="lg">
                  <Power size={16} />
                  Shutdown
                </Button>
                <Button variant="outline" size="lg">
                  Schedule
                </Button>
              </div>
              <div className="border-t border-mk-border pt-4 space-y-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-mk-text-muted">Last boot:</span>
                  <span className="text-mk-text-primary">2024-01-01 08:00</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-mk-text-muted">UPS:</span>
                  <span className="text-mk-text-primary">APC 1500VA - 98% (6h runtime)</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* AI Settings */}
        <TabsContent value="ai">
          <Card>
            <CardContent className={cn("p-6 space-y-4 max-w-lg")}>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-mk-text-secondary">Provider</span>
                  <span className="text-sm text-mk-text-primary">Anthropic (Claude)</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-mk-text-secondary">Model</span>
                  <span className="text-sm font-mono text-mk-text-primary">claude-sonnet-4-20250514</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-mk-text-secondary">API Key</span>
                  <span className="text-sm font-mono text-mk-text-muted">sk-...****</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-mk-text-secondary">Temperature</span>
                  <span className="text-sm text-mk-text-primary">0.7</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-mk-text-secondary">Max tokens</span>
                  <span className="text-sm text-mk-text-primary">4096</span>
                </div>
              </div>
              <div className="border-t border-mk-border pt-4 space-y-2">
                <h4 className="text-sm font-semibold text-mk-text-primary">Context Options</h4>
                <div className="space-y-1.5 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-mk-success">&#10003;</span>
                    <span className="text-mk-text-secondary">Include system metrics</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-mk-success">&#10003;</span>
                    <span className="text-mk-text-secondary">Include recent alerts</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-mk-success">&#10003;</span>
                    <span className="text-mk-text-secondary">Include page context</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-mk-text-muted">&#10007;</span>
                    <span className="text-mk-text-muted">Include full command history</span>
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
