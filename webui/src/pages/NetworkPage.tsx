/**
 * NetworkPage — Real network interface data
 */

import { RefreshCw, Wifi, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from "@/components/ui/table";
import { useNetworkInterfacesV2, useTailscaleStatus } from "@/hooks/useApi";

export function NetworkPage() {
  const { data: ifData, mutate: mi } = useNetworkInterfacesV2();
  const { data: tsData, mutate: mt } = useTailscaleStatus();

  const interfaces = (ifData as any)?.interfaces ?? [];
  const tsState = (tsData as any)?.BackendState ?? "Unknown";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">Network</h1>
        <Button variant="secondary" size="sm" onClick={() => { mi(); mt(); }}>
          <RefreshCw size={14} /> Refresh
        </Button>
      </div>

      {/* Tailscale status card */}
      <Card>
        <CardContent className="p-4 flex items-center gap-4">
          <Globe size={20} className="text-mk-accent" />
          <div>
            <p className="text-sm font-medium text-mk-text-primary">Tailscale</p>
            <p className="text-xs text-mk-text-muted">VPN mesh network</p>
          </div>
          <Badge variant={tsState === "Running" ? "success" : "default"} className="ml-auto">
            {tsState}
          </Badge>
        </CardContent>
      </Card>

      {/* Interfaces */}
      {interfaces.length === 0 ? (
        <Card><CardContent className="p-6 text-center text-mk-text-muted">
          <Wifi size={32} className="mx-auto mb-2 opacity-40" />
          <p>No network interfaces detected.</p>
        </CardContent></Card>
      ) : (
        <Table>
          <TableHeader><TableRow>
            <TableHead>Interface</TableHead>
            <TableHead>State</TableHead>
            <TableHead>IP Address</TableHead>
            <TableHead>Speed</TableHead>
            <TableHead>MAC</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {interfaces.map((iface: any) => (
              <TableRow key={iface.name}>
                <TableCell className="font-mono font-medium text-mk-text-primary">{iface.name}</TableCell>
                <TableCell>
                  <Badge variant={iface.state === "up" ? "success" : "default"}>{iface.state}</Badge>
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {iface.addresses?.filter((a: any) => a.family === "inet").map((a: any) => a.address).join(", ") || "—"}
                </TableCell>
                <TableCell>{iface.speed_mbps ? `${iface.speed_mbps} Mbps` : "—"}</TableCell>
                <TableCell className="font-mono text-xs text-mk-text-muted">{iface.mac || "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
