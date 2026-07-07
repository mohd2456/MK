/**
 * NetworkPage
 * ============
 * Interfaces, firewall, WireGuard, DNS, and reverse proxy.
 */

import { Search } from "lucide-react";
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
import { cn } from "@/lib/utils";

// ─── Mock Data ───

const interfaces = [
  { name: "eth0", type: "Physical", ip: "192.168.1.10/24", speed: "10 Gbps", status: "Connected" },
  { name: "eth1", type: "Physical", ip: "10.0.0.1/24", speed: "1 Gbps", status: "Connected" },
  { name: "br0", type: "Bridge", ip: "172.17.0.1/16", speed: "-", status: "Up" },
  { name: "wg0", type: "WireGuard", ip: "10.8.0.1/24", speed: "-", status: "Active" },
];

const firewallRules = [
  { id: "1", chain: "INPUT", source: "192.168.1.*", dest: "*", port: "22", action: "ACCEPT" },
  { id: "2", chain: "INPUT", source: "*", dest: "*", port: "80,443", action: "ACCEPT" },
  { id: "3", chain: "INPUT", source: "*", dest: "*", port: "*", action: "DROP" },
];

const wireguardPeers = [
  { name: "phone", publicKey: "aB3c...xYz", endpoint: "dynamic", lastSeen: "2 min ago" },
  { name: "laptop", publicKey: "dE4f...wVu", endpoint: "73.42.18.5", lastSeen: "1 hr ago" },
  { name: "remote-site", publicKey: "gH5i...tSr", endpoint: "198.51.100.1", lastSeen: "30 sec ago" },
];

const proxySites = [
  { domain: "plex.example.com", backend: "localhost:32400", ssl: "Auto", status: "Active" },
  { domain: "sonarr.example.com", backend: "localhost:8989", ssl: "Auto", status: "Active" },
  { domain: "grafana.example.com", backend: "localhost:3000", ssl: "Auto", status: "Active" },
];

export function NetworkPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-mk-text-primary">Network</h1>
        <Button variant="secondary" size="sm">
          <Search size={14} />
          Scan
        </Button>
      </div>

      <Tabs defaultValue="interfaces">
        <TabsList>
          <TabsTrigger value="interfaces">Interfaces</TabsTrigger>
          <TabsTrigger value="firewall">Firewall</TabsTrigger>
          <TabsTrigger value="wireguard">WireGuard</TabsTrigger>
          <TabsTrigger value="dns">DNS</TabsTrigger>
          <TabsTrigger value="proxy">Reverse Proxy</TabsTrigger>
        </TabsList>

        {/* Interfaces */}
        <TabsContent value="interfaces">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>IP Address</TableHead>
                <TableHead>Speed</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {interfaces.map((iface) => (
                <TableRow key={iface.name}>
                  <TableCell className="font-mono text-xs font-medium text-mk-text-primary">
                    {iface.name}
                  </TableCell>
                  <TableCell>{iface.type}</TableCell>
                  <TableCell className="font-mono text-xs">{iface.ip}</TableCell>
                  <TableCell>{iface.speed}</TableCell>
                  <TableCell>
                    <Badge variant="success">{iface.status}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TabsContent>

        {/* Firewall */}
        <TabsContent value="firewall">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>Chain</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Dest</TableHead>
                <TableHead>Port</TableHead>
                <TableHead>Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {firewallRules.map((rule, i) => (
                <TableRow key={rule.id}>
                  <TableCell className="text-mk-text-muted">{i + 1}</TableCell>
                  <TableCell className="font-mono text-xs">{rule.chain}</TableCell>
                  <TableCell className="font-mono text-xs">{rule.source}</TableCell>
                  <TableCell className="font-mono text-xs">{rule.dest}</TableCell>
                  <TableCell className="font-mono text-xs">{rule.port}</TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        rule.action === "ACCEPT" ? "success"
                          : rule.action === "DROP" ? "error"
                            : "warning"
                      }
                    >
                      {rule.action}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TabsContent>

        {/* WireGuard */}
        <TabsContent value="wireguard">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Peer Name</TableHead>
                <TableHead>Public Key</TableHead>
                <TableHead>Endpoint</TableHead>
                <TableHead>Last Seen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {wireguardPeers.map((peer) => (
                <TableRow key={peer.name}>
                  <TableCell className="font-medium text-mk-text-primary">
                    {peer.name}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{peer.publicKey}</TableCell>
                  <TableCell>{peer.endpoint}</TableCell>
                  <TableCell className="text-mk-text-muted">{peer.lastSeen}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TabsContent>

        {/* DNS */}
        <TabsContent value="dns">
          <div className={cn(
            "rounded-[8px] border border-mk-border bg-mk-surface p-6 space-y-4",
            "max-w-lg"
          )}>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm text-mk-text-secondary">Primary DNS</span>
                <span className="text-sm font-mono text-mk-text-primary">1.1.1.1</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-mk-text-secondary">Secondary DNS</span>
                <span className="text-sm font-mono text-mk-text-primary">8.8.8.8</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-mk-text-secondary">Search Domain</span>
                <span className="text-sm font-mono text-mk-text-primary">home.lab</span>
              </div>
            </div>
            <div className="border-t border-mk-border pt-4">
              <h4 className="text-sm font-semibold text-mk-text-primary mb-2">Local Overrides</h4>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-mono text-mk-text-secondary">plex.home.lab</span>
                  <span className="font-mono text-mk-text-muted">192.168.1.10</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-mono text-mk-text-secondary">nas.home.lab</span>
                  <span className="font-mono text-mk-text-muted">192.168.1.10</span>
                </div>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* Reverse Proxy */}
        <TabsContent value="proxy">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Domain</TableHead>
                <TableHead>Backend</TableHead>
                <TableHead>SSL</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {proxySites.map((site) => (
                <TableRow key={site.domain}>
                  <TableCell className="font-medium text-mk-text-primary">
                    {site.domain}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{site.backend}</TableCell>
                  <TableCell>
                    <Badge variant="accent">{site.ssl}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="success">{site.status}</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TabsContent>
      </Tabs>
    </div>
  );
}
