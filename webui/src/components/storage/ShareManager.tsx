/**
 * ShareManager Component
 * =======================
 * SMB/NFS share management table.
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
import type { Share } from "@/types/storage";

interface ShareManagerProps {
  shares?: Share[];
}

const defaultShares: Share[] = [
  { name: "media", type: "SMB", path: "/mnt/media", access: "read-only", status: "active" },
  { name: "downloads", type: "NFS", path: "/mnt/downloads", access: "192.168.1.*", status: "active" },
  { name: "backups", type: "SMB", path: "/mnt/backups", access: "admin-only", status: "active" },
];

export function ShareManager({ shares = defaultShares }: ShareManagerProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Path</TableHead>
          <TableHead>Access</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {shares.map((share) => (
          <TableRow key={share.name}>
            <TableCell className="font-medium text-mk-text-primary">
              {share.name}
            </TableCell>
            <TableCell>
              <Badge variant="default">{share.type}</Badge>
            </TableCell>
            <TableCell className="font-mono text-xs">{share.path}</TableCell>
            <TableCell>{share.access}</TableCell>
            <TableCell>
              <Badge variant={share.status === "active" ? "success" : "default"}>
                {share.status}
              </Badge>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
