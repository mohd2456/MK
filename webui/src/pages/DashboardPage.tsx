/**
 * DashboardPage
 * ==============
 * Home page with at-a-glance system health.
 * Fetches real data from /api/v1/dashboard/summary.
 *
 * Layout:
 * - Top row: 4 gauge cards (CPU, RAM, Network, Disk)
 * - Bottom: 2x2 grid (Health, Quick Actions, Alerts, Activity)
 */

import { Cpu, MemoryStick, Wifi, HardDrive, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GaugeCard } from "@/components/dashboard/GaugeCard";
import { HealthSummary } from "@/components/dashboard/HealthSummary";
import { QuickActions } from "@/components/dashboard/QuickActions";
import { AlertsList } from "@/components/dashboard/AlertsList";
import { ActivityLog } from "@/components/dashboard/ActivityLog";
import { useDashboardSummary } from "@/hooks/useApi";

export function DashboardPage() {
  const { data, isLoading, mutate } = useDashboardSummary();

  const cpuPercent = data?.cpu_percent ?? 0;
  const ramPercent = data?.ram_percent ?? 0;
  const ramUsed = data?.ram_used_gb ?? 0;
  const ramTotal = data?.ram_total_gb ?? 0;
  const diskPercent = data?.disk_percent ?? 0;
  const diskUsed = data?.disk_used_tb ?? 0;
  const diskTotal = data?.disk_total_tb ?? 0;
  const netIn = data?.network_in_mbps ?? 0;
  const netOut = data?.network_out_mbps ?? 0;

  // Network gauge value: percentage of a theoretical 1 Gbps link
  const netTotal = netIn + netOut;
  const netGaugePercent = Math.min(100, (netTotal / 1000) * 100);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">Dashboard</h1>
        <Button variant="secondary" size="sm" onClick={() => mutate()}>
          <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
          Refresh
        </Button>
      </div>

      {/* Gauge cards row */}
      <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <GaugeCard
          label="CPU"
          value={cpuPercent}
          displayValue={`${Math.round(cpuPercent)}%`}
          subtitle={isLoading ? "Loading..." : `${data?.containers_running ?? 0} containers`}
          icon={<Cpu size={18} />}
        />
        <GaugeCard
          label="RAM"
          value={ramPercent}
          displayValue={`${Math.round(ramPercent)}%`}
          subtitle={isLoading ? "Loading..." : `${ramUsed.toFixed(1)} / ${ramTotal.toFixed(1)} GB`}
          icon={<MemoryStick size={18} />}
        />
        <GaugeCard
          label="Network"
          value={netGaugePercent}
          displayValue={`${netIn.toFixed(0)} MB/s`}
          subtitle={isLoading ? "Loading..." : `up ${netOut.toFixed(0)} MB/s`}
          icon={<Wifi size={18} />}
          variant="accent"
        />
        <GaugeCard
          label="Disk"
          value={diskPercent}
          displayValue={`${Math.round(diskPercent)}%`}
          subtitle={isLoading ? "Loading..." : `${diskUsed.toFixed(1)} / ${diskTotal.toFixed(1)} TB`}
          icon={<HardDrive size={18} />}
        />
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <HealthSummary />
        <QuickActions />
        <AlertsList />
        <ActivityLog />
      </div>
    </div>
  );
}
