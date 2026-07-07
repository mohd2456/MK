/**
 * SystemPage
 * ===========
 * System info, services, updates, power controls, and AI configuration.
 * Fetches real data from API instead of mock.
 */

import { useState } from "react";
import { RefreshCw, Power, RotateCcw, Play, Square, Loader2 } from "lucide-react";
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
import {
  useSystemInfo,
  useContainers,
  useSystemUpdates,
  restartContainer,
  stopContainer,
  startContainer,
} from "@/hooks/useApi";

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
  const { data: containersData, isLoading: ctLoading, mutate: mutateCt } = useContainers();
  const { data: updatesData } = useSystemUpdates();
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const containers = containersData?.containers ?? [];
  const updates = (updatesData as any)?.updates ?? [];

  async function handleContainerAction(
    name: string,
    action: "restart" | "stop" | "start"
  ) {
    setActionLoading(`${name}-${action}`);
    try {
      if (action === "restart") await restartContainer(name);
      else if (action === "stop") await stopContainer(name);
      else await startContainer(name);
      // Refresh the container list
      await mutateCt();
    } catch (e) {
      console.error(`Failed to ${action} ${name}:`, e);
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">System</h1>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            mutateSys();
            mutateCt();
          }}
        >
          <RefreshCw size={14} className={sysLoading || ctLoading ? "animate-spin" : ""} />
          Refresh
        </Button>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="services">Services</TabsTrigger>
          <TabsTrigger value="updates">Updates</TabsTrigger>
          <TabsTrigger value="power">Power</TabsTrigger>
        </TabsList>

        {/* System Overview — Real data from /api/v1/system/info */}
        <TabsContent value="overview">
          <Card>
            <CardContent className="p-6">
              {sysLoading ? (
                <p className="text-sm text-mk-text-muted">Loading system info...</p>
              ) : sysInfo ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-3 gap-x-8">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm text-mk-text-muted min-w-[90px]">Hostname:</span>
                    <span className="text-sm text-mk-text-primary">{sysInfo.hostname}</span>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm text-mk-text-muted min-w-[90px]">Os:</span>
                    <span className="text-sm text-mk-text-primary">{sysInfo.os}</span>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm text-mk-text-muted min-w-[90px]">Kernel:</span>
                    <span className="text-sm text-mk-text-primary">{sysInfo.kernel}</span>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm text-mk-text-muted min-w-[90px]">Uptime:</span>
                    <span className="text-sm text-mk-text-primary">{formatUptime(sysInfo.uptime_seconds)}</span>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm text-mk-text-muted min-w-[90px]">Arch:</span>
                    <span className="text-sm text-mk-text-primary">{sysInfo.arch}</span>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm text-mk-text-muted min-w-[90px]">Cpu:</span>
                    <span className="text-sm text-mk-text-primary">
                      {sysInfo.cpu_model ? `${sysInfo.cpu_model} (${sysInfo.cpu_count}C)` : `${sysInfo.cpu_count} cores`}
                    </span>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm text-mk-text-muted min-w-[90px]">Ram:</span>
                    <span className="text-sm text-mk-text-primary">
                      {sysInfo.ram_total_gb ? `${sysInfo.ram_total_gb} GB (${sysInfo.ram_used_gb} GB used)` : "Unknown"}
                    </span>
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm text-mk-text-muted min-w-[90px]">Python:</span>
                    <span className="text-sm text-mk-text-primary">{sysInfo.python}</span>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-mk-text-muted">Failed to load system info</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Services — Real Docker containers from /api/v1/apps/containers */}
        <TabsContent value="services">
          {ctLoading ? (
            <p className="text-sm text-mk-text-muted p-4">Loading containers...</p>
          ) : containers.length === 0 ? (
            <p className="text-sm text-mk-text-muted p-4">No containers found</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Container</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Image</TableHead>
                  <TableHead>Ports</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {containers.map((ct) => (
                  <TableRow key={ct.name}>
                    <TableCell>
                      <span className="font-medium text-mk-text-primary">{ct.name}</span>
                    </TableCell>
                    <TableCell>
                      <Badge variant={ct.state === "running" ? "success" : "error"}>
                        {ct.state}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs font-mono text-mk-text-muted max-w-[200px] truncate">
                      {ct.image}
                    </TableCell>
                    <TableCell className="text-xs font-mono text-mk-text-muted max-w-[200px] truncate">
                      {ct.ports || "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {ct.state === "running" ? (
                          <>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label="Restart container"
                              disabled={actionLoading === `${ct.name}-restart`}
                              onClick={() => handleContainerAction(ct.name, "restart")}
                            >
                              {actionLoading === `${ct.name}-restart` ? (
                                <Loader2 size={13} className="animate-spin" />
                              ) : (
                                <RotateCcw size={13} />
                              )}
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label="Stop container"
                              disabled={actionLoading === `${ct.name}-stop`}
                              onClick={() => handleContainerAction(ct.name, "stop")}
                            >
                              {actionLoading === `${ct.name}-stop` ? (
                                <Loader2 size={13} className="animate-spin" />
                              ) : (
                                <Square size={13} />
                              )}
                            </Button>
                          </>
                        ) : (
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            aria-label="Start container"
                            disabled={actionLoading === `${ct.name}-start`}
                            onClick={() => handleContainerAction(ct.name, "start")}
                          >
                            {actionLoading === `${ct.name}-start` ? (
                              <Loader2 size={13} className="animate-spin" />
                            ) : (
                              <Play size={13} />
                            )}
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TabsContent>

        {/* Updates — Real from apt/dnf */}
        <TabsContent value="updates">
          {updates.length === 0 ? (
            <Card><CardContent className="p-6 text-center text-mk-text-muted">
              <p className="text-sm">System is up to date. No updates available.</p>
            </CardContent></Card>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-mk-text-secondary">
                Available updates: <span className="text-mk-text-primary font-medium">{updates.length} packages</span>
              </p>
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Package</TableHead><TableHead>Current</TableHead>
                  <TableHead>Available</TableHead><TableHead>Priority</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {updates.map((upd: any) => (
                    <TableRow key={upd.package}>
                      <TableCell className="font-medium text-mk-text-primary font-mono">{upd.package}</TableCell>
                      <TableCell className="font-mono text-xs">{upd.current}</TableCell>
                      <TableCell className="font-mono text-xs text-mk-accent">{upd.available}</TableCell>
                      <TableCell>
                        <Badge variant={upd.priority === "security" ? "error" : upd.priority === "bugfix" ? "info" : "default"}>
                          {upd.priority}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
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
              </div>
              <div className="border-t border-mk-border pt-4 space-y-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-mk-text-muted">Uptime:</span>
                  <span className="text-mk-text-primary">
                    {sysInfo ? formatUptime(sysInfo.uptime_seconds) : "Loading..."}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
