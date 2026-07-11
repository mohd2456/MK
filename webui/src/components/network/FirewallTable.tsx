/**
 * FirewallTable Component
 * ========================
 * Displays firewall rules in a table with chain, source, dest, port, and action badges.
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
import type { FirewallRule } from "@/types/network";

interface FirewallTableProps {
  rules: FirewallRule[];
}

const actionVariant: Record<string, "success" | "error" | "warning"> = {
  ACCEPT: "success",
  DROP: "error",
  REJECT: "warning",
};

export function FirewallTable({ rules }: FirewallTableProps) {
  if (rules.length === 0) {
    return (
      <p className="text-sm text-mk-text-muted p-4">No firewall rules configured.</p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>#</TableHead>
          <TableHead>Chain</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Destination</TableHead>
          <TableHead>Port</TableHead>
          <TableHead>Protocol</TableHead>
          <TableHead>Action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rules.map((rule, i) => (
          <TableRow key={rule.id}>
            <TableCell className="text-mk-text-muted">{i + 1}</TableCell>
            <TableCell className="font-mono text-xs">{rule.chain}</TableCell>
            <TableCell className="font-mono text-xs">{rule.source}</TableCell>
            <TableCell className="font-mono text-xs">{rule.destination}</TableCell>
            <TableCell className="font-mono text-xs">{rule.port}</TableCell>
            <TableCell className="font-mono text-xs">{rule.protocol}</TableCell>
            <TableCell>
              <Badge variant={actionVariant[rule.action] ?? "error"}>
                {rule.action}
              </Badge>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
