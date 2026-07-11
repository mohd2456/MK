/**
 * WireGuardPeers Component
 * =========================
 * Displays WireGuard VPN peers in a table with name, public key, endpoint, and last seen.
 */

import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import type { WireGuardPeer } from "@/types/network";

interface WireGuardPeersProps {
  peers: WireGuardPeer[];
}

export function WireGuardPeers({ peers }: WireGuardPeersProps) {
  if (peers.length === 0) {
    return (
      <p className="text-sm text-mk-text-muted p-4">No WireGuard peers configured.</p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Peer Name</TableHead>
          <TableHead>Public Key</TableHead>
          <TableHead>Endpoint</TableHead>
          <TableHead>Allowed IPs</TableHead>
          <TableHead>Last Seen</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {peers.map((peer) => (
          <TableRow key={peer.id}>
            <TableCell className="font-medium text-mk-text-primary">
              {peer.name}
            </TableCell>
            <TableCell className="font-mono text-xs max-w-[140px] truncate">
              {peer.public_key}
            </TableCell>
            <TableCell className="font-mono text-xs">{peer.endpoint || "dynamic"}</TableCell>
            <TableCell className="font-mono text-xs">{peer.allowed_ips}</TableCell>
            <TableCell>
              <Badge variant="accent">{peer.last_seen}</Badge>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
