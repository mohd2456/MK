/**
 * DashboardPage
 * ==============
 * Home page with at-a-glance system health.
 * No scrolling needed for critical info.
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

export function DashboardPage() {
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">Dashboard</h1>
        <Button variant="secondary" size="sm">
          <RefreshCw size={14} />
          Refresh
        </Button>
      </div>

      {/* Gauge cards row */}
      <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <GaugeCard
          label="CPU"
          value={47}
          displayValue="47%"
          subtitle="12 cores"
          icon={<Cpu size={18} />}
        />
        <GaugeCard
          label="RAM"
          value={62}
          displayValue="62%"
          subtitle="32 / 64 GB"
          icon={<MemoryStick size={18} />}
        />
        <GaugeCard
          label="Network"
          value={35}
          displayValue="120 MB/s"
          subtitle="eth0 (up 45 MB/s)"
          icon={<Wifi size={18} />}
          variant="accent"
        />
        <GaugeCard
          label="Disk"
          value={78}
          displayValue="78%"
          subtitle="18.2 TB used"
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
