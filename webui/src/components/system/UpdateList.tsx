/**
 * UpdateList Component
 * =====================
 * Displays available system updates with version info and priority badges.
 */

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

export interface UpdatePackage {
  name: string;
  current: string;
  available: string;
  priority?: string;
}

interface UpdateListProps {
  packages: UpdatePackage[];
  onUpdateAll?: () => void;
}

const priorityVariant: Record<string, "error" | "accent" | "warning"> = {
  security: "error",
  feature: "accent",
  bugfix: "warning",
};

export function UpdateList({ packages, onUpdateAll }: UpdateListProps) {
  if (packages.length === 0) {
    return (
      <div className="text-center p-6">
        <p className="text-sm text-mk-text-primary font-medium">System is up to date</p>
        <p className="text-xs text-mk-text-muted mt-1">No updates available</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-mk-text-secondary">
          {packages.length} update{packages.length !== 1 ? "s" : ""} available
        </p>
        {onUpdateAll && (
          <Button size="sm" onClick={onUpdateAll}>
            Update All
          </Button>
        )}
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Package</TableHead>
            <TableHead>Current</TableHead>
            <TableHead>Available</TableHead>
            {packages.some((p) => p.priority) && <TableHead>Priority</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {packages.map((pkg) => (
            <TableRow key={pkg.name}>
              <TableCell className="font-medium text-mk-text-primary">
                {pkg.name}
              </TableCell>
              <TableCell className="font-mono text-xs text-mk-text-muted">
                {pkg.current}
              </TableCell>
              <TableCell className="font-mono text-xs text-mk-text-primary">
                {pkg.available}
              </TableCell>
              {packages.some((p) => p.priority) && (
                <TableCell>
                  {pkg.priority && (
                    <Badge variant={priorityVariant[pkg.priority] ?? "accent"}>
                      {pkg.priority}
                    </Badge>
                  )}
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
