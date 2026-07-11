/**
 * ProxySites Component
 * =====================
 * Displays reverse proxy site configurations with domain, backend, SSL, and status.
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
import type { ProxySite } from "@/types/network";

interface ProxySitesProps {
  sites: ProxySite[];
}

const statusVariant: Record<string, "success" | "error" | "warning"> = {
  active: "success",
  inactive: "warning",
  error: "error",
};

export function ProxySites({ sites }: ProxySitesProps) {
  if (sites.length === 0) {
    return (
      <p className="text-sm text-mk-text-muted p-4">No proxy sites configured.</p>
    );
  }

  return (
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
        {sites.map((site) => (
          <TableRow key={site.id}>
            <TableCell className="font-medium text-mk-text-primary">
              {site.domain}
            </TableCell>
            <TableCell className="font-mono text-xs">{site.backend}</TableCell>
            <TableCell>
              <Badge variant="accent">{site.ssl}</Badge>
            </TableCell>
            <TableCell>
              <Badge variant={statusVariant[site.status] ?? "success"}>
                {site.status}
              </Badge>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
